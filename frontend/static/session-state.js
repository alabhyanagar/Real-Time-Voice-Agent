export class SessionState {
    constructor() {
        this.reconnectId = window.localStorage.getItem('voice_agent_session_id');
        this.intentionalStop = false;
        this.connected = false;
        this.state = 'idle';
    }

    saveServerSession(sessionId) {
        this.reconnectId = sessionId;
        window.localStorage.setItem('voice_agent_session_id', sessionId);
    }

    setState(state) {
        this.state = String(state || 'idle').toLowerCase();
    }

    clearReconnectHandle() {
        this.reconnectId = null;
        window.localStorage.removeItem('voice_agent_session_id');
    }
}
