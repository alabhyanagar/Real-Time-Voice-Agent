const toggleBtn = document.getElementById('toggle-btn');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const agentState = document.getElementById('agent-state');
const glowEffect = document.getElementById('glow-effect');
const transcriptLog = document.getElementById('transcript-log');

let ws = null;
let audioContext = null;
let mediaStream = null;
let processorNode = null;
let captureSource = null;
let playbackQueue = null;
let isConnected = false;

// Audio playback queue variables
let sessionId = null;
// This is only a server-issued reconnect handle. User identity is never stored
// in or accepted from the client memory protocol.
let reconnectSessionId = window.localStorage.getItem('voice_agent_session_id') || null;
let turnId = crypto.randomUUID();
let clientSequence = 0;
let frameIndex = 0;
let generationId = null;
let negotiatedSampleRate = 16000;
let streamedResponse = '';
let currentAgentLogEntry = null;

toggleBtn.addEventListener('click', () => {
    if (!isConnected) {
        startSession();
    } else {
        stopSession();
    }
});

async function startSession() {
    try {
        // 1. Request microphone access without hardcoded sampleRate constraints
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                sampleRate: 16000
            }
        });

        // 2. Establish WebSocket connection directly targeting FastAPI backend on port 8000
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const hostname = window.location.hostname || 'localhost';
        const reconnectQuery = reconnectSessionId ? `?session_id=${encodeURIComponent(reconnectSessionId)}` : '';
        const wsUrl = `${wsProtocol}//${hostname}:8000/api/v1/ws/audio${reconnectQuery}`;

        console.log(`Connecting to WebSocket endpoint: ${wsUrl}`);
        ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
            isConnected = true;
            statusDot.classList.remove('bg-red-500');
            statusDot.classList.add('bg-emerald-500');
            statusText.textContent = 'Connected (Live)';
            setAgentVisualState('Listening');
            toggleBtn.textContent = 'End Session';
            toggleBtn.classList.remove('bg-cyan-600', 'hover:bg-cyan-500');
            toggleBtn.classList.add('bg-rose-600', 'hover:bg-rose-500', 'text-white');

        };

        ws.onmessage = async (event) => {
            if (typeof event.data === 'string') {
                try {
                    const data = JSON.parse(event.data);
                    handleServerMessage(data);
                } catch (e) {
                    console.error('Failed to parse server message:', e);
                }
            } else {
                // Binary incoming PCM audio chunk from TTS
                playAudioChunk(event.data);
            }
        };

        ws.onclose = (event) => {
            console.warn(`WebSocket closed: Code ${event.code}, Reason: ${event.reason}`);
            stopSession();
        };

        ws.onerror = (error) => {
            console.error('WebSocket connection error:', error);
            stopSession();
        };

    } catch (err) {
        console.error('Failed to start session:', err);
        alert(`Microphone or Connection Error: ${err.message || 'Backend unavailable'}`);
        stopSession();
    }
}

function startAudioCapture() {
    // Standardize AudioContext instantiation across browsers
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    audioContext = new AudioCtx({ sampleRate: 16000 });
    playbackQueue = new window.VoicePlaybackQueue(audioContext, negotiatedSampleRate);
    captureSource = audioContext.createMediaStreamSource(mediaStream);
    if (audioContext.audioWorklet) {
        audioContext.audioWorklet.addModule('/static/audio-worklet.js').then(() => {
            processorNode = new AudioWorkletNode(audioContext, 'voice-capture-processor', {
                processorOptions: { targetSampleRate: negotiatedSampleRate }
            });
            processorNode.port.onmessage = (event) => sendPcmFrame(event.data);
            captureSource.connect(processorNode);
            // Keep the node alive without routing microphone audio to speakers.
            const silentGain = audioContext.createGain();
            silentGain.gain.value = 0;
            processorNode.connect(silentGain);
            silentGain.connect(audioContext.destination);
        }).catch((error) => console.error('AudioWorklet unavailable:', error));
    }
}

function sendPcmFrame(buffer) {
    if (!isConnected || !ws || ws.readyState !== WebSocket.OPEN) return;
    if (ws.bufferedAmount > 256 * 1024) return;
    sendClientEvent('audio_frame', { byte_length: buffer.byteLength, frame_index: frameIndex++ });
    ws.send(buffer);
}

function setAgentVisualState(state) {
    const displayState = String(state).toLowerCase();
    const stateLabels = {
        idle: 'Idle', listening: 'Listening', processing: 'Processing',
        speaking: 'Speaking', cancelling: 'Cancelling', interrupted: 'Interrupted', error: 'Error'
    };
    state = stateLabels[displayState] || state;
    agentState.textContent = state;
    glowEffect.className = 'absolute inset-0 rounded-full transition-all duration-300';

    if (state === 'Listening') {
        glowEffect.classList.add('bg-cyan-500/20', 'opacity-100', 'animate-pulse');
    } else if (state === 'Processing') {
        glowEffect.classList.add('bg-amber-500/20', 'opacity-100', 'animate-ping');
    } else if (state === 'Speaking') {
        glowEffect.classList.add('bg-emerald-500/25', 'opacity-100', 'animate-pulse');
    } else if (state === 'Interrupted') {
        glowEffect.classList.add('bg-rose-500/30', 'opacity-100');
    } else {
        glowEffect.classList.add('opacity-0');
    }
}

function clearPlaceholder() {
    const placeholder = transcriptLog.querySelector('p.italic');
    if (placeholder) {
        placeholder.remove();
    }
}

function handleServerMessage(data) {
    if (data.type === 'ready') {
        sessionId = data.session_id;
        reconnectSessionId = data.session_id;
        window.localStorage.setItem('voice_agent_session_id', reconnectSessionId);
        generationId = data.generation_id || null;
        negotiatedSampleRate = data.audio_format.sample_rate_hz || 16000;
        sendClientEvent('hello', { client_name: 'web', client_version: '1.0.0' });
        sendClientEvent('audio_format', { format: data.audio_format });
        startAudioCapture();
    } else if (data.type === 'state') {
        if (generationId && data.generation_id && data.generation_id !== generationId) return;
        setAgentVisualState(data.state);
    } else if (data.type === 'transcript') {
        updateTranscript(data.text, data.is_final);
    } else if (data.type === 'response_text_delta') {
        updateAgentResponse(data.text, data.is_final);
    } else if (data.type === 'audio_flush') {
        if (data.generation_id) generationId = data.generation_id;
        setAgentVisualState('Interrupted');
        stopAllAudioPlayback();
    } else if (data.type === 'audio_end') {
        setAgentVisualState('Listening');
    } else if (data.type === 'error') {
        console.error('Server side pipeline error:', data.message);
    }
}

function sendClientEvent(type, payload = {}) {
    if (!ws || ws.readyState !== WebSocket.OPEN || !sessionId) return;
    ws.send(JSON.stringify({
        type,
        protocol_version: '1.0',
        session_id: sessionId,
        turn_id: turnId,
        sequence: clientSequence++,
        generation_id: generationId,
        ...payload
    }));
}

function updateTranscript(text, isFinal) {
    clearPlaceholder();
    let logEntry = document.getElementById('current-transcript');
    if (!logEntry) {
        logEntry = document.createElement('p');
        logEntry.id = 'current-transcript';
        logEntry.className = 'text-slate-200';
        transcriptLog.appendChild(logEntry);
    }
    logEntry.textContent = `You: ${text}`;

    if (isFinal) {
        logEntry.removeAttribute('id');
        logEntry.className = 'text-slate-300 font-normal';
    }
    transcriptLog.scrollTop = transcriptLog.scrollHeight;
}

function updateAgentResponse(text, isFinal) {
    clearPlaceholder();
    if (!currentAgentLogEntry) {
        currentAgentLogEntry = document.createElement('p');
        currentAgentLogEntry.className = 'text-cyan-400 font-medium pl-2 border-l-2 border-cyan-500/50';
        transcriptLog.appendChild(currentAgentLogEntry);
        streamedResponse = '';
    }
    if (isFinal) {
        streamedResponse = text;
    } else {
        streamedResponse += text;
    }
    currentAgentLogEntry.textContent = `Agent: ${streamedResponse}`;
    if (isFinal) currentAgentLogEntry = null;
    transcriptLog.scrollTop = transcriptLog.scrollHeight;
}

function stopAllAudioPlayback() {
    if (playbackQueue) playbackQueue.stop();
}

async function playAudioChunk(arrayBuffer) {
    if (!audioContext || !playbackQueue) return;

    setAgentVisualState('Speaking');

    try {
        playbackQueue.enqueue(arrayBuffer);

    } catch (e) {
        console.error('Error playing audio chunk:', e);
    }
}

function stopSession() {
    isConnected = false;
    stopAllAudioPlayback();

    if (ws) {
        try { ws.close(); } catch (e) { }
        ws = null;
    }
    sessionId = null;
    generationId = null;
    frameIndex = 0;
    clientSequence = 0;
    currentAgentLogEntry = null;
    streamedResponse = '';
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }
    if (audioContext) {
        try { audioContext.close(); } catch (e) { }
        audioContext = null;
    }
    captureSource = null;
    processorNode = null;
    playbackQueue = null;

    statusDot.classList.remove('bg-emerald-500');
    statusDot.classList.add('bg-red-500');
    statusText.textContent = 'Disconnected';
    setAgentVisualState('Idle');
    toggleBtn.textContent = 'Start Session';
    toggleBtn.classList.remove('bg-rose-600', 'hover:bg-rose-500', 'text-white');
    toggleBtn.classList.add('bg-cyan-600', 'hover:bg-cyan-500');
}
