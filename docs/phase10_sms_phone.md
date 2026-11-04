# Phase 10 — SMS and outbound phone tools

Phase 10 adds the outbound communication surface from the canonical roadmap.

## Tools

| Tool | Behavior | Risk |
|---|---|---:|
| `sms_draft` | Prepare a recipient/message preview | medium |
| `sms_send` | Send an SMS through Twilio | high |
| `call_draft` | Prepare a call plan and script | medium |
| `call_place` | Place an outbound call through Twilio | high |
| `call_status` | Read assistant-controlled call status | low |
| `call_hangup` | End an assistant-controlled call | high |
| `call_transcript` | Retrieve permitted recordings/transcript availability | high |

All side-effecting operations are confirmation-gated by `ToolExecutor`, use
provider credentials only on the server, validate E.164 numbers, support rate
limits, and emit the existing requested/running/completed/failed status events.
Send/place operations are marked idempotent so callers can supply an
idempotency key and avoid duplicate provider actions.

## Scope boundary

Inbound answering, recording consent, autonomous call decisions, proactive
calling, and full transcription retention are intentionally deferred to a
separate advanced phase. `call_transcript` currently exposes recording metadata
and clearly reports when a transcription pipeline is not configured.

Configure the Twilio values in `.env` before enabling these tools. They remain
unavailable when credentials are missing.
