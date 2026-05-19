# VentureScope Backend

FastAPI backend for the AI-powered career guidance platform.

---

## Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115 + Uvicorn (ASGI) |
| Database | PostgreSQL 16 on Supabase (asyncpg + SQLAlchemy 2 async) |
| Migrations | Alembic (28 migrations) |
| Background tasks | Celery 5 + Redis |
| Auth | JWT (HS256) + OAuth (Google, GitHub) + TOTP MFA + Email OTP |
| Embeddings | HuggingFace `sentence-transformers/all-MiniLM-L6-v2` (384-dim, pgvector) |
| File storage | Supabase Storage (S3-compatible, CV/resume files) |
| Model storage | DigitalOcean Spaces (ML model staging/production) |
| Error tracking | Sentry (`sentry-sdk[fastapi]`) |
| Metrics | Prometheus (`prometheus-fastapi-instrumentator`) at `/metrics` |

---
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

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
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
# Fill in at minimum: DATABASE_URL, SECRET_KEY
# Generate SECRET_KEY: python -c "import secrets; print(secrets.token_hex(32))"
```

See [Environment Variables Reference](#environment-variables-reference) for all options.

### 3. Run migrations

The app connects to Supabase directly — no local Postgres needed for the default setup.
# Edit .env and fill in all required values (see Environment Variables section below)
```

### 3. Run database migrations(local)

```bash
alembic upgrade head
```

### 4. Start the API

```bash
alembic upgrade head
```

### 4. Start the API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API root: http://localhost:8000
- Interactive docs: http://localhost:8000/docs

### Optional: Docker Compose (local Postgres + Redis)

```bash
# API + local Postgres + Redis (DATABASE_URL is overridden to local postgres in compose)
docker compose up -d

# Also start Celery worker
docker compose --profile worker up -d

# Also start Prometheus
docker compose --profile monitoring up -d
```

Services:

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Postgres | localhost:5432 |
| Redis | localhost:6379 |
| Prometheus | http://localhost:9090 |

> **Note:** `docker-compose.yml` overrides `DATABASE_URL` to point at the local
> Postgres container. To use Supabase, run uvicorn directly (step 4).

---

## API overview

### Auth (`/api/auth/*`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register with email + password |
| `POST` | `/api/auth/login` | Login → JWT |
| `POST` | `/api/auth/logout` | Invalidate token |
| `POST` | `/api/auth/refresh` | Refresh access token |
| `GET` | `/api/auth/oauth/google` | Google OAuth flow |
| `GET` | `/api/auth/oauth/github` | GitHub OAuth flow |
| `POST` | `/api/auth/mfa/enable` | Enable TOTP MFA |
| `POST` | `/api/auth/mfa/verify` | Verify TOTP code |

### Users (`/api/users/*`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/users/me` | Current user profile |
| `PATCH` | `/api/users/me` | Update profile |
| `POST` | `/api/users/me/cv` | Upload CV/resume |

### Jobs, Chat, Roadmap (`/api/*`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/jobs` | Search job listings |
| `POST` | `/api/chat` | AI career chat |
| `GET` | `/api/roadmap` | Learning roadmap |

### Super-admin dashboard (`/api/admin/*`)

All routes require `is_admin=True` in the JWT unless noted.

#### ML pipeline

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/admin/ml/runs` | List training runs (Supabase), filterable by `status`/`model_type` |
| `GET` | `/api/admin/ml/runs/{run_id}` | Single training run with full metrics |
| `POST` | `/api/admin/ml/deploy/{run_id}` | Deploy model: copies `models/staging/` → `models/production/` in DO Spaces, updates status |
| `POST` | `/api/admin/ml/trigger` | Trigger `monthly_training_pipeline` DAG via Airflow |

#### Taxonomy

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/admin/taxonomy/unmatched` | List low-confidence job titles pending review |
| `PATCH` | `/api/admin/taxonomy/unmatched/{id}` | Accept (→ writes to `taxonomy_roles` DB) or decline |
| `GET` | `/api/admin/taxonomy/roles` | List accepted canonical roles |

#### System health

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/admin/system/pipeline-status` | Last run state for both DAGs (Airflow proxy) |
| `GET` | `/api/admin/system/pipeline-runs` | ETL run history + task durations (Recharts data) |
| `GET` | `/api/admin/system/storage` | DO Spaces model file listing + total size |

#### Sentry

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/admin/sentry/summary` | `is_admin` + 5-min cache | Error counts, trend, top issues, p95, Apdex |
| `POST` | `/api/admin/sentry-webhook` | HMAC-SHA256 only | Receives Sentry alert webhooks |

#### Notifications feed

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/admin/notifications` | Receive HMAC-signed pipeline webhook from CareerCompass |
| `GET` | `/api/admin/notifications-feed` | List stored notifications (pipeline + Sentry), paginated |
| `PATCH` | `/api/admin/notifications-feed/{id}/read` | Mark one notification as read |
| `PATCH` | `/api/admin/notifications-feed/mark-all-read` | Bulk mark read |

#### Users

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/admin/users` | List all users (paginated) |
| `GET/PATCH/DELETE` | `/api/admin/users/{id}` | Get / update / deactivate user |
| `POST` | `/api/admin/users/{id}/reactivate` | Reactivate deactivated user |

---

## Project structure

```
app/
├── api/
│   ├── deps.py                  # JWT auth dependencies
│   ├── auth.py, mfa.py          # Auth routes
│   ├── users.py, admin.py       # User management
│   ├── admin_ml.py              # ML pipeline admin + notifications feed
│   ├── admin_taxonomy.py        # Taxonomy review admin
│   ├── admin_system.py          # System health / Airflow proxy
│   ├── admin_sentry.py          # Sentry proxy + webhook receiver
│   ├── chat.py, jobs.py         # Core product routes
│   └── health.py
├── core/
│   ├── config.py                # Pydantic Settings (validates secrets at startup)
│   ├── database.py              # SQLAlchemy async engine + session
│   ├── security.py              # JWT helpers
│   └── rate_limit.py            # In-process fixed-window rate limiter
├── models/                      # SQLAlchemy ORM models (17 files)
├── repositories/                # Data access layer
├── schemas/                     # Pydantic request/response models
├── services/
│   ├── airflow_service.py       # Airflow REST API client (async, parallel calls)
│   ├── sentry_service.py        # Sentry API client (async, 5-min TTL cache, parallel calls)
│   ├── supabase_service.py      # asyncpg pool for Supabase admin queries + writes
│   ├── spaces_service.py        # Shared DO Spaces boto3 client factory
│   ├── auth_service.py, user_service.py, ...
│   └── email_service.py, embedding_service.py, ...
└── main.py                      # App factory, lifespan, router mounts
alembic/versions/                # 28 migration files
```

---

## Database migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "describe change"

# Check current state
alembic current

# Roll back one step
alembic downgrade -1
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
./run_tests.sh

# With coverage
./run_tests.sh coverage

# In Docker
./run_tests.sh docker

# Directly
pytest tests/ -v
```

---

## Environment Variables Reference

### Required to start

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | JWT signing key — generate: `python -c "import secrets; print(secrets.token_hex(32))"` |

> The app **refuses to start in production** (`ENVIRONMENT=production`) if either
> of these is still set to their placeholder defaults.

### Application

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` |
| `DEBUG` | `false` | Enable debug mode |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | 24 hours |

### OAuth (optional)

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth app credentials |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub OAuth app credentials |
| `OAUTH_STATE_SECRET` | CSRF protection secret (different from `SECRET_KEY`) |

### Embeddings / LLM

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_PROVIDER` | `hf` | `hf` (HuggingFace local) or `hosted` (OpenAI-compatible) |
| `EMBEDDING_MODEL_NAME` | `sentence-transformers/all-MiniLM-L6-v2` | Model name |
| `EMBEDDING_DIMENSIONS` | `384` | Must match pgvector column dimension |
| `HF_TOKEN` | | HuggingFace token (for `hf` provider) |
| `END_POINT` / `HOSTED_LLM_TOKEN` | | Hosted LLM endpoint + token (for `hosted` provider) |

### Storage (Supabase S3)

| Variable | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Supabase Storage S3 credentials |
| `S3_BUCKET_NAME` | Resume bucket name |
| `S3_ENDPOINT_URL` | Supabase Storage endpoint |

### Redis / Celery

| Variable | Description |
|---|---|
| `REDIS_URL` | Redis connection URL (supports `rediss://` TLS) |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Usually same as `REDIS_URL` |

### Email / OTP

| Variable | Description |
|---|---|
| `MAILGUN_API_KEY` / `MAILGUN_DOMAIN` | Mailgun credentials |
| `MAILGUN_FROM_EMAIL` | Sender address |
| `OTP_EXPIRE_MINUTES` | OTP validity window (default 10) |

### Super-admin dashboard

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Plain psycopg2 URL for Supabase (admin read/write queries) |
| `AIRFLOW_API_URL` | Airflow REST API base URL (`http://...:8080/api/v1`) |
| `AIRFLOW_SERVICE_ACCOUNT_USER` / `AIRFLOW_SERVICE_ACCOUNT_PASSWORD` | Airflow `backend-svc` account |
| `SENTRY_DSN` | Sentry ingest URL |
| `SENTRY_AUTH_TOKEN` | Internal integration token (`project:read` + `org:read`) |
| `SENTRY_ORG_SLUG` / `SENTRY_PROJECT_SLUG` | Sentry org/project identifiers |
| `SENTRY_WEBHOOK_SECRET` | HMAC secret for verifying inbound Sentry webhooks |
| `PIPELINE_WEBHOOK_SECRET` | HMAC secret shared with CareerCompass `notify_admin` task |
| `DO_SPACES_KEY` / `DO_SPACES_SECRET` | DO Spaces credentials for model deploy |
| `DO_SPACES_BUCKET` / `DO_SPACES_ENDPOINT` / `DO_SPACES_REGION` | DO Spaces config |

---

## Implementation status

| Phase | Description | Status |
|---|---|---|
| Scaffold | FastAPI app, config, CORS, folder structure | ✅ Done |
| Auth | JWT, register/login, token blocklist | ✅ Done |
| OAuth | Google + GitHub OAuth 2.0 | ✅ Done |
| MFA | TOTP + Email OTP | ✅ Done |
| Users | Profile update, CV upload, GitHub sync | ✅ Done |
| Alembic | 28 versioned migrations | ✅ Done |
| Jobs | Job listings, search, pgvector similarity | ✅ Done |
| Chat | LangGraph AI career chat | ✅ Done |
| Roadmap | Learning roadmap generation | ✅ Done |
| Admin users | User management endpoints | ✅ Done |
| **Phase 2** | **Super-admin dashboard (ML, taxonomy, system, Sentry, notifications)** | ✅ **Done** |
| Phase 4 | Prometheus instrumentation + `/metrics` endpoint | ✅ Done |
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
