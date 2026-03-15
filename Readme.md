# Silent Spiral

Silent Spiral is a privacy-first emotional reflection companion built with:

- FastAPI backend for NLP, pattern analysis, and agent orchestration
- Expo React Native mobile app for journaling, voice capture, and insights
- Multi-agent pipeline (Reflection, Pattern, Coach, Burst, Session)

This project is designed for self-awareness support and is not a medical product.

## Table Of Contents

- Overview
- User Journey (What Happens And Why)
- Architecture
- Features
- Tech Stack
- Project Structure
- Prerequisites
- Quick Start (Local)
- Environment Variables
- API Reference
- Testing
- Troubleshooting
- Safety Disclaimer

## Overview

Silent Spiral helps users notice emotional trends early through:

- Journal emotion analysis via GoEmotions NLP
- Pattern summaries and anomaly detection
- Reflection prompts and micro-challenge coaching
- Ephemeral listening sessions (Burst and Session flows)
- Voice transcription fallback for English and Hindi

## User Journey (What Happens And Why)

This section is written for end users. It explains what each feature is doing and why it exists.

### Step 1: User writes or speaks a journal entry

- What user does: Types thoughts or records voice.
- What system does: Converts voice to text when needed, then sends text for emotion analysis.
- Purpose: Reduce friction so users can express themselves even on low-energy days.

### Step 2: Emotion Analysis runs

- What user sees: Top emotions, intensity, and a simple emotional category.
- What system does: Uses the GoEmotions NLP model to score multiple emotions from the text.
- Purpose: Turn vague feelings into concrete emotional language users can understand.

### Step 3: Crisis language check happens

- What user sees: Supportive safety prompt when concerning language is detected.
- What system does: Flags high-risk text patterns with a `crisis_flag`.
- Purpose: Add a basic safety layer and encourage timely human support.

### Step 4: Reflection Agent responds

- What user sees: 2 gentle follow-up reflection questions.
- What system does: `POST /agent/reflect` generates open-ended prompts based on entry + emotions.
- Purpose: Help users go deeper than surface mood labels and build self-awareness.

### Step 5: Pattern Engine tracks trends over time

- What user sees: Dominant emotion trends, volatility, and pattern summaries.
- What system does: `POST /patterns/analyze` computes window stats and optional anomaly flags.
- Purpose: Show repeated emotional cycles, not just one-day snapshots.

### Step 6: Pattern Agent creates insight narrative

- What user sees: Human-readable insight card and headline.
- What system does: `POST /agent/pattern` turns numeric stats into understandable language.
- Purpose: Make trend data emotionally meaningful and easy to act on.

### Step 7: Coach Agent suggests one small action

- What user sees: 1-2 small suggestions and a one-day challenge (when needed).
- What system does: `POST /agent/coach` provides micro-habit guidance if anomaly exists.
- Purpose: Convert insight into realistic behavior change without pressure.

### Step 8: Burst and Session modes for immediate emotional release

- What user sees: Real-time acknowledgment and a warm closure message.
- What system does: - `POST /agent/burst/ack` and `POST /agent/burst/close` for short venting flow - `POST /agent/session/start`, `POST /agent/session/message`, `POST /agent/session/close` for private 10-minute guided conversation
- Purpose: Offer emotional containment during intense moments, without requiring long journaling.

### Step 8.1: 10-minute private listening (how to use)

- What user does: - Open the Check-in tab - Start private listening - Share freely for up to 10 minutes - End session or let timer complete
- What system does: - Starts an ephemeral timed session - Sends supportive listener replies each turn - Returns a gentle closing message at the end
- Purpose: Create a safe, time-bounded release space when emotions feel heavy.

### Step 9: Privacy and boundaries

- What user should know: - This app supports reflection, not diagnosis. - Burst and session routes are designed as ephemeral interactions. - Users should contact professional or emergency support in crisis situations.
- Purpose: Keep expectations clear, safe, and ethically grounded.

## Architecture

```text
Mobile App (Expo)
            |
            v
FastAPI Backend
      |- /analyze             -> NLP emotion scoring
      |- /patterns/analyze    -> trend stats + anomaly flag
      |- /agent/*             -> reflection/pattern/coach/burst/session agents
      |- /transcribe          -> audio transcription fallback
      |- /auth/*              -> basic email/password auth (SQLite)
```

## Features

- Emotion analysis from free-text journal entries
- Emotion category and crisis language flagging
- Pattern window analysis (dominant emotion, volatility, anomaly)
- Reflection questions tailored to recent emotional context
- Pattern narrative cards and coach micro-habits
- 10-minute private listening session APIs with no server-side session storage
- Audio-to-text fallback endpoint for mobile voice flows

## Tech Stack

### Mobile

- Expo SDK 54
- React Native 0.81
- Expo Router
- Axios
- TypeScript

### Backend

- FastAPI + Uvicorn
- Pydantic v2 + pydantic-settings
- Transformers + Torch (GoEmotions)
- LangChain + LangGraph
- Groq + Hugging Face APIs
- SQLite (current auth storage), SQLAlchemy/Alembic for evolving persistence

## Project Structure

```text
Hackrux/
      backend/
            app/
                  agents/
                  core/
                  models/
                  routes/
                  schemas/
                  services/
            tests/
            requirements.txt
            .env.example
      mobile/
            app/
            components/
            context/
            hooks/
            services/
            package.json
```

## Prerequisites

- Python 3.10+ (3.13 also works with current setup)
- Node.js 18+ and npm
- Git
- Optional API keys for full agent/transcription capability

## Quick Start (Local)

### 1) Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and add your keys as needed.

Start backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend docs:

- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

### 2) Mobile setup

```powershell
cd mobile
npm install
npm run start
```

If using a physical device, set API base URL in `mobile/.env.local`:

```bash
EXPO_PUBLIC_API_BASE_URL=http://<your-lan-ip>:8000
```

The app will auto-infer host when possible, but explicit env is recommended for device testing.

## Environment Variables

### Backend (`backend/.env`)

Key fields currently used by the backend:

- `DEBUG`
- `NLP_MODEL_NAME`
- `NLP_EMOTION_THRESHOLD`
- `NLP_TOP_K`
- `HUGGINGFACE_API_TOKEN`
- `GROQ_API_KEY`
- `GROQ_MODEL`
- `DATABASE_URL`

Notes:

- Missing `GROQ_API_KEY` does not crash startup; some agent routes return graceful fallback behavior.
- Keep `.env` out of version control.

## API Reference

### Core

- `GET /health` : service status and active model names
- `POST /analyze` : classify emotions from journal text
- `POST /patterns/analyze` : compute window stats and anomaly flag
- `POST /transcribe` : transcribe uploaded audio (multipart)

### Auth

- `POST /auth/register` : create user
- `POST /auth/login` : login user

### Agents

- `POST /agent/reflect` : reflection questions
- `POST /agent/pattern` : pattern narrative + highlight
- `POST /agent/coach` : micro-habit suggestions
- `POST /agent/burst/ack` : short in-session acknowledgment
- `POST /agent/burst/close` : burst closing message
- `POST /agent/session/start` : begin private session
- `POST /agent/session/message` : one message turn
- `POST /agent/session/close` : end private session

Use Swagger UI for full request and response schemas.

## Testing

From backend directory:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

Skip integration tests (faster local loop):

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -m "not integration"
```

## Troubleshooting

### Git Bash terminal crash on Windows

If VS Code shows:

`console device allocation failure - too many consoles in use, max consoles is 32`

Do this:

1. Close VS Code completely.
2. End all `bash.exe`, `git-bash.exe`, and `mintty.exe` processes in Task Manager.
3. Reopen VS Code and switch default terminal profile to PowerShell.
4. If needed, restart Windows once to clear orphaned console handles.

### First `/analyze` request is slow

The NLP model is warmed up at startup, but initial cold boots can still be heavy on lower-resource machines.

### Mobile cannot reach backend from phone

Set `EXPO_PUBLIC_API_BASE_URL` in `mobile/.env.local` to your machine LAN IP and ensure backend is listening on `0.0.0.0:8000`.

## Safety Disclaimer

Silent Spiral is not a medical device and does not provide diagnosis, treatment, or crisis intervention.
If someone is in immediate danger, contact local emergency or crisis services right away.