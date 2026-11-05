export class VoiceProtocol {
    constructor(sessionId = null) {
        this.sessionId = sessionId;
        this.turnId = crypto.randomUUID();
        this.sequence = 0;
        this.generationId = null;
    }

    ready(event) {
        this.sessionId = event.session_id;
        this.generationId = event.generation_id || null;
        this.sequence = 0;
    }

    accepts(event) {
        return !this.generationId || !event.generation_id || event.generation_id === this.generationId;
    }

    generationChanged(generationId) {
        if (generationId) this.generationId = generationId;
    }

    event(type, payload = {}) {
        if (!this.sessionId) return null;
        return {
            type,
            protocol_version: '1.0',
            session_id: this.sessionId,
            turn_id: this.turnId,
            sequence: this.sequence++,
            generation_id: this.generationId,
            ...payload,
        };
    }
}
