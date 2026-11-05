package com.voiceagent.android.protocol

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

class VoiceProtocol(val session: ProtocolSession = ProtocolSession()) {
    val json = Json {
        encodeDefaults = true
        ignoreUnknownKeys = true
        isLenient = true
    }

    fun ready(payload: JsonObject) {
        val sid = payload["session_id"]?.toString()?.trim('"')
        val gid = payload["generation_id"]?.toString()?.trim('"')
        if (!sid.isNullOrBlank()) {
            session.reset(sid, gid)
        }
    }

    fun accepts(payload: JsonObject): Boolean {
        val eventGeneration = payload["generation_id"]?.toString()?.trim('"')
        return session.generationId == null || eventGeneration == null || eventGeneration == session.generationId
    }

    fun generationChanged(generationId: String?) {
        if (!generationId.isNullOrBlank()) {
            session.generationId = generationId
        }
    }

    fun createHello(resumeToken: String? = null): String? {
        val sid = session.sessionId ?: return null
        val event = ClientHelloEvent(
            sessionId = sid,
            turnId = session.turnId,
            sequence = session.sequence++,
            timestampMs = System.currentTimeMillis(),
            resumeToken = resumeToken,
            generationId = session.generationId,
        )
        return json.encodeToString(ClientHelloEvent.serializer(), event)
    }

    fun createAudioFormat(format: AudioFormat = AudioFormat()): String? {
        val sid = session.sessionId ?: return null
        val event = ClientAudioFormatEvent(
            sessionId = sid,
            turnId = session.turnId,
            sequence = session.sequence++,
            timestampMs = System.currentTimeMillis(),
            format = format,
            generationId = session.generationId,
        )
        return json.encodeToString(ClientAudioFormatEvent.serializer(), event)
    }

    fun createAudioFrameMetadata(byteLength: Int, frameIndex: Long = 0): String? {
        val sid = session.sessionId ?: return null
        val event = ClientAudioFrameMetadata(
            sessionId = sid,
            turnId = session.turnId,
            sequence = session.sequence++,
            timestampMs = System.currentTimeMillis(),
            byteLength = byteLength,
            frameIndex = frameIndex,
            generationId = session.generationId,
        )
        return json.encodeToString(ClientAudioFrameMetadata.serializer(), event)
    }

    fun createCancel(reason: String = "user_cancel"): String? {
        val sid = session.sessionId ?: return null
        val event = ClientCancelEvent(
            sessionId = sid,
            turnId = session.turnId,
            sequence = session.sequence++,
            timestampMs = System.currentTimeMillis(),
            reason = reason,
            generationId = session.generationId,
        )
        return json.encodeToString(ClientCancelEvent.serializer(), event)
    }

    fun createFlush(reason: String = "barge_in"): String? {
        val sid = session.sessionId ?: return null
        val event = ClientFlushEvent(
            sessionId = sid,
            turnId = session.turnId,
            sequence = session.sequence++,
            timestampMs = System.currentTimeMillis(),
            reason = reason,
            generationId = session.generationId,
        )
        return json.encodeToString(ClientFlushEvent.serializer(), event)
    }

    fun createToolConfirmationResponse(confirmationId: String, approved: Boolean): String? {
        val sid = session.sessionId ?: return null
        val event = ClientToolConfirmationResponseEvent(
            sessionId = sid,
            turnId = session.turnId,
            sequence = session.sequence++,
            timestampMs = System.currentTimeMillis(),
            confirmationId = confirmationId,
            approved = approved,
            generationId = session.generationId,
        )
        return json.encodeToString(ClientToolConfirmationResponseEvent.serializer(), event)
    }

    fun createPing(): String? {
        val sid = session.sessionId ?: return null
        val event = ClientPingEvent(
            sessionId = sid,
            turnId = session.turnId,
            sequence = session.sequence++,
            timestampMs = System.currentTimeMillis(),
            generationId = session.generationId,
        )
        return json.encodeToString(ClientPingEvent.serializer(), event)
    }
}
