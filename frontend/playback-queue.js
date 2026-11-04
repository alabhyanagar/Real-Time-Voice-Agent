class VoicePlaybackQueue {
    constructor(context, sampleRate = 16000, maxChunks = 64) {
        this.context = context;
        this.sampleRate = sampleRate;
        this.maxChunks = maxChunks;
        this.sources = new Set();
        this.nextTime = context.currentTime;
    }

    stop() {
        for (const source of this.sources) { try { source.stop(); } catch (_) {} }
        this.sources.clear();
        this.nextTime = this.context.currentTime;
    }

    enqueue(arrayBuffer) {
        if (this.sources.size >= this.maxChunks) return;
        const pcm = new Int16Array(arrayBuffer);
        const buffer = this.context.createBuffer(1, pcm.length, this.sampleRate);
        const channel = buffer.getChannelData(0);
        for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768;
        const source = this.context.createBufferSource();
        source.buffer = buffer;
        source.connect(this.context.destination);
        source.onended = () => this.sources.delete(source);
        this.nextTime = Math.max(this.nextTime, this.context.currentTime);
        source.start(this.nextTime);
        this.nextTime += buffer.duration;
        this.sources.add(source);
    }
}
window.VoicePlaybackQueue = VoicePlaybackQueue;
