# VentureScope Backend

AI-powered career guidance platform built with FastAPI. Helps students and professionals with career discovery, resume generation, learning roadmaps, job matching, and a personalized AI chat assistant.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI 0.115 (Python 3.12) |
| Database | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.x (async) |
| Migrations | Alembic |
| Task Queue | Celery 5.x |
| Cache / OTP Store | Upstash Redis (HTTP) |
| Celery Broker | Upstash Redis (rediss://) |
| AI / LLM | OpenAI (gpt-4o-mini), LangChain, LangGraph |
| Embeddings | HuggingFace `all-MiniLM-L6-v2` (384 dims) |
| File Storage | Supabase Storage (S3-compatible) |
| Email | Mailgun |
| Auth | JWT + bcrypt + TOTP MFA |
| OAuth | Google + GitHub |
| Deployment | Azure Container Apps via GitHub Actions |

---

## Features

- **Auth** — Register, login, email OTP verification, password reset, Google/GitHub OAuth, TOTP MFA, re-authentication, JWT revocation
- **User Profile** — Profile management, skills, work experience, CV upload (S3), profile picture, GitHub sync
- **AI Chat** — WebSocket streaming RAG chatbot powered by LangGraph ReAct agent + web search
- **Transcripts** — Academic transcript upload with version history, GPA validation, AI profile summary
- **Learning Roadmaps** — AI-generated week-by-week roadmaps with real resource URLs, step progress tracking, completion percentage
- **Resume Generation** — AI-generated resumes from user knowledge base (transcript, CV, GitHub, profile)
- **Jobs** — Trending careers, in-demand skills, job market stats
- **Notifications** — In-app notification system
- **Admin** — User management (list, update, soft/hard delete, reactivate)
- **Background Tasks** — Async embedding generation via Celery workers

---

## Project Structure

```
Backend/
├── app/
│   ├── api/              # Route handlers (14 modules)
│   ├── core/             # Config, database, security
│   ├── models/           # SQLAlchemy ORM models (13 models)
│   ├── repositories/     # Data access layer
│   ├── schemas/          # Pydantic request/response models
│   ├── services/         # Business logic
│   ├── tasks/            # Celery background tasks
│   ├── templates/email/  # Email templates
│   └── main.py
├── alembic/              # Database migrations
├── tests/                # Unit, integration, e2e tests
├── scripts/              # Dev/ops scripts
├── Dockerfile            # API image
├── Dockerfile.worker     # Celery worker image
├── docker-compose.yml    # Local dev stack
├── docker-compose.prod.yml
└── requirements.txt
```

---

## API Endpoints

| Prefix | Description |
|---|---|
| `POST /api/auth/register` | Register with email/password |
| `POST /api/auth/login` | Login, returns JWT |
| `POST /api/auth/verify-email` | Verify OTP |
| `POST /api/auth/forgot-password` | Request password reset |
| `POST /api/auth/reset-password` | Reset password with OTP |
| `POST /api/auth/logout` | Revoke JWT |
| `GET  /api/auth/oauth/google/login` | Google OAuth URL |
| `GET  /api/auth/oauth/github/login` | GitHub OAuth URL |
| `POST /api/auth/mfa/enroll` | Start TOTP enrollment |
| `POST /api/auth/mfa/verify` | Verify TOTP code |
| `GET  /api/users/me` | Get own profile |
| `PATCH /api/users/me` | Update profile |
| `POST /api/users/me/cv` | Upload CV |
| `GET  /api/users/me/github/sync` | Sync GitHub profile |
| `POST /api/users/me/experiences` | Add work experience |
| `GET  /api/transcripts/` | List transcript versions |
| `POST /api/transcripts/` | Upload transcript |
| `GET  /api/chat/sessions` | List chat sessions |
| `WS   /api/chat/ws/{session_id}` | Streaming chat WebSocket |
| `POST /api/roadmaps/generate` | Generate learning roadmap |
| `GET  /api/roadmaps/` | List roadmaps with progress % |
| `PATCH /api/roadmaps/steps/{id}/progress` | Update step progress |
| `POST /api/resume/generate` | Generate AI resume |
| `GET  /api/jobs/trending` | Trending careers |
| `GET  /api/jobs/in-demand-skills` | In-demand skills |
| `GET  /api/notifications/` | List notifications |
| `GET  /api/health` | Health check |

Full interactive docs at `http://localhost:8000/docs` (Swagger UI).

---

## Local Development

### Prerequisites

- Python 3.12
- PostgreSQL 16 with pgvector extension
- Redis (local, for Celery worker)

### 1. Clone and install

```bash
git clone https://github.com/VentureScope/Backend.git
cd Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in all required values (see Environment Variables section below)
```

### 3. Run database migrations

```bash
alembic upgrade head
```

### 4. Start the API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs

### 5. Start the Celery worker (local)

Upstash Redis wire-protocol is blocked by WSL2 networking. Use your local Redis for development:

```bash
CELERY_BROKER_URL=redis://localhost:6379 \
CELERY_RESULT_BACKEND=redis://localhost:6379 \
celery -A app.celery_config.celery_app worker --loglevel=info
```

In production (Azure) the worker uses the Upstash `rediss://` URL from `.env` automatically.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | JWT signing key — generate with `openssl rand -hex 32` |
| `UPSTASH_REDIS_URL` | Upstash REST URL (`https://...upstash.io`) |
| `UPSTASH_REDIS_TOKEN` | Upstash REST token |
| `CELERY_BROKER_URL` | Upstash wire-protocol URL (`rediss://...`) |
| `CELERY_RESULT_BACKEND` | Same as `CELERY_BROKER_URL` |
| `EMBEDDING_PROVIDER` | `hf` for HuggingFace or `hosted` for OpenAI-compatible |
| `HF_TOKEN` | HuggingFace API token (if `EMBEDDING_PROVIDER=hf`) |
| `EMBEDDING_MODEL_NAME` | e.g. `sentence-transformers/all-MiniLM-L6-v2` |
| `EMBEDDING_DIMENSIONS` | Must match the model output (e.g. `384`) |
| `END_POINT` | LLM API base URL |
| `HOSTED_LLM_TOKEN` | LLM API token |
| `CHAT_MODEL_NAME` | LLM model name e.g. `gpt-4o-mini` |
| `AWS_ACCESS_KEY_ID` | Supabase Storage access key |
| `AWS_SECRET_ACCESS_KEY` | Supabase Storage secret |
| `S3_BUCKET_NAME` | Storage bucket name |
| `S3_ENDPOINT_URL` | Supabase Storage endpoint |
| `MAILGUN_API_KEY` | Mailgun API key |
| `MAILGUN_DOMAIN` | Mailgun sending domain |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret |
| `SERPER_API_KEY` | Serper API key for web search |

---

## Background Tasks

Two Celery tasks run in the background:

| Task | Triggered by | What it does |
|---|---|---|
| `generate_user_profile_embedding` | Register, profile update, CV upload, skills update | Builds user document text → generates vector embedding → stores in `users.embedding` |
| `generate_knowledge_embedding` | Transcript upload, CV upload, GitHub sync | Embeds individual knowledge chunks → stores in `user_knowledge.embedding` |
| `batch_generate_knowledge_embeddings` | Transcript re-upload | Re-embeds all knowledge chunks for a source type |

These embeddings power semantic job matching and the RAG chatbot retrieval.

---

## Database Models

| Model | Table | Purpose |
|---|---|---|
| `User` | `users` | Core user identity, skills, embedding |
| `OAuthAccount` | `oauth_accounts` | Google/GitHub OAuth connections |
| `TokenBlocklist` | `token_blocklist` | JWT revocation store |
| `AcademicTranscript` | `academic_transcripts` | E-student transcript versions |
| `TranscriptConfig` | `transcript_configs` | User GPA scale config |
| `UserKnowledge` | `user_knowledge` | Vector-searchable RAG knowledge chunks |
| `Experience` | `experiences` | Work experience entries |
| `GitHubSyncSnapshot` | `github_sync_snapshots` | Cached GitHub profile data |
| `Job` | `jobs` | Job listings with embeddings |
| `LearningRoadmap` | `learning_roadmaps` | AI-generated learning plans |
| `LearningRoadmapStep` | `learning_roadmap_steps` | Weekly steps |
| `LearningRoadmapStepResource` | `learning_roadmap_step_resources` | Resources per step |
| `LearningRoadmapProgress` | `learning_roadmap_progress` | User progress per step |
| `Resume` | `resumes` | AI-generated resume data |
| `ChatSession` | `chat_sessions` | Conversation threads |
| `ChatMessage` | `chat_messages` | Individual messages |
| `Notification` | `notifications` | In-app notifications |

---

## Authentication & Security

- **JWT** — HS256 signed tokens with `jti` UUID for per-token revocation via `token_blocklist`
- **AAL2** — Sensitive routes (password change, account deletion, MFA management) require re-authentication or TOTP verification
- **OTP** — 6-digit codes stored in Upstash Redis with TTL, rate-limited (60s cooldown, max 3/hour)
- **OAuth CSRF** — State parameter signed with HMAC-SHA256 + timestamp expiry
- **Timing attacks** — Constant-time comparison on passwords and OTP codes throughout
- **bcrypt** — Password hashing via passlib

---

## Deployment

Deploys automatically to **Azure Container Apps** on every push to `master-v2` via GitHub Actions.

### What the pipeline does

1. Builds and pushes the **API image** (`Dockerfile`) to GitHub Container Registry
2. Builds and pushes the **Worker image** (`Dockerfile.worker`) to GitHub Container Registry
3. Updates the `venturescope` Container App with the new API image
4. Updates the `backgroundworker` Container App with the new worker image

### Required GitHub Secrets

| Secret | Value |
|---|---|
| `AZURE_CREDENTIALS` | Azure service principal JSON |
| `AZURE_RG` | Azure resource group name |

### Update environment variables on Azure

```bash
# API container
az containerapp update \
  --name venturescope \
  --resource-group <AZURE_RG> \
  --set-env-vars KEY="value" KEY2="value2"

# Worker container
az containerapp update \
  --name backgroundworker \
  --resource-group <AZURE_RG> \
  --set-env-vars KEY="value" KEY2="value2"
```

---

## Testing

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# With coverage report
pytest tests/ --cov=app --cov-report=html
```

Test structure:
```
tests/
├── conftest.py          # Fixtures: engine, db session, client, users
├── unit/                # Service and repository unit tests (9 modules)
├── integration/         # API endpoint + migration tests (6 modules)
└── e2e/                 # Full user journey tests (1 module)
```

---

## Architecture

```
HTTP Request
  → FastAPI Router
    → get_current_user (JWT → blocklist → user fetch)
      → [require_aal2 if sensitive]
        → Route Handler
          → Service Layer (business logic)
            → Repository Layer (SQLAlchemy async)
              → PostgreSQL
          → Celery task dispatched (embeddings)
          → Pydantic response serialization
```

WebSocket Chat flow:
```
WS Connect (?token=JWT)
  → Auth check
    → Receive message
      → Embed query → vector search UserKnowledge
      → Load message history
      → LangGraph ReAct agent (may call web search tool)
        → Stream tokens → WS send_json
      → Save assistant message
      → Create notification
```
