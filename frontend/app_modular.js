import { AudioClient } from '/static/audio-client.js';
import { VoiceProtocol } from '/static/protocol.js';
import { SessionState } from '/static/session-state.js';
import { TelemetryPanel } from '/static/telemetry.js';

const $ = (id) => document.getElementById(id);
const toggleButton = $('toggle-btn');
const muteButton = $('mute-btn');
const deviceSelect = $('device-select');
const statusDot = $('status-dot');
const statusText = $('status-text');
const agentState = $('agent-state');
const glow = $('glow-effect');
const transcriptLog = $('transcript-log');
const toolLog = $('tool-log');
const citationLog = $('citation-log');
const errorBanner = $('error-banner');
const privacyIndicator = $('privacy-indicator');
const liveAnnouncement = $('live-announcement');
const telemetry = new TelemetryPanel($('telemetry-values'));
const state = new SessionState();
const audio = new AudioClient({ onFrame: sendAudioFrame, onSpeaking: () => setVisualState('speaking') });

let socket = null;
let protocol = null;
let reconnectTimer = null;
let reconnectAttempt = 0;
let currentTranscript = null;
let currentResponse = null;

toggleButton.addEventListener('click', () => state.connected ? disconnect(true) : connect());
muteButton?.addEventListener('click', () => {
    const muted = muteButton.getAttribute('aria-pressed') !== 'true';
    audio.setMuted(muted);
    muteButton.setAttribute('aria-pressed', String(muted));
    muteButton.textContent = muted ? 'Unmute microphone' : 'Mute microphone';
    privacyIndicator.textContent = muted ? 'Microphone muted' : 'Microphone active • audio streams to the assistant';
});
deviceSelect?.addEventListener('change', async () => {
    if (!state.connected) return;
    try { await audio.start(deviceSelect.value); } catch (error) { showError(`Could not switch microphone: ${error.message}`); }
});

async function populateDevices() {
    if (!deviceSelect) return;
    const devices = await audio.devices();
    deviceSelect.replaceChildren();
    devices.forEach((device, index) => {
        const option = document.createElement('option');
        option.value = device.deviceId;
        option.textContent = device.label || `Microphone ${index + 1}`;
        deviceSelect.appendChild(option);
    });
}

async function connect() {
    state.intentionalStop = false;
    clearError();
    setStatus('Connecting…', 'connecting');
    try {
        await audio.start(deviceSelect?.value || '');
        await populateDevices();
        const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const query = state.reconnectId ? `?session_id=${encodeURIComponent(state.reconnectId)}` : '';
        socket = new WebSocket(`${scheme}://${window.location.hostname || 'localhost'}:8000/api/v1/ws/audio${query}`);
        socket.binaryType = 'arraybuffer';
        socket.onopen = () => {
            state.connected = true;
            reconnectAttempt = 0;
            setStatus('Connected', 'connected');
            toggleButton.textContent = 'End session';
            toggleButton.classList.add('bg-rose-600');
            liveAnnouncement.textContent = 'Voice session connected';
            privacyIndicator.textContent = 'Microphone active • audio streams to the assistant';
        };
        socket.onmessage = (event) => {
            if (typeof event.data !== 'string') { audio.enqueue(event.data); return; }
            try { handleServerMessage(JSON.parse(event.data)); }
            catch (error) { showError(`Invalid server message: ${error.message}`); }
        };
        socket.onerror = () => showError('The voice connection encountered an error.');
        socket.onclose = () => {
            state.connected = false;
            audio.stop();
            privacyIndicator.textContent = 'Microphone inactive';
            if (!state.intentionalStop) scheduleReconnect();
            else setStatus('Disconnected', 'disconnected');
        };
    } catch (error) {
        audio.stop();
        showError(`Could not start the microphone: ${error.message}`);
        scheduleReconnect();
    }
}

function scheduleReconnect() {
    if (state.intentionalStop || reconnectTimer) return;
    const delay = Math.min(30_000, 1_000 * (2 ** reconnectAttempt++));
    setStatus(`Reconnecting in ${Math.ceil(delay / 1000)}s…`, 'connecting');
    reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, delay);
}

function disconnect(intentional = false) {
    state.intentionalStop = intentional;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    socket?.close();
    socket = null;
    state.connected = false;
    audio.stop();
    setStatus('Disconnected', 'disconnected');
    setVisualState('idle');
    toggleButton.textContent = 'Start session';
    toggleButton.classList.remove('bg-rose-600');
}

function sendAudioFrame(buffer, frameIndex) {
    if (!protocol || !socket || socket.readyState !== WebSocket.OPEN || socket.bufferedAmount > 256 * 1024) return;
    send('audio_frame', { byte_length: buffer.byteLength, frame_index: frameIndex });
    socket.send(buffer);
}

function send(type, payload = {}) {
    const event = protocol?.event(type, payload);
    if (event && socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(event));
}

function handleServerMessage(data) {
    if (data.type === 'ready') {
        protocol = new VoiceProtocol(data.session_id);
        protocol.ready(data);
        state.saveServerSession(data.session_id);
        send('hello', { client_name: 'web', client_version: '2.0.0', resume_token: state.reconnectId || undefined });
        send('audio_format', { format: data.audio_format });
        return;
    }
    if (protocol && !protocol.accepts(data)) return;
    if (data.type === 'state') { state.setState(data.state); setVisualState(data.state); return; }
    if (data.type === 'transcript') { renderTranscript(data.text, data.is_final); return; }
    if (data.type === 'response_text_delta') { renderResponse(data.text, data.is_final); return; }
    if (data.type === 'audio_flush') { protocol?.generationChanged(data.generation_id); audio.flush(); setVisualState('interrupted'); return; }
    if (data.type === 'tool_status') { renderToolStatus(data); return; }
    if (data.type === 'tool_confirmation') { showConfirmation(data); return; }
    if (data.type === 'ui_card' && data.card_type === 'citations') { renderCitations(data.payload?.citations || []); return; }
    if (data.type === 'telemetry') { telemetry.update(data.measurements); return; }
    if (data.type === 'error') {
        showError(data.message || 'The server reported an error.');
        if (data.retryable) scheduleReconnect();
    }
}

function setStatus(text, kind) {
    statusText.textContent = text;
    statusDot.className = `w-3 h-3 rounded-full ${kind === 'connected' ? 'bg-emerald-500' : kind === 'connecting' ? 'bg-amber-400 animate-pulse' : 'bg-red-500'}`;
}

function setVisualState(value) {
    const normalized = String(value || 'idle').toLowerCase();
    const labels = { idle: 'Idle', listening: 'Listening', processing: 'Processing', speaking: 'Speaking', cancelling: 'Cancelling', interrupted: 'Interrupted', error: 'Error' };
    agentState.textContent = labels[normalized] || normalized;
    liveAnnouncement.textContent = `Assistant state: ${labels[normalized] || normalized}`;
    glow.className = 'absolute inset-0 rounded-full transition-all duration-300';
    const colors = { listening: ['bg-cyan-500/20', 'opacity-100', 'animate-pulse'], processing: ['bg-amber-500/20', 'opacity-100', 'animate-ping'], speaking: ['bg-emerald-500/25', 'opacity-100', 'animate-pulse'], interrupted: ['bg-rose-500/30', 'opacity-100'] };
    glow.classList.add(...(colors[normalized] || ['opacity-0']));
}

function clearPlaceholder() { transcriptLog.querySelector('p.italic')?.remove(); }
function renderTranscript(text, final) {
    clearPlaceholder();
    currentTranscript ||= Object.assign(document.createElement('p'), { className: 'text-slate-200' });
    if (!currentTranscript.parentNode) transcriptLog.appendChild(currentTranscript);
    currentTranscript.textContent = `You: ${text}`;
    if (final) { currentTranscript.className = 'text-slate-300'; currentTranscript = null; }
    transcriptLog.scrollTop = transcriptLog.scrollHeight;
}
function renderResponse(text, final) {
    clearPlaceholder();
    currentResponse ||= Object.assign(document.createElement('p'), { className: 'text-cyan-400 font-medium pl-2 border-l-2 border-cyan-500/50' });
    if (!currentResponse.parentNode) transcriptLog.appendChild(currentResponse);
    currentResponse.dataset.text = final ? text : `${currentResponse.dataset.text || ''}${text}`;
    currentResponse.textContent = `Agent: ${currentResponse.dataset.text}`;
    if (final) currentResponse = null;
    transcriptLog.scrollTop = transcriptLog.scrollHeight;
}
function renderToolStatus(data) {
    if (!toolLog) return;
    const item = document.getElementById(`tool-${data.tool_name}`) || Object.assign(document.createElement('div'), { id: `tool-${data.tool_name}`, className: 'text-xs text-amber-200' });
    item.textContent = `${data.tool_name}: ${data.status}${data.detail ? ` — ${data.detail}` : ''}`;
    if (!item.parentNode) toolLog.appendChild(item);
}
function renderCitations(citations) {
    if (!citationLog) return;
    citationLog.replaceChildren(...citations.map((citation) => {
        const item = document.createElement('div');
        item.textContent = `[${citation.citation_id}] ${citation.filename || citation.source_id || 'Document'}`;
        return item;
    }));
}
function showConfirmation(data) {
    const approved = window.confirm(`${data.prompt}\n\nTool: ${data.tool_name}`);
    send('tool_confirmation_response', { confirmation_id: data.confirmation_id, approved });
}
function showError(message) { errorBanner.textContent = message; errorBanner.hidden = false; setVisualState('error'); liveAnnouncement.textContent = message; }
function clearError() { errorBanner.hidden = true; errorBanner.textContent = ''; telemetry.reset(); }
