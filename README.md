# 🎙️ NovaVoice AI Copilot

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Poetry](https://img.shields.io/badge/Packaging-Poetry-60A5FA.svg?logo=poetry&logoColor=white)](https://python-poetry.org/)
[![React 19](https://img.shields.io/badge/React-19.0-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![Vite 8](https://img.shields.io/badge/Vite-8.2-646CFF.svg?logo=vite&logoColor=white)](https://vitejs.dev/)
[![SQLite WAL](https://img.shields.io/badge/Database-SQLite_WAL-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/wal.html)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**NovaVoice AI Copilot** is a production-grade, full-duplex conversational voice application powered by **Vocode**, **FastAPI**, **WebSockets**, and a modern **React 19** frontend.

It delivers real-time, low-latency streaming dialogue (~150ms speech-to-text, sub-300ms time-to-first-token, streaming linear PCM audio) alongside multi-tenant authentication, dynamic LLM function calling, and persistent conversation history.

---

## 🌟 Key Features & Architectural Highlights

### ⚡ 1. Full-Duplex Audio & Voice Pipeline
- **Real-Time Streaming**: Browser microphone audio resampled and streamed as 16kHz Linear PCM over WebSockets (`ws://host:port/conversation`).
- **Sub-200ms STT**: Streaming transcription via **Deepgram Nova-2** with Neural Voice Activity Detection (VAD).
- **Multi-Engine Speech Synthesis**: High-fidelity TTS streaming via **ElevenLabs Turbo v2.5**, **Cartesia Sonic**, **Edge-TTS**, **StreamElements**, and **Azure Cognitive Speech**.
- **Dual-Model LLM Intelligence**: Supports **Google Gemini** (`gemini-1.5-flash`, `gemini-2.0`, `gemini-3.5-flash`) via modern OpenAI `tools` schema translation, as well as native **OpenAI** (`gpt-4o`, `gpt-4o-mini`) and **Groq**.

### 🛠️ 2. Real-Time Action Engine & Function Calling
- Out-of-band JSON schema tool execution directly integrated into Vocode agents.
- **Calendar & Appointments**: `check_availability` queries real-time open slots; `book_appointment` schedules slots and persists reservations in SQLite.
- **Business Knowledge**: `get_company_info` retrieves dynamic clinic/office data.

### 🔐 3. User Tenancy & Token Rotation
- **Salted Password Hashing**: PBKDF2-HMAC-SHA256 with 16-byte random salts and constant-time verification.
- **Double-Token Rotation**:
  - **Short-Lived Access Tokens** (15 mins) for stateless API and WebSocket authorization.
  - **Stateful Refresh Tokens** (7 days) with single-use rotation and **Reuse / Theft Detection** that automatically invalidates the entire token family if compromised.
- **Transparent Client Interceptor**: Frontend automatically intercepts `401 Unauthorized`, rotates credentials silently, and replays failed requests without user disruption.
- **Data Isolation**: User API credentials (OpenAI, Gemini, Deepgram, ElevenLabs) are stored per-user, isolating settings and custom agents.

### 🎭 4. Agent Persona Studio & Customization
- **Built-in Personas**: Executive Concierge (`Nova`), Medical Receptionist (`Chloe`), Technical Interviewer (`Alex`), School Office (`Mary`).
- **Custom Agent Builder**: Create custom personas with tailored system prompts, custom voices, idle nudges, and closure protocols.

### 💾 5. Enterprise Persistence Tier
- **SQLite with WAL Mode**: Write-Ahead Logging (`PRAGMA journal_mode=WAL`) enables concurrent reader threads alongside fast writes.
- **Self-Bootstrapping Migrations**: Automated schema synchronization detects missing columns on startup and applies non-destructive `ALTER TABLE` operations.
- **Complete Session History**: Captures turn-by-turn transcripts, speaker attribution, latency metrics, and booked appointments.

---

## 🏗️ Repository Layout

```text
voice-ai-agent/
├── backend/
│   ├── actions/               # Real-time action engine (check_availability, book_appointment)
│   ├── db/                    # SQLite WAL database, models, migrations & repository tier
│   ├── agent_factory.py       # Resilient LLM agent, action routing & Gemini tools adapter
│   ├── agent_registry.py      # Built-in and user-scoped custom persona registry
│   ├── app.py                 # FastAPI application, auth routers & WebSocket audio streaming
│   ├── auth.py                # PBKDF2 password hashing & token rotation lifecycle
│   └── config.py              # Pydantic v2 settings & environment configuration
├── frontend_react/            # React 19 + Vite 8 Dark Glassmorphic Web App
│   ├── src/
│   │   ├── api/client.js      # Unified API client with automatic 401 token refresh interceptor
│   │   ├── context/AuthContext.jsx # Reactive authentication state provider
│   │   ├── components/        # VoiceOrb, VisualizerCanvas, AuthModal, CallHistoryModal, SettingsModal
│   │   └── hooks/useVocodeVoice.js # AudioContext capture & WebSocket PCM streaming hook
├── vocode-core/               # Local Vocode core SDK engine (editable package)
├── pyproject.toml             # Poetry project configuration & dependency lock
├── requirements.txt           # Pinned production requirements manifest
└── run.py                     # Unified backend CLI entrypoint
```

---

## 🚀 Quickstart Guide

### Prerequisites
- **Python**: `3.11.x`
- **Poetry**: `>=1.8.0` ([Install Poetry](https://python-poetry.org/docs/#installation))
- **Node.js**: `>=18.0.0` and `npm`

---

### Step 1: Clone & Configure Environment

```bash
git clone https://github.com/Ameyak17901/voice-ai-agent.git
cd voice-ai-agent
```

Copy the environment template and populate your API credentials:

```bash
cp .env.example .env
```

Key environment variables in `.env`:
```ini
# Server
HOST=127.0.0.1
PORT=8000
DEBUG=true

# STT (Deepgram Nova-2)
DEEPGRAM_API_KEY=your_deepgram_api_key

# LLM (Google Gemini or OpenAI)
GEMINI_API_KEY=your_gemini_api_key
OPENAI_MODEL_NAME=gemini-3.5-flash

# TTS (ElevenLabs, Cartesia, or Edge-TTS)
TTS_PROVIDER=eleven_labs
ELEVEN_LABS_API_KEY=your_elevenlabs_api_key

# Auth Secret
JWT_SECRET_KEY=change_this_to_a_secure_random_string_in_production
```

---

### Step 2: Backend Setup (Poetry)

Configure Poetry to create an in-project virtual environment (`.venv`) and install all dependencies:

```bash
poetry config virtualenvs.in-project true --local
poetry install
```

Verify backend installation:
```bash
poetry run python run.py --test
```

Start the backend server:
```bash
poetry run python run.py --reload
```
The FastAPI server will start at `http://127.0.0.1:8000`.  
- **Interactive OpenAPI Docs**: `http://127.0.0.1:8000/docs`  
- **Streaming WebSocket**: `ws://127.0.0.1:8000/conversation`

---

### Step 3: Frontend Setup (React + Vite)

In a new terminal window, navigate to the frontend directory:

```bash
cd frontend_react
npm install
npm run dev
```

The frontend interface will open at `http://localhost:5173`.

---

## 🧪 Testing & Verification

The project includes a comprehensive, isolated test suite under `tests/` powered by `pytest` and `pytest-asyncio`. Tests run against an isolated SQLite test database with zero side effects on the development database.

```bash
# 1. Run all automated test suites with verbose output
poetry run pytest -v

# 2. Run specific test suites
poetry run pytest tests/test_auth_isolation.py -v
poetry run pytest tests/test_token_rotation.py -v
poetry run pytest tests/test_gemini_tools.py -v

# 3. Verify server initialization and route registration
poetry run python run.py --test
```


---

## 🛡️ Security & Privacy Notice

- **Database Files**: SQLite database files (`*.db`, `*.db-wal`, `*.db-shm`) are excluded via `.gitignore` to prevent leaking private credentials or conversation transcripts.
- **Secret Isolation**: User API keys configured in the settings drawer are encrypted/persisted per user in SQLite and never logged or exposed to other tenants.
- **Token Security**: Tokens are signed with HMAC-SHA256 and rotated on every single-use refresh token exchange.
