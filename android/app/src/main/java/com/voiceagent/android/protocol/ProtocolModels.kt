package com.voiceagent.android.protocol

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

const val PROTOCOL_VERSION = "1.0"

@Serializable
data class AudioFormat(
    val encoding: String = "pcm_s16le",
    @SerialName("sample_rate_hz") val sampleRateHz: Int = 16_000,
    val channels: Int = 1,
    @SerialName("sample_width_bytes") val sampleWidthBytes: Int = 2,
)

data class ProtocolSession(
    var sessionId: String? = null,
    var generationId: String? = null,
    var turnId: String = "turn-android",
    var sequence: Long = 0,
) {
    fun reset(newSessionId: String, newGenerationId: String? = null) {
        sessionId = newSessionId
        generationId = newGenerationId
        sequence = 0
    }
}

// Client-originated messages
@Serializable
data class ClientHelloEvent(
    val type: String = "hello",
    @SerialName("protocol_version") val protocolVersion: String = PROTOCOL_VERSION,
    @SerialName("session_id") val sessionId: String,
    @SerialName("turn_id") val turnId: String,
    val sequence: Long,
    @SerialName("timestamp_ms") val timestampMs: Long,
    @SerialName("client_name") val clientName: String = "android",
    @SerialName("client_version") val clientVersion: String = "0.1.0",
    @SerialName("resume_token") val resumeToken: String? = null,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ClientAudioFormatEvent(
    val type: String = "audio_format",
    @SerialName("protocol_version") val protocolVersion: String = PROTOCOL_VERSION,
    @SerialName("session_id") val sessionId: String,
    @SerialName("turn_id") val turnId: String,
    val sequence: Long,
    @SerialName("timestamp_ms") val timestampMs: Long,
    val format: AudioFormat = AudioFormat(),
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ClientAudioFrameMetadata(
    val type: String = "audio_frame",
    @SerialName("protocol_version") val protocolVersion: String = PROTOCOL_VERSION,
    @SerialName("session_id") val sessionId: String,
    @SerialName("turn_id") val turnId: String,
    val sequence: Long,
    @SerialName("timestamp_ms") val timestampMs: Long,
    @SerialName("byte_length") val byteLength: Int,
    @SerialName("frame_index") val frameIndex: Long = 0,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ClientCancelEvent(
    val type: String = "cancel",
    @SerialName("protocol_version") val protocolVersion: String = PROTOCOL_VERSION,
    @SerialName("session_id") val sessionId: String,
    @SerialName("turn_id") val turnId: String,
    val sequence: Long,
    @SerialName("timestamp_ms") val timestampMs: Long,
    val reason: String = "user_cancel",
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ClientFlushEvent(
    val type: String = "flush",
    @SerialName("protocol_version") val protocolVersion: String = PROTOCOL_VERSION,
    @SerialName("session_id") val sessionId: String,
    @SerialName("turn_id") val turnId: String,
    val sequence: Long,
    @SerialName("timestamp_ms") val timestampMs: Long,
    val reason: String = "barge_in",
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ClientToolConfirmationResponseEvent(
    val type: String = "tool_confirmation_response",
    @SerialName("protocol_version") val protocolVersion: String = PROTOCOL_VERSION,
    @SerialName("session_id") val sessionId: String,
    @SerialName("turn_id") val turnId: String,
    val sequence: Long,
    @SerialName("timestamp_ms") val timestampMs: Long,
    @SerialName("confirmation_id") val confirmationId: String,
    val approved: Boolean,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ClientPingEvent(
    val type: String = "ping",
    @SerialName("protocol_version") val protocolVersion: String = PROTOCOL_VERSION,
    @SerialName("session_id") val sessionId: String,
    @SerialName("turn_id") val turnId: String,
    val sequence: Long,
    @SerialName("timestamp_ms") val timestampMs: Long,
    @SerialName("generation_id") val generationId: String? = null,
)

// Server-originated messages
@Serializable
data class ServerReadyEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    @SerialName("turn_id") val turnId: String,
    @SerialName("server_version") val serverVersion: String,
    @SerialName("audio_format") val audioFormat: AudioFormat,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ServerStateEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    val state: String,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ServerTranscriptEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    val text: String,
    @SerialName("is_final") val isFinal: Boolean = false,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ServerResponseTextDeltaEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    val text: String,
    @SerialName("is_final") val isFinal: Boolean = false,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ServerAudioFlushEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    val reason: String = "barge_in",
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ServerToolStatusEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    @SerialName("tool_name") val toolName: String,
    val status: String,
    val detail: String? = null,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ServerToolConfirmationEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    @SerialName("tool_name") val toolName: String,
    @SerialName("confirmation_id") val confirmationId: String,
    val prompt: String,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ServerUiCardEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    @SerialName("card_type") val cardType: String,
    val payload: JsonObject? = null,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ServerErrorEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    val code: String,
    val message: String,
    val retryable: Boolean = false,
    @SerialName("generation_id") val generationId: String? = null,
)

@Serializable
data class ServerTelemetryEvent(
    val type: String,
    @SerialName("protocol_version") val protocolVersion: String,
    @SerialName("session_id") val sessionId: String,
    val measurements: JsonObject? = null,
    @SerialName("generation_id") val generationId: String? = null,
)
