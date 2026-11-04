class VoiceCaptureProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super();
        this.targetRate = (options.processorOptions || {}).targetSampleRate || 16000;
        this.buffer = [];
    }

    process(inputs) {
        const input = inputs[0] && inputs[0][0];
        if (!input || !input.length) return true;
        const ratio = sampleRate / this.targetRate;
        for (let i = 0; i < input.length; i++) this.buffer.push(input[i]);
        const outputLength = Math.floor(this.buffer.length / ratio);
        if (outputLength > 0) {
            const pcm = new Int16Array(outputLength);
            for (let i = 0; i < outputLength; i++) {
                const sourceIndex = Math.min(this.buffer.length - 1, Math.floor(i * ratio));
                const sample = Math.max(-1, Math.min(1, this.buffer[sourceIndex]));
                pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
            }
            this.buffer = this.buffer.slice(Math.floor(outputLength * ratio));
            this.port.postMessage(pcm.buffer, [pcm.buffer]);
        }
        return true;
    }
}
registerProcessor('voice-capture-processor', VoiceCaptureProcessor);
