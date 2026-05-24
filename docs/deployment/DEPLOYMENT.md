# VentureScope Backend — Deployment & CI/CD Guide

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Services & Infrastructure](#services--infrastructure)
3. [Environment Variables Reference](#environment-variables-reference)
4. [CI/CD Pipeline](#cicd-pipeline)
5. [Docker Images](#docker-images)
6. [Azure Container Apps](#azure-container-apps)
7. [Database Migrations](#database-migrations)
8. [Manual Deployment](#manual-deployment)
9. [Updating Environment Variables on Azure](#updating-environment-variables-on-azure)
10. [Monitoring & Logs](#monitoring--logs)
11. [Troubleshooting](#troubleshooting)
12. [Local Development](#local-development)

---

## Architecture Overview

```
GitHub (master-v2)
    │
    ▼ push triggers
GitHub Actions CI/CD
    │
    ├── Build API image ──────► ghcr.io/venturescope/backend:{sha}
    │
    └── Build Worker image ───► ghcr.io/venturescope/backend-worker:{sha}
                                          │
                              ┌───────────┴───────────┐
                              ▼                       ▼
                  Azure Container App         Azure Container App
                   (venturescope)            (backgroundworker)
                   API Server                Celery Worker
                   Port 8000                 Background tasks
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
               Supabase    Upstash    Supabase
               PostgreSQL  Redis      Storage
               (main DB)   (OTP/      (files)
                            Celery)
```

---

## Services & Infrastructure

| Service | Provider | Purpose |
|---|---|---|
| **API Server** | Azure Container Apps (`venturescope`) | FastAPI REST API + WebSocket |
| **Background Worker** | Azure Container Apps (`backgroundworker`) | Celery embedding tasks |
| **Database** | Supabase PostgreSQL | All application data + pgvector |
| **OTP / Rate Limiting** | Upstash Redis (HTTP) | OTP codes, resend rate limits |
| **Celery Broker** | Render Redis (wire protocol) | Task queue + result backend |
| **File Storage** | Supabase Storage (S3-compatible) | CVs, profile pictures, org logos |
| **Email** | Mailgun | OTP emails, org invite emails |
| **Container Registry** | GitHub Container Registry (GHCR) | Docker image storage |
| **Error Monitoring** | Sentry | Runtime error tracking |
| **Metrics** | Prometheus + Azure Monitor | Application metrics |

---

## Environment Variables Reference

All environment variables are configured in `.env` for local dev and set directly on Azure Container Apps for production.

### Core Application

| Variable | Required | Description |
|---|---|---|
| `PROJECT_NAME` | No | Application name (default: VentureScope) |
| `DEBUG` | No | Enable debug mode (default: false) |
| `ENVIRONMENT` | No | `development` \| `staging` \| `production` |
| `SECRET_KEY` | **Yes** | JWT signing key — generate with `openssl rand -hex 32` |
| `ALGORITHM` | No | JWT algorithm (default: HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | JWT TTL in minutes (default: 1440 = 24h) |

### Database

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | **Yes** | PostgreSQL async URL: `postgresql+asyncpg://user:pass@host:port/db?ssl=require` |
| `SUPABASE_URL` | **Yes** | Plain psycopg2 URL for admin/analytics queries: `postgresql://user:pass@host:5432/db` |

### Redis

| Variable | Required | Description |
|---|---|---|
| `UPSTASH_REDIS_URL` | **Yes** | Upstash HTTP URL: `https://xxx.upstash.io` |
| `UPSTASH_REDIS_TOKEN` | **Yes** | Upstash REST token |
| `CELERY_BROKER_URL` | **Yes** | Wire-protocol URL: `rediss://default:token@host:6379?ssl_cert_reqs=CERT_NONE` |
| `CELERY_RESULT_BACKEND` | **Yes** | Same as `CELERY_BROKER_URL` |

### AI / LLM

| Variable | Required | Description |
|---|---|---|
| `END_POINT` | **Yes** | LLM API base URL (e.g. `https://models.github.ai/inference`) |
| `HOSTED_LLM_TOKEN` | **Yes** | LLM API token |
| `CHAT_MODEL_NAME` | No | Model name (default: `gpt-4o-mini`) |
| `CHAT_MAX_TOKENS` | No | Max tokens per response (default: 800) |
| `CHAT_TEMPERATURE` | No | Sampling temperature (default: 0.7) |
| `SERPER_API_KEY` | **Yes** | Serper API key for web search in roadmaps/chat |

### Embeddings

| Variable | Required | Description |
|---|---|---|
| `EMBEDDING_PROVIDER` | **Yes** | `hf` for HuggingFace or `hosted` for OpenAI-compatible |
| `HF_TOKEN` | If `hf` | HuggingFace API token |
| `EMBEDDING_MODEL_NAME` | **Yes** | e.g. `sentence-transformers/all-MiniLM-L6-v2` |
| `EMBEDDING_DIMENSIONS` | **Yes** | Must match model output (e.g. `384`) |

### File Storage (Supabase S3-compatible)

| Variable | Required | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | **Yes** | Supabase Storage access key |
| `AWS_SECRET_ACCESS_KEY` | **Yes** | Supabase Storage secret |
| `AWS_REGION` | **Yes** | Region (e.g. `eu-west-2`) |
| `S3_BUCKET_NAME` | **Yes** | CV/resume files bucket (e.g. `resume`) |
| `S3_ENDPOINT_URL` | **Yes** | `https://{project}.storage.supabase.co/storage/v1/s3` |
| `S3_PROFILE_PICTURE_BUCKET` | No | Profile pictures bucket (default: `photo`) |
| `S3_ORG_BUCKET` | **Yes** | Org logos bucket (e.g. `organization`) |

### Email (Mailgun)

| Variable | Required | Description |
|---|---|---|
| `MAILGUN_API_KEY` | **Yes** | Mailgun API key |
| `MAILGUN_DOMAIN` | **Yes** | Sending domain (e.g. `mg.yourdomain.com`) |
| `MAILGUN_FROM_EMAIL` | No | From address (default: `noreply@mg.venturescope.app`) |
| `MAILGUN_API_BASE_URL` | No | US: `https://api.mailgun.net/v3`, EU: `https://api.eu.mailgun.net/v3` |

### OAuth

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLIENT_ID` | For Google OAuth | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | For Google OAuth | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | For Google OAuth | e.g. `https://api.venturescope.tech/api/auth/oauth/google/callback` |
| `GITHUB_CLIENT_ID` | For GitHub OAuth | GitHub OAuth app client ID |
| `GITHUB_CLIENT_SECRET` | For GitHub OAuth | GitHub OAuth app client secret |
| `GITHUB_REDIRECT_URI` | For GitHub OAuth | e.g. `https://api.venturescope.tech/api/auth/oauth/github/callback` |
| `OAUTH_STATE_SECRET` | **Yes** | CSRF state signing key — generate with `openssl rand -hex 32` |

### Monitoring

| Variable | Required | Description |
|---|---|---|
| `SENTRY_DSN` | No | Sentry DSN for error tracking |
| `SENTRY_ENVIRONMENT` | No | `development` \| `production` |
| `SENTRY_TRACES_SAMPLE_RATE` | No | Trace sampling rate (0.0–1.0) |
| `SENTRY_AUTH_TOKEN` | No | Internal integration token |
| `SENTRY_ORG_SLUG` | No | Sentry organization slug |
| `SENTRY_PROJECT_SLUG` | No | Sentry project slug |

### Airflow / Pipeline (Admin features)

| Variable | Required | Description |
|---|---|---|
| `AIRFLOW_API_URL` | No | Airflow REST API URL |
| `AIRFLOW_SERVICE_ACCOUNT_USER` | No | Airflow service account username |
| `AIRFLOW_SERVICE_ACCOUNT_PASSWORD` | No | Airflow service account password |
| `PIPELINE_WEBHOOK_SECRET` | No | HMAC secret for pipeline webhook |

### Digital Ocean Spaces (ML model staging)

| Variable | Required | Description |
|---|---|---|
| `DO_SPACES_KEY` | No | DO Spaces access key |
| `DO_SPACES_SECRET` | No | DO Spaces secret |
| `DO_SPACES_REGION` | No | Region (e.g. `ams3`) |
| `DO_SPACES_BUCKET` | No | Bucket name |
| `DO_SPACES_ENDPOINT` | No | e.g. `https://ams3.digitaloceanspaces.com` |

---

## CI/CD Pipeline

### Trigger

Every push to the `master-v2` branch triggers the full build and deploy pipeline.

```
git push origin master-v2
     │
     ▼
GitHub Actions: .github/workflows/deploy.yml
```

### Pipeline Steps

```
1. Checkout code
     │
2. Set up Docker Buildx
     │
3. Login to GitHub Container Registry (GHCR)
     │
4. Extract image metadata (SHA tags, branch tags, :latest)
     │
5. Build & push API image ──────────────────────────────────────────────────────
│   Uses: Dockerfile                                                            │
│   Cache: GitHub Actions cache (type=gha) — fast, correct invalidation        │
│   Tags pushed:                                                                │
│     ghcr.io/venturescope/backend:{short-sha}  (e.g. 6c55af0f47)             │
│     ghcr.io/venturescope/backend:master-v2                                   │
│     ghcr.io/venturescope/backend:latest                                      │
6. Build & push Worker image ──────────────────────────────────────────────────
│   Uses: Dockerfile.worker                                                     │
│   Tags pushed:                                                                │
│     ghcr.io/venturescope/backend-worker:{short-sha}                          │
│     ghcr.io/venturescope/backend-worker:master-v2                            │
│     ghcr.io/venturescope/backend-worker:latest                               │
7. Compute revision suffix (first 10 chars of commit SHA)
     │   Needed because Azure Container Apps revision names ≤ 10 chars
     │
8. Azure Login (using AZURE_CREDENTIALS secret)
     │
9. Deploy API to Azure Container Apps
│   az containerapp update
│     --name venturescope
│     --image ghcr.io/venturescope/backend:{short-sha}
│     --revision-suffix {10-char-sha}     ← forces new revision every push
     │
10. Deploy Worker to Azure Container Apps
    az containerapp update
      --name backgroundworker
      --image ghcr.io/venturescope/backend-worker:{short-sha}
      --revision-suffix {10-char-sha}
```

### Why `--revision-suffix` is Critical

Without `--revision-suffix`, Azure Container Apps compares image digests. If the new image has the same digest as the running one (can happen with Docker layer caching), Azure **silently skips the update** and keeps running the old code.

With `--revision-suffix {commit-sha}`, Azure always creates a new named revision (e.g. `venturescope--6c55af0f47`), guaranteeing deployment on every push.

### Required GitHub Secrets

| Secret | Value |
|---|---|
| `AZURE_CREDENTIALS` | Azure service principal JSON (`az ad sp create-for-rbac --sdk-auth`) |
| `AZURE_RG` | Azure resource group name (e.g. `NetworkWatcherRG`) |

### Checking Pipeline Status

```
https://github.com/VentureScope/Backend/actions
```

A successful run takes **3–8 minutes**:
- Docker build with GHA cache: ~1–3 min
- Azure deploy: ~1–2 min per container

---

## Docker Images

### API Image (`Dockerfile`)

```dockerfile
FROM python:3.12-slim
# Installs all requirements, copies app code, runs uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Runs the FastAPI application serving all REST API endpoints and WebSocket connections.

### Worker Image (`Dockerfile.worker`)

```dockerfile
FROM python:3.12-slim
# Same requirements, starts Celery worker
CMD ["celery", "-A", "app.celery_config.celery_app", "worker",
     "--loglevel=info", "--concurrency=2"]
```

Runs background tasks:
- `generate_user_profile_embedding` — user embedding after profile updates
- `generate_knowledge_embedding` — individual knowledge chunk embedding
- `batch_generate_knowledge_embeddings` — re-embed all chunks for a source type
- `generate_org_embedding` — organization embedding after profile/membership changes

### Image Tags

| Tag | When created | Use case |
|---|---|---|
| `{short-sha}` e.g. `6c55af0f47` | Every push | Production deploy — pinned to exact commit |
| `master-v2` | Every push to branch | Branch tracking |
| `latest` | Every push | Docker cache reference |

---

## Azure Container Apps

### Container Apps

| Container App | Internal name | Port | Replicas |
|---|---|---|---|
| API Server | `venturescope` | 8000 | 1 (auto-scale configured) |
| Celery Worker | `backgroundworker` | — | 1 |

### Checking Revision Status

```bash
# List all revisions for the API
az containerapp revision list \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --output table

# List all revisions for the worker
az containerapp revision list \
  --name backgroundworker \
  --resource-group NetworkWatcherRG \
  --output table
```

The `Active` column shows which revision is receiving traffic. `HealthState` should be `Healthy`. The `Name` column should contain the latest commit SHA.

### Forcing a Manual Redeployment

If GitHub Actions ran but the new code is not live:

```bash
# Get the latest image tag from GHCR (short SHA of HEAD commit)
# Then run:
az containerapp update \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --image ghcr.io/venturescope/backend:{short-sha} \
  --revision-suffix {short-sha}

az containerapp update \
  --name backgroundworker \
  --resource-group NetworkWatcherRG \
  --image ghcr.io/venturescope/backend-worker:{short-sha} \
  --revision-suffix {short-sha}
```

Replace `{short-sha}` with the first 7–10 characters of the latest commit SHA:

```bash
git rev-parse --short HEAD
```

### Custom Domain

The API is accessible at:
- **Production:** `https://api.venturescope.tech`
- **Azure default:** `https://venturescope.{random}.{region}.azurecontainerapps.io`

Both URLs work simultaneously. The custom domain was configured via:

```bash
az containerapp hostname add \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --hostname api.venturescope.tech

az containerapp hostname bind \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --hostname api.venturescope.tech \
  --certificate-type managed   # free Let's Encrypt cert
```

---

## Database Migrations

Migrations are managed with Alembic. They run **manually** — not automatically on deployment.

### Run migrations on production

```bash
# Option 1: Run locally against the production DB
# (ensure DATABASE_URL in .env points to production)
alembic upgrade head

# Option 2: Run via Azure Cloud Shell
# SSH into the container or use az containerapp exec
az containerapp exec \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --command "alembic upgrade head"
```

### Check current migration state

```bash
alembic current      # what revision the DB is at
alembic heads        # latest revision in code
alembic history      # full migration history
```

### Create a new migration

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "add my new table"

# Create empty migration (manual)
alembic revision -m "add my custom change"
```

### Migration file naming convention

Files follow the pattern: `{revision_id}_{description}.py`

Examples:
- `l5g9h2i3j4k5_add_organization_tables.py`
- `p9k3l6m7n8o9_add_resource_progress.py`

**Always run `alembic upgrade head` after deploying code that contains new migrations.**

---

## Manual Deployment

For situations where CI/CD is not available or you need to deploy a specific version.

### Prerequisites

```bash
# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Login to Azure
az login

# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin
```

### Deploy a specific commit

```bash
# 1. Get the short SHA you want to deploy
SHA=6c55af0f47

# 2. Update API container
az containerapp update \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --image ghcr.io/venturescope/backend:${SHA} \
  --revision-suffix ${SHA}

# 3. Update worker container
az containerapp update \
  --name backgroundworker \
  --resource-group NetworkWatcherRG \
  --image ghcr.io/venturescope/backend-worker:${SHA} \
  --revision-suffix ${SHA}
```

### Build and push manually

```bash
# Build API image
docker build -f Dockerfile -t ghcr.io/venturescope/backend:manual .
docker push ghcr.io/venturescope/backend:manual

# Build worker image
docker build -f Dockerfile.worker -t ghcr.io/venturescope/backend-worker:manual .
docker push ghcr.io/venturescope/backend-worker:manual
```

---

## Updating Environment Variables on Azure

Environment variables are set directly on each Container App. They persist across deployments — you only need to update them when values change.

### Update API container env vars

```bash
az containerapp update -n venturescope -g NetworkWatcherRG --set-env-vars \
  VAR_NAME="value" \
  ANOTHER_VAR="another_value"
```

### Update Worker container env vars

```bash
az containerapp update -n backgroundworker -g NetworkWatcherRG --set-env-vars \
  VAR_NAME="value"
```

### View current env vars

```bash
az containerapp show \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --query "properties.template.containers[0].env" \
  --output table
```

### Complete env var update (all services)

Run this when rotating credentials or adding new services:

```bash
# API + Worker — Upstash Redis
az containerapp update -n venturescope -g NetworkWatcherRG --set-env-vars \
  UPSTASH_REDIS_URL="https://your-db.upstash.io" \
  UPSTASH_REDIS_TOKEN="your-token" \
  CELERY_BROKER_URL="rediss://default:token@host:6379?ssl_cert_reqs=CERT_NONE" \
  CELERY_RESULT_BACKEND="rediss://default:token@host:6379?ssl_cert_reqs=CERT_NONE"

az containerapp update -n backgroundworker -g NetworkWatcherRG --set-env-vars \
  UPSTASH_REDIS_URL="https://your-db.upstash.io" \
  UPSTASH_REDIS_TOKEN="your-token" \
  CELERY_BROKER_URL="rediss://default:token@host:6379?ssl_cert_reqs=CERT_NONE" \
  CELERY_RESULT_BACKEND="rediss://default:token@host:6379?ssl_cert_reqs=CERT_NONE"
```

---

## Monitoring & Logs

### View live API logs

```bash
az containerapp logs show \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --tail 50 \
  --follow
```

### View live worker logs

```bash
az containerapp logs show \
  --name backgroundworker \
  --resource-group NetworkWatcherRG \
  --tail 50 \
  --follow
```

### Health check endpoint

```bash
curl https://api.venturescope.tech/api/health
# Expected: {"status": "ok"}
```

### Metrics

Prometheus metrics are exposed at:
```
GET https://api.venturescope.tech/metrics
```

Sentry error tracking dashboard:
```
https://sentry.io/organizations/venture-scope/projects/venture-scope-app/
```

---

## Troubleshooting

### Deployment ran but changes not live

**Symptom:** GitHub Actions shows green, Azure revision is still the old one.

**Diagnosis:**
```bash
az containerapp revision list \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --output table
```

Check that the revision `Name` contains the latest commit SHA.

**Fix:** Force redeploy with explicit revision suffix:
```bash
SHA=$(git rev-parse --short HEAD)
az containerapp update \
  --name venturescope \
  --resource-group NetworkWatcherRG \
  --image ghcr.io/venturescope/backend:${SHA} \
  --revision-suffix ${SHA}
```

---

### Worker crashes with `InvalidRequestError: mapper failed to initialize`

**Symptom:**
```
sqlalchemy.exc.InvalidRequestError: When initializing mapper
Mapper[OrganizationRoadmap(organization_roadmaps)], expression 'LearningRoadmap'
failed to locate a name
```

**Cause:** A new SQLAlchemy model with cross-table relationships was added but not imported in the Celery worker task files.

**Fix:** Add the missing model import to `app/tasks/_model_imports.py` (or directly to the failing task file):
```python
from app.models.roadmap import LearningRoadmap, LearningRoadmapStep, ...
from app.models.organization import OrganizationRoadmap, ...
```

---

### Celery worker can't connect to Redis (`Connection reset by peer`)

**Symptom:**
```
redis.exceptions.ConnectionError: Error 104 connecting to host:6379.
Connection reset by peer.
```

**Cause on WSL:** WSL2 blocks outbound TLS on non-standard ports. This only affects local development.

**Fix for local dev:**
```bash
CELERY_BROKER_URL=redis://localhost:6379 \
CELERY_RESULT_BACKEND=redis://localhost:6379 \
celery -A app.celery_config.celery_app worker --loglevel=info
```

**On Azure:** This does not occur — Azure Linux VMs have no such restriction.

---

### Database connection pool exhausted (`EMAXCONNSESSION`)

**Symptom:**
```
asyncpg.exceptions.InternalServerError: (EMAXCONNSESSION) max clients reached
in session mode - max clients are limited to pool_size: 15
```

**Cause:** Supabase free tier limits to 15 concurrent connections in session mode. Multiple requests holding connections simultaneously exceed the limit.

**Fix:**
1. Reduce SQLAlchemy pool size in `app/core/database.py`:
   ```python
   create_async_engine(database_url, pool_size=3, max_overflow=2, ...)
   ```
2. Reduce asyncpg pool size in `app/services/supabase_service.py`:
   ```python
   asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2, ...)
   ```
3. Upgrade Supabase plan for higher connection limits.

---

### OTP / Redis operations fail

**Symptom:** Login, OTP send/verify return 500 errors.

**Check:** Verify Upstash HTTP connection:
```python
import asyncio
from app.services.otp_service import get_redis_client
async def test():
    r = get_redis_client()
    print(await r.ping())
asyncio.run(test())
```

If this fails, check `UPSTASH_REDIS_URL` and `UPSTASH_REDIS_TOKEN` environment variables.

---

### Missing `SUPABASE_URL` error

**Symptom:**
```
RuntimeError: SUPABASE_URL is not configured.
Set it to the Supabase PostgreSQL connection string.
```

**Fix:** Set the `SUPABASE_URL` environment variable:
```bash
az containerapp update -n venturescope -g NetworkWatcherRG --set-env-vars \
  SUPABASE_URL="postgresql://postgres.{ref}:{password}@aws-1-{region}.pooler.supabase.com:5432/postgres"
```

Note: `SUPABASE_URL` uses plain `postgresql://` (no `+asyncpg`), port `5432`, and no `?ssl=require`.

---

## Local Development

### Quick start

```bash
# 1. Clone and set up venv
git clone https://github.com/VentureScope/Backend.git
cd Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — fill in required values

# 3. Run database migrations
alembic upgrade head

# 4. Start API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. Start Celery worker (uses local Redis — no TLS issues on WSL)
CELERY_BROKER_URL=redis://localhost:6379 \
CELERY_RESULT_BACKEND=redis://localhost:6379 \
celery -A app.celery_config.celery_app worker --loglevel=info
```

### API docs

```
http://localhost:8000/docs       ← Swagger UI
http://localhost:8000/redoc      ← ReDoc
```

### Running tests

```bash
pytest tests/ -v                          # all tests
pytest tests/unit/ -v                     # unit only
pytest tests/integration/ -v             # integration only
pytest tests/ --cov=app --cov-report=html # with coverage
```

### Local Redis (for Celery)

Your machine already has Redis running (`redis-cli ping` → `PONG`). Use it for Celery during local development to avoid WSL TLS blocking issues with remote Redis.

The `CELERY_BROKER_URL` in `.env` points to Upstash (for production). Override it with environment variables for local runs as shown above — no `.env` changes needed.

---

## Deployment Checklist

Before every production deployment:

- [ ] All changes committed and pushed to `master-v2`
- [ ] GitHub Actions run completed successfully (green)
- [ ] Latest revision in Azure shows the expected commit SHA
- [ ] `GET /api/health` returns `{"status": "ok"}`
- [ ] New Alembic migrations run: `alembic upgrade head`
- [ ] Any new environment variables added to both containers
- [ ] Worker logs checked for startup errors

After deployment:

- [ ] Test a critical endpoint (login, roadmap generation, etc.)
- [ ] Check Sentry for new errors
- [ ] Verify background worker is processing tasks (check worker logs)
