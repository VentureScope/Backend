# Docker Setup for VentureScope Backend

This document explains how to run VentureScope Backend using Docker Compose with secure environment variable management.

## 🔒 Security-First Architecture

### Single Source of Truth: `.env` File
All configuration is managed in a single `.env` file that:
- ✅ **Never gets committed** to git (protected by `.gitignore`)
- ✅ **Works for both Docker and local development**
- ✅ **Follows industry security standards**
- ✅ **Eliminates environment variable duplication**

### Configuration Flow
```
.env (secrets) → Docker Compose → Application
     ↓
  (same file)
     ↓
Local Development → Application
```

## 🚀 Quick Start

### 1. Setup Environment
```bash
# Copy example environment file
cp .env.example .env

# Edit with your actual credentials
nano .env  # or your favorite editor
```

### 2. Validate Configuration
```bash
# Check environment security
python3 check_docker.py

# Should show: "🎉 Docker environment is properly configured!"
```

### 3. Start Application
```bash
# Start all services (backend, database, redis)
docker compose up --build

# Or run in background
docker compose up -d --build
```

### 4. Test OAuth
```bash
# Test OAuth endpoint
curl 'http://localhost:8000/api/auth/oauth/google/login'

# Should return authorization URL with your client_id
```

## 📋 Environment Variables

### Required OAuth Variables
```env
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-google-client-secret
OAUTH_STATE_SECRET=your-oauth-state-secret-here
```

### Required Application Variables
```env
SECRET_KEY=your-jwt-secret-key
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/venturescope
```

### Google OAuth Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API and OAuth consent screen
4. Create OAuth 2.0 credentials (Web application)
5. Add authorized redirect URI: `http://localhost:8000/api/auth/oauth/google/callback`
6. Copy Client ID and Client Secret to `.env`

### Generate Secrets
```bash
# Generate JWT secret
openssl rand -hex 32

# Generate OAuth state secret
openssl rand -hex 32
```

## 🐳 Docker Commands

### Development
```bash
# Start all services
docker compose up --build

# View logs
docker compose logs backend
docker compose logs postgres
docker compose logs redis

# Stop services
docker compose down

# Rebuild and restart
docker compose down && docker compose up --build
```

### Testing
```bash
# Run tests in Docker
docker compose --profile testing up test

# Run tests with coverage
docker compose --profile testing up test --build
```

### Database Management
```bash
# Connect to database
docker compose exec postgres psql -U venturescope -d venturescope

# Run migrations
docker compose exec backend alembic upgrade head

# Create migration
docker compose exec backend alembic revision --autogenerate -m "description"
```

## 🔧 How It Works

### Environment Loading in Docker
```yaml
# docker-compose.yml
services:
  backend:
    env_file:
      - .env  # Loads ALL variables from .env
    environment:
      # Only override specific Docker networking variables
      DATABASE_URL: postgresql+asyncpg://venturescope:venturescope@postgres:5432/venturescope
```

### Local vs Docker Database URLs
- **Local development**: `DATABASE_URL` connects to host PostgreSQL
- **Docker development**: `DATABASE_URL` is overridden for container networking
- **Same `.env` file works for both!**

## ⚠️ Security Best Practices

### What's Protected
✅ All secrets in `.env` file only  
✅ `.env` in `.gitignore`  
✅ No hardcoded secrets in `docker-compose.yml`  
✅ No hardcoded secrets in source code  
✅ Same environment variables for all deployments  

### What to Avoid
❌ Hardcoding secrets in `docker-compose.yml`  
❌ Committing `.env` file to git  
❌ Different env vars for Docker vs local  
❌ Storing secrets in source code  

### Validation
```bash
# Always run before deployment
python3 check_docker.py

# Validates:
# - No hardcoded secrets in docker-compose.yml
# - .env file exists and has required variables
# - .env is protected by .gitignore
```

## 🌐 Endpoints

Once running, the following endpoints are available:

- **API Documentation**: http://localhost:8000/docs
- **OAuth Login**: http://localhost:8000/api/auth/oauth/google/login
- **Health Check**: http://localhost:8000/health (if implemented)

## 🔍 Troubleshooting

### Empty client_id in OAuth URL
```bash
# Check if environment variables are loaded
docker compose logs backend | grep -i "client_id\|oauth"

# Validate .env file
python3 check_docker.py
```

### Database Connection Issues
```bash
# Check database is running
docker compose ps

# Check database logs
docker compose logs postgres

# Test database connection
docker compose exec postgres pg_isready -U venturescope
```

### OAuth Callback Errors
1. Verify Google OAuth redirect URI matches exactly: `http://localhost:8000/api/auth/oauth/google/callback`
2. Check OAuth credentials are correct in `.env`
3. Ensure `OAUTH_STATE_SECRET` is set and unique

## 📚 Related Files

- `.env` - Your actual environment variables (NEVER commit)
- `.env.example` - Template for environment variables (safe to commit)
- `docker-compose.yml` - Docker service definitions (no secrets)
- `check_docker.py` - Validation script for security
- `Dockerfile` - Application container definition

## 🤝 Industry Standards Compliance

This setup follows Docker and security industry standards:

- **12-Factor App**: Configuration through environment variables
- **Docker Compose**: Official environment file loading with `env_file`
- **Security**: No secrets in source code or Docker files
- **DevOps**: Same configuration for all environments
- **Git Security**: Secrets excluded from version control