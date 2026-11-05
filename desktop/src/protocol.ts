/**
 * Shared TypeScript protocol models matching backend/protocol/messages.py
 * Protocol Version: 1.0
 */

export const PROTOCOL_VERSION = "1.0";

export interface AudioFormat {
  encoding: "pcm_s16le";
  sample_rate_hz: number;
  channels: number;
  sample_width_bytes: 2;
}

export const DEFAULT_AUDIO_FORMAT: AudioFormat = {
  encoding: "pcm_s16le",
  sample_rate_hz: 16000,
  channels: 1,
  sample_width_bytes: 2,
};

export interface EventEnvelope {
  type: string;
  protocol_version: string;
  session_id: string;
  turn_id: string;
  sequence: number;
  timestamp_ms: number;
  response_id?: string | null;
  generation_id?: string | null;
}

// Client -> Server Events
export interface HelloEvent extends EventEnvelope {
  type: "hello";
  client_name: string;
  client_version?: string | null;
  resume_token?: string | null;
}

export interface AudioFormatEvent extends EventEnvelope {
  type: "audio_format";
  format: AudioFormat;
}

export interface AudioFrameMetadata extends EventEnvelope {
  type: "audio_frame";
  byte_length: number;
  frame_index: number;
}

export interface CancelEvent extends EventEnvelope {
  type: "cancel";
  reason: "barge_in" | "user_cancel" | "disconnect" | "timeout";
}

export interface FlushEvent extends EventEnvelope {
  type: "flush";
  reason: "barge_in" | "cancel" | "new_turn";
}

export interface FlushAckEvent extends EventEnvelope {
  type: "flush_ack";
}

export interface ResumeEvent extends EventEnvelope {
  type: "resume";
  resume_token: string;
}

export interface PingEvent extends EventEnvelope {
  type: "ping";
}

export interface PongEvent extends EventEnvelope {
  type: "pong";
}

export interface ClientMetricsEvent extends EventEnvelope {
  type: "client_metrics";
  metrics: Record<string, number | string>;
}

export interface ToolConfirmationResponseEvent extends EventEnvelope {
  type: "tool_confirmation_response";
  confirmation_id: string;
  approved: boolean;
}

export type ClientEvent =
  | HelloEvent
  | AudioFormatEvent
  | AudioFrameMetadata
  | CancelEvent
  | FlushEvent
  | FlushAckEvent
  | ResumeEvent
  | PingEvent
  | ClientMetricsEvent
  | ToolConfirmationResponseEvent;

// Server -> Client Events
export interface ReadyEvent extends EventEnvelope {
  type: "ready";
  server_version: string;
  audio_format: AudioFormat;
}

export type AssistantState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "cancelling"
  | "error";

export interface StateEvent extends EventEnvelope {
  type: "state";
  state: AssistantState;
}

export interface TranscriptEvent extends EventEnvelope {
  type: "transcript";
  text: string;
  is_final: boolean;
}

export interface ResponseTextDeltaEvent extends EventEnvelope {
  type: "response_text_delta";
  text: string;
  is_final: boolean;
}

export interface AudioStartEvent extends EventEnvelope {
  type: "audio_start";
  mime_type: string;
}

export interface AudioEndEvent extends EventEnvelope {
  type: "audio_end";
}

export interface AudioFlushEvent extends EventEnvelope {
  type: "audio_flush";
  reason: string;
}

export interface ToolStatusEvent extends EventEnvelope {
  type: "tool_status";
  tool_name: string;
  status: "requested" | "running" | "completed" | "failed";
  detail?: string | null;
}

export interface ToolConfirmationEvent extends EventEnvelope {
  type: "tool_confirmation";
  tool_name: string;
  confirmation_id: string;
  prompt: string;
}

export interface UiCardEvent extends EventEnvelope {
  type: "ui_card";
  card_type: string;
  payload: Record<string, unknown>;
}

export interface ErrorEvent extends EventEnvelope {
  type: "error";
  code: string;
  message: string;
  retryable: boolean;
}

export interface TelemetryEvent extends EventEnvelope {
  type: "telemetry";
  measurements: Record<string, number>;
}

export type ServerEvent =
  | ReadyEvent
  | StateEvent
  | TranscriptEvent
  | ResponseTextDeltaEvent
  | AudioStartEvent
  | AudioEndEvent
  | AudioFlushEvent
  | ToolStatusEvent
  | ToolConfirmationEvent
  | UiCardEvent
  | ErrorEvent
  | TelemetryEvent
  | PongEvent;

export class ProtocolSessionState {
  sessionId: string | null = null;
  turnId: string = "turn-0";
  generationId: string | null = null;
  sequence: number = 0;

  reset(sessionId: string, generationId?: string | null) {
    this.sessionId = sessionId;
    this.generationId = generationId || null;
    this.sequence = 0;
  }

  nextSequence(): number {
    return this.sequence++;
  }
}

export function createEnvelope(
  session: ProtocolSessionState,
  type: string,
  extra: Record<string, unknown> = {}
): EventEnvelope {
  if (!session.sessionId) {
    throw new Error("Cannot create protocol event without active session_id");
  }
  return {
    type,
    protocol_version: PROTOCOL_VERSION,
    session_id: session.sessionId,
    turn_id: session.turnId,
    sequence: session.nextSequence(),
    timestamp_ms: Date.now(),
    generation_id: session.generationId,
    ...extra,
  };
}

export function parseServerEvent(rawJson: string | Record<string, unknown>): ServerEvent {
  const data = typeof rawJson === "string" ? JSON.parse(rawJson) : rawJson;
  if (!data || typeof data !== "object") {
    throw new Error("Invalid event payload: expected object");
  }
  if (data.protocol_version !== PROTOCOL_VERSION) {
    throw new Error(
      `Unsupported protocol version: ${data.protocol_version}, expected ${PROTOCOL_VERSION}`
    );
  }
  return data as ServerEvent;
}

