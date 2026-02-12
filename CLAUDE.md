# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BiliNote is an AI-powered video note-taking assistant that automatically extracts content from videos (Bilibili, YouTube, Douyin, Kuaishou, local files) and generates structured Markdown notes using LLMs. The application consists of a FastAPI backend and a React + Vite frontend, deployable via Docker or locally.

**Version:** v1.8.1
**Tech Stack:** FastAPI (Python 3.11) + React 19 + TypeScript + Tailwind CSS

## Development Commands

### Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
python main.py  # Starts on port 8483 by default
```

**Environment Variables:** Copy `.env.example` to `.env` and configure:
- `BACKEND_PORT`: Backend server port (default: 8483)
- `TRANSCRIBER_TYPE`: Audio transcription engine (fast-whisper/groq/mlx-whisper/bcut/kuaishou)
- `WHISPER_MODEL_SIZE`: Whisper model size (base/small/medium/large)

**Requirements:** FFmpeg must be installed and available in PATH.

### Frontend (React + Vite)

```bash
cd BiliNote_frontend
pnpm install
pnpm dev      # Development server (port 3015)
pnpm build    # Production build
pnpm lint     # ESLint check
pnpm preview  # Preview production build
```

**Vite Configuration:**
- Dev server: Port 3015 (configurable via `VITE_FRONTEND_PORT`)
- API proxy: `/api` → `http://localhost:8483`
- Path alias: `@/` → `./src/`

### Docker Deployment

```bash
# Standard deployment
docker-compose up --build

# GPU-accelerated (NVIDIA CUDA)
docker-compose -f docker-compose.gpu.yml up --build
```

**One-click startup scripts:**
- `start-local.bat` / `start-local.sh` - Local development
- `start-docker.bat` / `start-docker.sh` - Docker deployment

## Architecture

### Backend Architecture

The backend follows a **layered architecture** with clear separation of concerns:

```
API Layer (FastAPI Routers in app/routers/)
    ↓
Service Layer (Business Logic in app/services/)
    ├── NoteGenerator (core orchestration)
    ├── ProviderService
    └── ModelService
    ↓
Data Access Layer (DAOs in app/db/)
    ├── model_dao
    ├── provider_dao
    └── video_task_dao
    ↓
Database Layer (SQLAlchemy ORM)
    └── SQLite
```

**Key Design Patterns:**

1. **Factory Pattern:** `GPTFactory` (app/gpt/gpt_factory.py) creates LLM provider instances based on configuration
2. **Strategy Pattern:**
   - Downloaders (app/downloaders/base.py) - Platform-specific video/audio downloaders
   - Transcribers (app/transcriber/base.py) - Multiple transcription engine implementations
3. **DAO Pattern:** Database operations abstracted through data access objects

**Core Workflow (NoteGenerator):**

The `NoteGenerator` class (app/services/note.py) orchestrates the entire note generation pipeline:

1. **Download:** Platform-specific downloader extracts audio from video
2. **Transcribe:** Transcriber converts audio to text with timestamps
3. **Generate:** LLM generates structured notes from transcript
4. **Enhance:** Optionally inserts screenshots and timestamp links
5. **Persist:** Saves to database and file system

### Frontend Architecture

```
Pages (Route Components in src/pages/)
    ↓
Components (UI Components in src/components/)
    ↓
Hooks (Custom React Hooks in src/hooks/)
    ↓
Services (API Layer in src/services/)
    ↓
Store (Zustand State Management in src/store/)
```

**State Management (Zustand):**
- `configStore`: System configuration and settings
- `modelStore`: AI model selection and configuration
- `providerStore`: LLM provider management
- `taskStore`: Task tracking and history

**Key Components:**
- `HomePage`: Main application interface with video input and note display
- `SettingPage`: Configuration for models, providers, and transcription settings
- `src/services/note.ts`: API calls for note generation and task management

## Key Directories

### Backend Structure

- **app/routers/**: FastAPI endpoint definitions (note.py, provider.py, model.py, config.py)
- **app/services/**: Business logic layer
  - `note.py`: Core `NoteGenerator` class with main workflow
  - `constant.py`: Platform support mappings and constants
- **app/downloaders/**: Platform-specific video/audio downloaders
  - Each platform (Bilibili, YouTube, Douyin, Kuaishou) has its own downloader class
  - All inherit from `Downloader` base class
- **app/transcriber/**: Audio transcription implementations
  - `whisper.py`: Faster-Whisper (local, GPU-accelerated)
  - `groq.py`: Groq API transcriber
  - `mlx_whisper_transcriber.py`: Apple Silicon MLX Whisper
  - `bcut.py`, `kuaishou.py`: Platform-specific transcription services
- **app/gpt/**: LLM integration layer
  - `gpt_factory.py`: Factory for creating GPT provider instances
  - `universal_gpt.py`: Universal wrapper for OpenAI-compatible APIs
  - `anthropic_gpt.py`: Anthropic Claude integration
  - `prompt.py`, `prompt_builder.py`: Prompt templates and construction
- **app/db/**: Database layer
  - `models/`: SQLAlchemy models (Model, Provider, VideoTask)
  - `*_dao.py`: Data access objects for each model
- **app/models/**: Pydantic data models for validation and serialization

### Frontend Structure

- **src/pages/**: Route-level page components
  - `HomePage/`: Main application interface
  - `SettingPage/`: Configuration and settings
- **src/components/**: Reusable UI components
  - `ui/`: shadcn/ui components (Radix UI + Tailwind)
  - `Form/`: Form-related components
  - `Icons/`: Icon components
- **src/services/**: API service layer (Axios-based)
  - `note.ts`: Note generation and task APIs
  - `model.ts`: Model configuration APIs
  - `downloader.ts`: Downloader management APIs
- **src/store/**: Zustand state management stores
- **src/hooks/**: Custom React hooks for reusable logic
- **src/types/**: TypeScript type definitions

## Important Implementation Details

### Adding New Video Platform Support

To add a new video platform downloader:

1. Create a new downloader class in `backend/app/downloaders/` inheriting from `Downloader` base class
2. Implement required methods: `download()`, `get_video_info()`
3. Register the platform in `SUPPORT_PLATFORM_MAP` (app/services/constant.py)
4. Add platform detection logic in `NoteGenerator._get_downloader()` (app/services/note.py)

### Adding New LLM Provider

To add a new LLM provider:

1. Create a provider class in `backend/app/gpt/provider/` inheriting from `GPT` base class
2. Implement `generate()` method with streaming support
3. Register in `GPTFactory.create_gpt()` (app/gpt/gpt_factory.py)
4. Add provider configuration to database via `ProviderService`

### Adding New Transcription Engine

To add a new transcription engine:

1. Create a transcriber class in `backend/app/transcriber/` inheriting from `Transcriber` base class
2. Implement `transcribe()` method returning `TranscriptResult`
3. Register in `get_transcriber()` (app/transcriber/transcriber_provider.py)
4. Add configuration option to `.env` (`TRANSCRIBER_TYPE`)

### Database Migrations

The application uses SQLAlchemy with SQLite. Database initialization happens automatically on startup via `init_db()` in `backend/app/db/init_db.py`. Models are defined in `backend/app/db/models/`.

**Key Models:**
- `Model`: AI model configurations
- `Provider`: LLM provider configurations (OpenAI, Anthropic, DeepSeek, etc.)
- `VideoTask`: Task tracking and history

### Screenshot Generation

Screenshots are generated using FFmpeg via `generate_screenshot()` in `backend/app/utils/video_helper.py`. The function:
- Extracts frames at specified timestamps
- Saves to `static/screenshots/` directory
- Returns URLs for embedding in Markdown

### Prompt Engineering

Prompts are managed in `backend/app/gpt/prompt.py` and constructed via `PromptBuilder` (app/gpt/prompt_builder.py). The system supports:
- Multiple note styles (academic, conversational, bullet points, etc.)
- Custom format specifications (Markdown, structured sections)
- Video understanding with multimodal inputs
- Customizable extras and instructions

## Configuration Files

### Backend Configuration (.env)

Key environment variables:
- `BACKEND_PORT`: Backend server port (default: 8483)
- `BACKEND_HOST`: Server host (default: 0.0.0.0)
- `TRANSCRIBER_TYPE`: Transcription engine selection
- `WHISPER_MODEL_SIZE`: Whisper model size for local transcription
- `GROQ_TRANSCRIBER_MODEL`: Groq API model selection
- `FFMPEG_BIN_PATH`: Custom FFmpeg binary path (optional)
- `NOTE_OUTPUT_DIR`: Directory for note output files
- `IMAGE_BASE_URL`: Base URL for screenshot images

### Frontend Configuration

**Vite Config (vite.config.ts):**
- Base URL: `./` (relative paths for production)
- Dev server proxy: `/api` → backend
- Path alias: `@/` → `./src/`
- Plugins: React, Tailwind CSS Vite plugin

**TypeScript Config (tsconfig.json):**
- Target: ES2020
- Module: ESNext
- JSX: React-JSX
- Strict mode enabled

### Docker Configuration

**docker-compose.yml services:**
- `backend`: FastAPI service (internal port 8483)
- `frontend`: Nginx serving static files (internal port 80)
- `nginx`: Reverse proxy (external port 3015)

**Volume mounts:**
- `./videos:/app/videos` - Video storage
- `./data:/app/data` - Database and persistent data
- `./static:/app/static` - Screenshots and static files

## Testing and Debugging

### Backend Logging

Logging is configured in `backend/app/utils/logger.py`. The main entry point (`backend/main.py`) includes an `EndpointFilter` to suppress frequent polling logs (task status, model list, note history).

### Frontend Development

Use React DevTools and browser console for debugging. The application uses:
- `react-hot-toast` for user notifications
- `sonner` for toast notifications
- Axios interceptors for API error handling

### Common Issues

1. **FFmpeg not found:** Ensure FFmpeg is installed and in PATH
2. **CUDA errors:** Use CPU-only Docker image or install CUDA toolkit for GPU acceleration
3. **Port conflicts:** Change `BACKEND_PORT` and `FRONTEND_PORT` in `.env`
4. **Transcription failures:** Check `TRANSCRIBER_TYPE` configuration and model availability

## API Endpoints

Key backend endpoints (all prefixed with `/api`):

- `POST /api/note/generate` - Generate notes from video URL
- `GET /api/note/task_status/{task_id}` - Check task status
- `GET /api/note/note_history` - Retrieve note history
- `GET /api/model_list` - List available AI models
- `GET /api/provider_list` - List LLM providers
- `POST /api/provider/add` - Add new provider
- `POST /api/upload/video` - Upload local video file

## External Dependencies

**Critical Runtime Dependencies:**
- **FFmpeg:** Required for audio extraction and video processing
- **CUDA Toolkit:** Optional, for GPU-accelerated Whisper transcription
- **Redis:** Required if using Celery for task queuing (not currently active)

**Python Package Notes:**
- `faster-whisper`: Requires specific CUDA versions for GPU support
- `weasyprint`: Requires system libraries (Cairo, Pango) for PDF generation
- `yt-dlp`: Regularly updated for YouTube support

**Frontend Package Notes:**
- `pnpm` is the preferred package manager (uses `pnpm-lock.yaml`)
- `@tauri-apps/*`: Desktop app support (optional)
- Markdown rendering uses `react-markdown` with `remark-gfm`, `rehype-katex` plugins
