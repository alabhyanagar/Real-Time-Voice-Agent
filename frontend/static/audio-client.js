export class AudioClient {
    constructor({ onFrame, onSpeaking } = {}) {
        this.onFrame = onFrame;
        this.onSpeaking = onSpeaking;
        this.context = null;
        this.stream = null;
        this.source = null;
        this.processor = null;
        this.playback = null;
        this.frameIndex = 0;
        this.deviceId = '';
        this.muted = false;
    }

    async devices() {
        const devices = await navigator.mediaDevices.enumerateDevices();
        return devices.filter((device) => device.kind === 'audioinput');
    }

    async start(deviceId = '') {
        this.stop();
        this.deviceId = deviceId || '';
        this.stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                sampleRate: 16000,
                ...(this.deviceId ? { deviceId: { exact: this.deviceId } } : {}),
            },
        });
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        this.context = new AudioContextClass({ sampleRate: 16000 });
        this.playback = new window.VoicePlaybackQueue(this.context, 16000);
        this.source = this.context.createMediaStreamSource(this.stream);
        await this.context.audioWorklet.addModule('/static/audio-worklet.js');
        this.processor = new AudioWorkletNode(this.context, 'voice-capture-processor', {
            processorOptions: { targetSampleRate: 16000 },
        });
        this.processor.port.onmessage = (event) => {
            if (!this.onFrame || this.muted) return;
            this.onFrame(event.data, this.frameIndex++);
        };
        this.source.connect(this.processor);
        const silentGain = this.context.createGain();
        silentGain.gain.value = 0;
        this.processor.connect(silentGain);
        silentGain.connect(this.context.destination);
    }

    enqueue(buffer) {
        if (!this.playback) return;
        this.onSpeaking?.();
        this.playback.enqueue(buffer);
    }

    flush() {
        this.playback?.stop();
    }

    setMuted(value) {
        this.muted = value;
        this.stream?.getAudioTracks().forEach((track) => { track.enabled = !value; });
    }

    stop() {
        this.flush();
        this.processor?.disconnect();
        this.source?.disconnect();
        this.stream?.getTracks().forEach((track) => track.stop());
        this.context?.close();
        this.processor = null;
        this.source = null;
        this.stream = null;
        this.context = null;
        this.playback = null;
        this.frameIndex = 0;
    }
}
