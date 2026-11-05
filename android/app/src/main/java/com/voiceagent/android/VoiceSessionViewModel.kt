package com.voiceagent.android

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.voiceagent.android.audio.AudioEngine
import com.voiceagent.android.protocol.VoiceProtocol
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import okhttp3.*
import okio.ByteString
import okio.ByteString.Companion.toByteString

data class VoiceUiState(
    val status: String = "Disconnected",
    val assistantState: String = "idle",
    val transcript: String = "",
    val response: String = "",
    val muted: Boolean = false,
    val toolStatus: String = "",
    val confirmationId: String? = null,
    val confirmationPrompt: String? = null,
    val dialerTarget: String? = null,
    val citations: List<String> = emptyList(),
    val telemetry: String = "",
    val error: String? = null,
)

sealed class VoiceUiEffect {
    data class LaunchDialer(val phoneNumber: String) : VoiceUiEffect()
}

class VoiceSessionViewModel(application: Application) : AndroidViewModel(application) {
    private val _state = MutableStateFlow(VoiceUiState())
    val state: StateFlow<VoiceUiState> = _state.asStateFlow()

    private val _effects = MutableSharedFlow<VoiceUiEffect>()
    val effects: SharedFlow<VoiceUiEffect> = _effects.asSharedFlow()

    private val client = OkHttpClient()
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val protocol = VoiceProtocol()
    private val audio = AudioEngine(application)
    private var socket: WebSocket? = null
    private val preferences = application.getSharedPreferences("voice_agent", 0)

    fun connect() {
        if (socket != null) return
        val reconnect = preferences.getString("session_id", null)
        val url = if (reconnect.isNullOrBlank()) {
            BuildConfig.VOICE_AGENT_WS_URL
        } else {
            "${BuildConfig.VOICE_AGENT_WS_URL}?session_id=$reconnect"
        }

        _state.value = _state.value.copy(status = "Connecting", error = null)
        val serviceIntent = Intent(getApplication(), com.voiceagent.android.audio.VoiceForegroundService::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            getApplication<Application>().startForegroundService(serviceIntent)
        } else {
            getApplication<Application>().startService(serviceIntent)
        }

        socket = client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                _state.value = _state.value.copy(status = "Connected")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val element = json.parseToJsonElement(text).jsonObject
                    handle(element)
                } catch (e: Exception) {
                    _state.value = _state.value.copy(error = "Protocol decode error: ${e.message}")
                }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                audio.play(bytes.toByteArray())
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                socket = null
                audio.stop()
                _state.value = _state.value.copy(status = "Error", error = t.message ?: "WebSocket failure")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                socket = null
                audio.stop()
                _state.value = _state.value.copy(status = "Disconnected")
            }
        })
    }

    private fun handle(event: JsonObject) {
        val eventType = event["type"]?.toString()?.trim('"')
        when (eventType) {
            "ready" -> {
                protocol.ready(event)
                val reconnectToken = preferences.getString("session_id", null)
                protocol.createHello(resumeToken = reconnectToken)?.let { socket?.send(it) }
                protocol.createAudioFormat()?.let { socket?.send(it) }
                event["session_id"]?.toString()?.trim('"')?.let { sid ->
                    preferences.edit().putString("session_id", sid).apply()
                }

                audio.start { frame ->
                    protocol.createAudioFrameMetadata(byteLength = frame.size)?.let { meta ->
                        socket?.send(meta)
                        socket?.send(frame.toByteString())
                    }
                }
            }
            else -> if (protocol.accepts(event)) {
                when (eventType) {
                    "state" -> {
                        val st = event["state"]?.toString()?.trim('"') ?: "idle"
                        _state.value = _state.value.copy(assistantState = st)
                    }
                    "transcript" -> {
                        val text = event["text"]?.toString()?.trim('"') ?: ""
                        _state.value = _state.value.copy(transcript = text)
                    }
                    "response_text_delta" -> {
                        val delta = event["text"]?.toString()?.trim('"') ?: ""
                        _state.value = _state.value.copy(response = _state.value.response + delta)
                    }
                    "audio_flush" -> {
                        protocol.generationChanged(event["generation_id"]?.toString()?.trim('"'))
                        audio.flush()
                    }
                    "tool_status" -> {
                        val toolName = event["tool_name"]?.toString()?.trim('"') ?: ""
                        val status = event["status"]?.toString()?.trim('"') ?: ""
                        _state.value = _state.value.copy(toolStatus = "$toolName: $status")
                    }
                    "tool_confirmation" -> {
                        val confId = event["confirmation_id"]?.toString()?.trim('"')
                        val prompt = event["prompt"]?.toString()?.trim('"')
                        val toolName = event["tool_name"]?.toString()?.trim('"')
                        _state.value = _state.value.copy(
                            confirmationId = confId,
                            confirmationPrompt = prompt,
                        )
                    }
                    "ui_card" -> {
                        val cardType = event["card_type"]?.toString()?.trim('"')
                        if (cardType == "citations") {
                            _state.value = _state.value.copy(citations = listOf(event["payload"].toString()))
                        } else if (cardType == "phone_call") {
                            val target = event["payload"]?.jsonObject?.get("phone_number")?.toString()?.trim('"')
                            if (!target.isNullOrBlank()) {
                                _state.value = _state.value.copy(dialerTarget = target)
                            }
                        }
                    }
                    "telemetry" -> {
                        _state.value = _state.value.copy(telemetry = event["measurements"].toString())
                    }
                    "error" -> {
                        _state.value = _state.value.copy(error = event["message"]?.toString()?.trim('"'))
                    }
                }
            }
        }
    }

    fun setMuted(muted: Boolean) {
        audio.setMuted(muted)
        _state.value = _state.value.copy(muted = muted)
    }

    fun confirmTool(approved: Boolean) {
        val id = _state.value.confirmationId ?: return
        protocol.createToolConfirmationResponse(confirmationId = id, approved = approved)?.let {
            socket?.send(it)
        }
        _state.value = _state.value.copy(confirmationId = null, confirmationPrompt = null)
    }

    fun confirmDialerCall(approved: Boolean) {
        val target = _state.value.dialerTarget ?: return
        _state.value = _state.value.copy(dialerTarget = null)
        if (approved) {
            viewModelScope.launch {
                _effects.emit(VoiceUiEffect.LaunchDialer(target))
            }
        }
    }

    fun cancelActiveTurn() {
        protocol.createCancel(reason = "user_cancel")?.let { socket?.send(it) }
        audio.flush()
    }

    fun stop() {
        socket?.close(1000, "user_stop")
        socket = null
        audio.stop()
        getApplication<Application>().stopService(
            Intent(getApplication(), com.voiceagent.android.audio.VoiceForegroundService::class.java)
        )
    }

    override fun onCleared() {
        stop()
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
    }
}
