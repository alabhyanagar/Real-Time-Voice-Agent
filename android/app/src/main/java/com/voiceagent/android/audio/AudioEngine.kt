package com.voiceagent.android.audio

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.AcousticEchoCanceler
import android.media.MediaRecorder
import android.media.NoiseSuppressor
import android.os.Build
import android.os.Process
import java.util.concurrent.atomic.AtomicBoolean

class AudioEngine(private val context: Context? = null) {
    companion object {
        const val SAMPLE_RATE = 16_000
        const val FRAME_BYTES = 640 // 20ms of 16kHz 16-bit mono PCM
    }

    private var recorder: AudioRecord? = null
    private var player: AudioTrack? = null
    private var worker: Thread? = null
    private val running = AtomicBoolean(false)
    @Volatile private var muted = false

    private val audioManager = context?.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
    private var focusRequest: AudioFocusRequest? = null
    private var becomingNoisyReceiver: BroadcastReceiver? = null

    private val focusChangeListener = AudioManager.OnAudioFocusChangeListener { focusChange ->
        when (focusChange) {
            AudioManager.AUDIOFOCUS_LOSS,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> {
                player?.pause()
            }
            AudioManager.AUDIOFOCUS_GAIN -> {
                player?.play()
            }
        }
    }

    private fun requestAudioFocus() {
        val am = audioManager ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val playbackAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
            val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                .setAudioAttributes(playbackAttributes)
                .setAcceptsDelayedFocusGain(false)
                .setOnAudioFocusChangeListener(focusChangeListener)
                .build()
            focusRequest = request
            am.requestAudioFocus(request)
        } else {
            @Suppress("DEPRECATION")
            am.requestAudioFocus(focusChangeListener, AudioManager.STREAM_VOICE_CALL, AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
        }
    }

    private fun abandonAudioFocus() {
        val am = audioManager ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            focusRequest?.let { am.abandonAudioFocusRequest(it) }
            focusRequest = null
        } else {
            @Suppress("DEPRECATION")
            am.abandonAudioFocus(focusChangeListener)
        }
    }

    fun start(onPcmFrame: (ByteArray) -> Unit) {
        requestAudioFocus()
        registerBecomingNoisyReceiver()

        val minimum = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        recorder = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minimum, FRAME_BYTES * 4)
        )

        recorder?.let { recording ->
            if (AcousticEchoCanceler.isAvailable()) {
                AcousticEchoCanceler.create(recording.audioSessionId)?.enabled = true
            }
            if (NoiseSuppressor.isAvailable()) {
                NoiseSuppressor.create(recording.audioSessionId)?.enabled = true
            }
            recording.startRecording()
            running.set(true)
            worker = Thread {
                Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
                val frame = ByteArray(FRAME_BYTES)
                while (running.get()) {
                    val count = recording.read(frame, 0, frame.size, AudioRecord.READ_BLOCKING)
                    if (count == frame.size && !muted) {
                        onPcmFrame(frame.copyOf())
                    }
                }
            }.also { it.start() }
        }
    }

    fun play(pcm: ByteArray) {
        if (player == null) {
            val minimum = AudioTrack.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            )
            player = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setSampleRate(SAMPLE_RATE)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build()
                )
                .setBufferSizeInBytes(maxOf(minimum, FRAME_BYTES * 4))
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()
            player?.play()
        }
        player?.write(pcm, 0, pcm.size)
    }

    fun flush() {
        player?.pause()
        player?.flush()
        player?.play()
    }

    fun setMuted(value: Boolean) {
        muted = value
    }

    private fun registerBecomingNoisyReceiver() {
        if (context == null || becomingNoisyReceiver != null) return
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context?, intent: Intent?) {
                if (intent?.action == AudioManager.ACTION_AUDIO_BECOMING_NOISY) {
                    player?.pause()
                }
            }
        }
        becomingNoisyReceiver = receiver
        context.registerReceiver(receiver, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY))
    }

    private fun unregisterBecomingNoisyReceiver() {
        val receiver = becomingNoisyReceiver ?: return
        try {
            context?.unregisterReceiver(receiver)
        } catch (_: Exception) {}
        becomingNoisyReceiver = null
    }

    fun stop() {
        running.set(false)
        unregisterBecomingNoisyReceiver()
        abandonAudioFocus()

        recorder?.stop()
        recorder?.release()
        recorder = null
        worker = null

        player?.stop()
        player?.release()
        player = null
    }
}
