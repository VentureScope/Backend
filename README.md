# VentureScope Backend

FastAPI backend for the AI-powered career guidance platform. Start here for implementation order and run instructions.

## Where we started (implementation order)

1. **Project scaffold** – FastAPI app, config, CORS, folder structure ✅  
2. **Database** – PostgreSQL + SQLAlchemy async, base and `User` model ✅  
3. **Auth** – JWT (register, login, `GET /api/users/me`) ✅  
4. **Next steps** – See “Implementation roadmap” below.

## Run locally

### 1. Create virtualenv and install deps

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

### Optional: start all services with Docker Compose

```bash
docker compose up --build -d
```

- API: http://localhost:8000  
- PostgreSQL: localhost:5432  
- Redis: localhost:6379

### 3. Create DB tables (no migrations yet)

From project root (or `backend/`):

```bash
# One-off: create tables from models (add a small script or use Python shell)
python -c "
import asyncio
from app.core.database import engine, Base
from app.models import User
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(init())
print('Tables created.')
"
```

### 4. Environment

```bash
cp .env.example .env
# Edit .env: set SECRET_KEY (e.g. openssl rand -hex 32)
```

### 5. Run API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: http://localhost:8000  
- Docs: http://localhost:8000/docs  

Try: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/users/me` (with `Authorization: Bearer <token>`).

## Implementation roadmap (from here)

| Phase | What to add | Purpose |
|-------|-------------|--------|
| **A** | Alembic migrations | Versioned schema changes |
| **B** | Profile update, GitHub username | Complete User Management (FR1.2) |
| **C** | OAuth (GitHub/Google) | Social login (doc) |
| **D** | `JobListing` model + `/api/jobs` (CRUD + search) | Job market data (FR4) |
| **E** | Job scrapers + Celery + Redis Beat | Weekly scraping (UC-08) |
| **F** | PGVector + embeddings + SBERT | Semantic job matching (FR5.1) |
| **G** | AI services (recommendations, RAG, CV) | LLM integration (FR5–FR7) |
| **H** | B2B models + corporate endpoints | Corporate dashboard (FR8) |

## Folder structure

```
backend/
├── app/
│   ├── api/          # Routers: health, auth, users, (jobs, ai_services later)
│   ├── core/         # config, security, database
│   ├── models/       # SQLAlchemy models (User, JobListing, …)
│   ├── repositories/ # Data access (UserRepository, …)
│   ├── schemas/      # Pydantic request/response
│   ├── services/     # Business logic (AuthService, …)
│   └── main.py
├── requirements.txt
├── docker-compose.yml
└── README.md
```

Aligns with the doc: API → Service → Repository → DB.
