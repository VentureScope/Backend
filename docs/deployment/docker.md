# Docker Deployment Guide

## Overview
This guide covers deploying the VentureScope Backend using Docker and Docker Compose.

## Prerequisites
- Docker 20.0+
- Docker Compose 2.0+

## Development Setup

### Quick Start
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down
```

### Services

#### Backend API
- **Image**: Built from local Dockerfile
- **Port**: 8000 (mapped to host)
- **Dependencies**: PostgreSQL, Redis
- **Environment**: See `.env.example`

#### PostgreSQL Database
- **Image**: `postgres:16-alpine`
- **Port**: 5432 (mapped to host)
- **Volume**: `pgdata` for persistence
- **Database**: `venturescope`

#### Redis Cache
- **Image**: `redis:7-alpine`  
- **Port**: 6379 (mapped to host)
- **Use**: Caching, session storage (future)

### Environment Configuration

Copy and modify environment file:
```bash
cp .env.example .env
```

Key environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: JWT signing secret (generate with `openssl rand -hex 32`)
- `DEBUG`: Enable/disable debug mode

### Database Setup

After starting services, create tables:
```bash
docker-compose exec backend python scripts/create_tables.py
```

## Testing with Docker

### Test Suite
```bash
# Run all tests in Docker
docker-compose --profile testing run --rm test pytest tests/ -v

# Run with coverage
docker-compose --profile testing run --rm test pytest tests/ --cov=app --cov-report=html
```

### Test Service
- **Profile**: `testing` (separate from main services)
- **Image**: Built from `Dockerfile.test`
- **Environment**: Test-specific settings
- **Dependencies**: Same database and Redis instances

## Production Considerations

### Security
- [ ] Use secure `SECRET_KEY`
- [ ] Set `DEBUG=false`
- [ ] Configure proper CORS origins
- [ ] Use environment-specific database credentials

### Performance  
- [ ] Configure database connection pooling
- [ ] Set appropriate worker processes for uvicorn
- [ ] Configure Redis for session/cache storage
- [ ] Add health checks for all services

### Monitoring
- [ ] Add logging configuration
- [ ] Configure metrics collection
- [ ] Set up health check endpoints
- [ ] Configure backup strategies for PostgreSQL

## Troubleshooting

### Common Issues

**Service won't start**
```bash
# Check logs
docker-compose logs backend

# Check service status
docker-compose ps
```

**Database connection issues**
```bash
# Verify database is running
docker-compose exec postgres psql -U venturescope -d venturescope -c "SELECT 1;"

# Check database logs
docker-compose logs postgres
```

**Port conflicts**
```bash
# Check if ports are in use
netstat -tlnp | grep :8000

# Modify ports in docker-compose.yml if needed
```

### Cleanup
```bash
# Remove all containers and volumes
docker-compose down -v

# Remove built images
docker-compose down --rmi all
```

## Docker Images

### Backend Dockerfile
- **Base**: `python:3.12-slim`
- **Working Dir**: `/app`
- **Port**: 8000
- **Command**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### Test Dockerfile
- **Base**: Same as main Dockerfile
- **Additional**: Test dependencies
- **Purpose**: Isolated testing environment

## Last Updated
April 2, 2026 - Initial Docker deployment documentation