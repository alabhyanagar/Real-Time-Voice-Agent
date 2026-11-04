# Voice Assistant Architecture Blueprint

To transform your real-time voice agent into a personal daily assistant capable of scheduling meetings, sending emails, making calls, and running smoothly across desktop and mobile devices (similar to Google Gemini Live on Android), here is a complete architectural blueprint, technical guide, and deployment roadmap.

---

### Table of Contents
1. [How Tool Calling Works in a Real-Time Voice Pipeline](#1-how-tool-calling-works-in-a-real-time-voice-pipeline)
2. [Designing the Tool Registry Architecture](#2-designing-the-tool-registry-architecture)
3. [Connecting Real-World Workspace Capabilities](#3-connecting-real-world-workspace-capabilities)
4. [Desktop & Mobile Packaging Strategy](#4-desktop--mobile-packaging-strategy)
5. [Product Enhancements for a "Gemini-Grade" Experience](#5-product-enhancements-for-a-gemini-grade-experience)
6. [Step-by-Step Implementation Roadmap](#6-step-by-step-implementation-roadmap)

---

### 1. How Tool Calling Works in a Real-Time Voice Pipeline

In standard chatbots, an LLM calls a tool, waits for the result, and then prints the response. In a **real-time voice pipeline**, waiting 2–4 seconds for an API call (like Google Calendar) causes awkward dead silence.

To feel like Gemini or Siri, your voice pipeline must use an **asynchronous acknowledgment pattern**:

```text
[User Audio Chunk]
       │
   (Silero VAD) ──► (Deepgram/STT)
                            │
                     (Transcription)
                            │
                     (LLM Service)
                     ┌──────┴────────────────────────┐
                     ▼                               ▼
       [Intent: schedule_meeting]            [Spoken Acknowledgment]
                     │                               │
        (Tool Runner Async Worker)         (TTS: "Checking your calendar...")
                     │                               │
            [External Calendar API]            (Audio Stream to User)
                     │
         [Tool Result Returned]
                     │
           (LLM Formulates Result)
                     │
         (TTS: "You're all booked for tomorrow at 10 AM!")
```

#### Key Rules for Voice Tool Calling:
1. **Low Latency & Filler Phrases**: The system can trigger a quick conversational filler (e.g., *"Let me check that for you..."*) while the network request executes in the background.
2. **Streaming Function Arguments**: Modern streaming LLM APIs (Groq, OpenAI, Gemini) stream tool arguments token-by-token. Your backend accumulates the JSON chunk until `finish_reason == "tool_calls"`.
3. **Interruptibility / Barge-in**: If the user interrupts while a tool is being confirmed or executed (*"Wait, cancel that!"*), your pipeline cancels the execution task and resets the state.
4. **Safety & Confirmation Gate**: Destructive actions (e.g., *sending an email*, *deleting an event*, *placing an order*) must require explicit voice confirmation:
   - LLM: *"I drafted an email to Sarah asking for the project report. Would you like me to send it?"*
   - User: *"Yes, go ahead."*
   - Only then does `send_email` execute.

---

### 2. Designing the Tool Registry Architecture

Create a dedicated `tools/` package inside `/backend/services/tools/` to decouple tool definitions from the core pipeline logic.

#### Recommended Directory Structure:
```text
backend/
├── services/
│   ├── llm_service.py
│   ├── tools/
│   │   ├── __init__.py          # Tool registry & dispatcher
│   │   ├── schemas.py           # JSON schemas exposed to LLM
│   │   ├── calendar_service.py  # Google Calendar / Outlook
│   │   ├── email_service.py     # Gmail / SMTP
│   │   ├── telephony_service.py # Twilio / Android dialer intent
│   │   └── notes_service.py     # Quick notes, reminders, tasks
```

#### A. Tool Definition & Registry (`backend/services/tools/schemas.py`)
Define functions using standard JSON schema format compatible with Groq / OpenAI / Gemini:

```python
TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Schedule a new event or meeting on the user's primary calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Title or subject of the meeting/event"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "ISO 8601 start time, e.g. 2026-10-29T10:00:00Z"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes (default 30)",
                        "default": 30
                    },
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee email addresses"
                    }
                },
                "required": ["summary", "start_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to a recipient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Email address of recipient"},
                    "subject": {"type": "string", "description": "Subject of the email"},
                    "body": {"type": "string", "description": "Body text of the email"}
                },
                "required": ["recipient", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_phone_call",
            "description": "Initiate a phone call to a contact or phone number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name_or_number": {
                        "type": "string",
                        "description": "Name of contact or E.164 phone number"
                    }
                },
                "required": ["contact_name_or_number"]
            }
        }
    }
]
```

#### B. Tool Dispatcher (`backend/services/tools/__init__.py`)
```python
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class ToolExecutor:
    @staticmethod
    async def execute(tool_name: str, arguments: Dict[str, Any]) -> str:
        """Dispatches tool calls to their respective integration handlers."""
        logger.info(f"Executing tool {tool_name} with args: {arguments}")
        
        try:
            if tool_name == "create_calendar_event":
                # Call Google Calendar API
                return json.dumps({
                    "status": "success",
                    "event_id": "evt_987654",
                    "summary": arguments.get("summary"),
                    "scheduled_time": arguments.get("start_time")
                })
                
            elif tool_name == "send_email":
                # Call Gmail / SMTP API
                return json.dumps({
                    "status": "success",
                    "recipient": arguments.get("recipient"),
                    "message": "Email dispatched successfully."
                })
                
            elif tool_name == "trigger_phone_call":
                # Call Twilio or emit client event for native dialer
                return json.dumps({
                    "status": "initiated",
                    "target": arguments.get("contact_name_or_number")
                })
                
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
                
        except Exception as e:
            logger.error(f"Error executing {tool_name}: {e}")
            return json.dumps({"error": str(e)})
```

---

### 3. Connecting Real-World Workspace Capabilities

To perform real tasks on behalf of the user, integrate standard identity and productivity protocols:

| Capability | Best Integration Method | Details |
| :--- | :--- | :--- |
| **Calendar & Events** | **Google Calendar API** / **Microsoft Graph API** | Use OAuth 2.0 with offline access (`refresh_token`). Store tokens securely in SQLite/PostgreSQL per user. |
| **Emails** | **Gmail API** / **Resend** / **SendGrid** | Use Gmail API for personal accounts (read drafts, compose, send) or standard IMAP/SMTP for general mail. |
| **Phone Calls** | **Twilio Voice API** (Cloud) OR **Native Device Intent** (Mobile) | • **Mobile (Recommended)**: Emit a WebSocket event to the frontend client to invoke the native dialer (`tel:+123456789`).<br>• **Autonomous AI Agent calling businesses**: Use Twilio Voice + your voice pipeline to call restaurants/salons to book appointments. |
| **Contacts & Search** | **Google People API** | Resolves names ("call Mom", "email David") to phone numbers and email addresses. |
| **Reminders & Notes** | **SQLite / Notion / Apple Reminders** | Store quick voice memos and timed reminders with scheduled cron triggers. |

---

### 4. Desktop & Mobile Packaging Strategy

Your backend is currently built with **FastAPI, WebSockets, and Python**. For cross-platform deployment, **keep the FastAPI pipeline running on a central cloud server** (or locally on desktop) and build a lightweight client frontend that connects over secure WebSockets (`wss://`).

```text
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│     Mobile App (Android/iOS)    │       │     Desktop App (Win/Mac/Linux) │
│   Flutter or React Native App   │       │      Tauri (Rust + Web) App     │
│   • AudioRecorder & AudioPlayer │       │   • Global Hotkey (Alt+Space)   │
│   • Native Calls & Contacts     │       │   • Floating Spotlight UI       │
│   • Background Voice Service    │       │   • Minimal RAM (<20MB)         │
└────────────────┬────────────────┘       └────────────────┬────────────────┘
                 │                                         │
                 │      WebSocket Audio Stream (WSS)       │
                 └───────────────────┬─────────────────────┘
                                     ▼
                     ┌───────────────────────────────┐
                     │    FastAPI Central Backend    │
                     │  • Silero VAD (Voice Detect)  │
                     │  • Deepgram (Fast STT)        │
                     │  • Groq / Gemini (LLM + Tools)│
                     │  • Cartesia / ElevenLabs(TTS) │
                     │  • User OAuth & Tool Runners  │
                     └───────────────────────────────┘
```

#### A. Mobile Application (Android / iOS)
- **Framework Recommendation**: **Flutter** or **React Native (Expo)**.
- **Why**:
  - Full access to low-level microphone streams (`flutter_sound`, `record`, or `react-native-live-audio-stream`).
  - Native integration with device features:
    - **Phone Calling**: `url_launcher` triggers `tel:${phoneNumber}` directly.
    - **Contacts Access**: `contacts_service` to resolve contacts on-device before sending to the LLM.
    - **Background Service**: Can run a foreground service with a persistent mic notification (similar to Android Gemini).
    - **Lock Screen / Floating Widget**: Floating overlay bubble on Android so you can talk to the agent from any screen.

#### B. Desktop Application (Windows / macOS / Linux)
- **Framework Recommendation**: **Tauri (Rust + HTML/JS/CSS)**.
- **Why over Electron**:
  - Electron uses 150–250MB RAM; **Tauri uses under 25MB**.
  - Tauri starts instantly and has built-in support for:
    - **Global Shortcuts**: Press `Alt + Space` or `Ctrl + Shift + V` from anywhere to summon the voice assistant in a compact pill window (like Raycast or Spotlight).
    - **System Tray**: Sits quietly in the taskbar/menu bar ready to listen.
    - Reuses the existing HTML/Tailwind frontend with zero redesign needed.

---

### 5. Product Enhancements for a "Gemini-Grade" Experience

To make this a daily driver product that users love, implement these practical features:

1. **Multimodal Visual Canvas (Generative UI / Cards)**
   - When the user says *"Schedule a call with John at 3 PM"*, don't just speak.
   - Send a typed message over the WebSocket: `{"type": "ui_card", "card_type": "calendar_preview", "data": {...}}`.
   - The UI renders an interactive, beautifully formatted card showing the event time, attendees, and an "Undo" or "Open in Calendar" button.
2. **Persistent User Persona & Memory**
   - Use a fast database (SQLite / PostgreSQL) to save key user preferences:
     - *"I prefer 25-minute meetings instead of 30."*
     - *"My mom's phone number is +1-555-0192."*
     - *"Remind me to take medication every day at 9 AM."*
   - Inject these user memories dynamically into the LLM system prompt.
3. **Barge-in with Smooth Cancellation**
   - If the user interrupts while the assistant is speaking, immediately emit a `cancel` packet over WebSocket to cut off audio playback and stop LLM token generation.
4. **Proactive Notifications (Push & Voice Reminders)**
   - Instead of only reacting when spoken to, the server can push urgent reminders to the user's phone or desktop tray:
     - *"You have a meeting with the engineering team in 5 minutes."*

---

### 6. Step-by-Step Implementation Roadmap

#### Phase 1: Tool Execution Engine (Backend)
- [ ] Create `backend/services/tools/` with JSON schemas for `create_calendar_event`, `send_email`, and `trigger_call`.
- [ ] Update `llm_service.py` to pass the `tools` parameter to Groq / Gemini.
- [ ] Handle tool call responses in the async event loop and return formatted results back to the LLM.

#### Phase 2: Google Workspace OAuth Integration
- [ ] Set up a Google Cloud Console Project and enable **Google Calendar API** and **Gmail API**.
- [ ] Implement an OAuth2 flow (`/auth/login`, `/auth/callback`) to securely store `access_token` and `refresh_token` for the user.
- [ ] Connect the tool functions to live Google Calendar and Gmail endpoints.

#### Phase 3: Desktop Shell (Tauri)
- [ ] Initialize Tauri in the repository (`pnpm tauri init` or cargo tauri).
- [ ] Configure global hotkey (`Alt + Space`) and borderless floating overlay window.
- [ ] Connect the frontend to your FastAPI WebSocket endpoint.

#### Phase 4: Mobile App (Android / iOS)
- [ ] Build a Flutter or React Native client with WebSocket streaming.
- [ ] Hook device permissions: Microphone, Contacts, and Phone Dialer.
- [ ] Add Android floating overlay bubble for quick access.

#### Phase 5: Production Cloud Deployment
- [ ] Deploy FastAPI to a cloud provider with WebSocket support (GCP Cloud Run, AWS EC2, or Fly.io).
- [ ] Enforce SSL/TLS (`wss://`) for microphone permissions on mobile browsers and native apps.