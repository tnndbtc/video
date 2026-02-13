# BeatStitch Deployment Guide

This guide covers deploying BeatStitch to production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [Docker Deployment](#docker-deployment)
- [Reverse Proxy Setup](#reverse-proxy-setup)
- [SSL/TLS Configuration](#ssltls-configuration)
- [Backup Procedures](#backup-procedures)
- [Monitoring](#monitoring)
- [Scaling Considerations](#scaling-considerations)
- [Deployment Checklist](#deployment-checklist)

## Prerequisites

### System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Storage | 50 GB SSD | 100+ GB SSD |
| OS | Linux (Ubuntu 22.04+) | Ubuntu 22.04 LTS |

### Software Requirements

- Docker Engine 24.0+
- Docker Compose v2.20+
- Nginx or Caddy (reverse proxy)
- SSL certificate (Let's Encrypt recommended)

### Network Requirements

- Port 80/443 accessible from internet (reverse proxy)
- Internal ports (3000, 8000, 6379) blocked from external access
- Outbound internet access for package updates

## Environment Configuration

### Environment Variables Reference

Create `.env` from the template:

```bash
cp .env.example .env
```

#### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key. **MUST be changed!** Generate with `openssl rand -hex 32` | `a1b2c3d4...` (64 hex chars) |

#### Application Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Enable debug mode (set `false` in production) | `false` |
| `VERSION` | Application version | `0.1.0` |

#### Database Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLite database URL. Uses file-based storage. | `sqlite:////data/db/beatstitch.db` |

#### Redis Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |

#### Storage Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `STORAGE_PATH` | Base path for file storage | `/data` |
| `MAX_UPLOAD_SIZE` | Maximum upload size in bytes | `524288000` (500MB) |

#### API and CORS

| Variable | Description | Default |
|----------|-------------|---------|
| `API_URL` | API URL for frontend. Use `/api` for reverse proxy setup. | Empty (same-origin) |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `http://localhost:3000` |

#### Authentication

| Variable | Description | Default |
|----------|-------------|---------|
| `ACCESS_TOKEN_EXPIRE_HOURS` | JWT token expiration in hours | `24` |

### Production Environment Example

```bash
# .env (production)

# Application
SECRET_KEY=your-64-character-hex-secret-generated-with-openssl-rand-hex-32
DEBUG=false
VERSION=1.0.0

# Database
DATABASE_URL=sqlite:////data/db/beatstitch.db

# Redis
REDIS_URL=redis://redis:6379/0

# Storage
STORAGE_PATH=/data
MAX_UPLOAD_SIZE=524288000

# API / Frontend
API_URL=/api
CORS_ORIGINS=https://beatstitch.example.com

# Authentication
ACCESS_TOKEN_EXPIRE_HOURS=24
```

## Docker Deployment

### Starting Production Services

```bash
# Initialize environment
make init-env

# Edit .env with production values
nano .env

# Start services in detached mode
make prod

# Verify services are running
docker-compose ps

# Check logs
make logs
```

### Container Resources

For production, consider adding resource limits to `docker-compose.yml`:

```yaml
services:
  backend:
    # ... existing config ...
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M

  worker:
    # ... existing config ...
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2'
        reservations:
          memory: 1G
```

> **Note**: `deploy.resources` only works in Docker Swarm mode. For standard `docker-compose up`, use `mem_limit` (Compose v2) or rely on job timeouts as primary protection.

### Health Checks

The backend provides a health endpoint:

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "healthy"},
    "redis": {"status": "healthy"},
    "storage": {"status": "healthy", "free_gb": 45.2},
    "ffmpeg": {"status": "healthy"}
  },
  "version": "1.0.0"
}
```

Add health check to docker-compose for automatic restarts:

```yaml
services:
  backend:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## Reverse Proxy Setup

### Nginx Configuration

Create `/etc/nginx/sites-available/beatstitch`:

```nginx
server {
    listen 80;
    server_name beatstitch.example.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name beatstitch.example.com;

    # SSL certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/beatstitch.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/beatstitch.example.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # CRITICAL: Allow large file uploads (500MB)
    client_max_body_size 500M;

    # Increase timeouts for large uploads
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 60s;

    # API endpoints
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Disable buffering for upload progress
        proxy_request_buffering off;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://localhost:8000/health;
        proxy_set_header Host $host;
    }

    # Frontend (React)
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for HMR in development)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/beatstitch /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Caddy Configuration

Create `Caddyfile`:

```caddyfile
beatstitch.example.com {
    # Large upload support
    request_body {
        max_size 500MB
    }

    # API endpoints
    handle /api/* {
        reverse_proxy localhost:8000
    }

    # Health check
    handle /health {
        reverse_proxy localhost:8000
    }

    # Frontend
    handle {
        reverse_proxy localhost:3000
    }
}
```

## SSL/TLS Configuration

### Let's Encrypt with Certbot (Nginx)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d beatstitch.example.com

# Verify auto-renewal
sudo certbot renew --dry-run
```

### Let's Encrypt with Caddy

Caddy automatically obtains and renews Let's Encrypt certificates. Just ensure:
- Domain DNS points to your server
- Ports 80 and 443 are open

## Backup Procedures

### What to Backup

| Location | Contents | Frequency |
|----------|----------|-----------|
| `/data/db/beatstitch.db` | SQLite database | Daily |
| `/data/uploads/` | User-uploaded media | Daily |
| `/data/derived/` | Beat grids, EDLs, thumbnails | Weekly (regeneratable) |
| `/data/outputs/` | Rendered videos | Optional (regeneratable) |
| `.env` | Configuration | On change |

### Backup Script

Create `scripts/backup.sh`:

```bash
#!/bin/bash
# BeatStitch Backup Script

set -e

BACKUP_DIR="/var/backups/beatstitch"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="beatstitch_backup_${DATE}"

# Create backup directory
mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"

# Stop services temporarily for consistent backup
docker-compose stop backend worker

# Backup database
cp /var/lib/docker/volumes/video_beatstitch-data/_data/db/beatstitch.db \
   "${BACKUP_DIR}/${BACKUP_NAME}/beatstitch.db"

# Backup uploads
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/uploads.tar.gz" \
    -C /var/lib/docker/volumes/video_beatstitch-data/_data/uploads .

# Backup configuration
cp .env "${BACKUP_DIR}/${BACKUP_NAME}/.env"

# Restart services
docker-compose start backend worker

# Create archive
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" \
    -C "${BACKUP_DIR}" "${BACKUP_NAME}"

# Cleanup
rm -rf "${BACKUP_DIR}/${BACKUP_NAME}"

# Keep only last 7 daily backups
find "${BACKUP_DIR}" -name "beatstitch_backup_*.tar.gz" -mtime +7 -delete

echo "Backup completed: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
```

### Automated Backups (Cron)

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/video/scripts/backup.sh >> /var/log/beatstitch-backup.log 2>&1
```

### Restore from Backup

```bash
#!/bin/bash
# Restore from backup

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: restore.sh <backup_file.tar.gz>"
    exit 1
fi

# Stop services
docker-compose down

# Extract backup
tar -xzf "$BACKUP_FILE" -C /tmp
BACKUP_DIR=$(basename "$BACKUP_FILE" .tar.gz)

# Restore database
cp "/tmp/${BACKUP_DIR}/beatstitch.db" \
   /var/lib/docker/volumes/video_beatstitch-data/_data/db/

# Restore uploads
tar -xzf "/tmp/${BACKUP_DIR}/uploads.tar.gz" \
    -C /var/lib/docker/volumes/video_beatstitch-data/_data/uploads

# Restore configuration
cp "/tmp/${BACKUP_DIR}/.env" .env

# Start services
docker-compose up -d

# Cleanup
rm -rf "/tmp/${BACKUP_DIR}"

echo "Restore completed"
```

## Monitoring

### Log Aggregation

Configure Docker logging driver for production:

```yaml
# docker-compose.yml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Prometheus Metrics

The backend exposes Prometheus metrics (if enabled):

```bash
curl http://localhost:8000/metrics
```

Example Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: 'beatstitch'
    static_configs:
      - targets: ['localhost:8000']
```

### Key Metrics to Monitor

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `http_requests_total` | Total HTTP requests | N/A |
| `render_jobs_total` | Total render jobs by status | >10 failed/hour |
| `render_duration_seconds` | Render job duration | >30 minutes |
| `active_render_jobs` | Currently running renders | >5 |
| `disk_usage_bytes` | Storage usage | >80% capacity |

### Simple Health Monitoring Script

```bash
#!/bin/bash
# health_check.sh

HEALTH_URL="http://localhost:8000/health"
ALERT_EMAIL="admin@example.com"

response=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL")

if [ "$response" != "200" ]; then
    echo "BeatStitch health check failed at $(date)" | \
        mail -s "BeatStitch Alert" "$ALERT_EMAIL"
fi
```

Add to cron for regular checks:

```bash
*/5 * * * * /path/to/health_check.sh
```

## Scaling Considerations

### Current Limits (MVP)

- Single server deployment
- One worker process
- SQLite database (single writer)
- Local file storage

### Horizontal Scaling (Phase 2)

For scaling beyond a single server:

1. **Database**: Migrate from SQLite to PostgreSQL
2. **Storage**: Use shared storage (NFS, MinIO, S3)
3. **Workers**: Run multiple worker containers
4. **Load Balancer**: Add nginx/HAProxy upstream

```
                   Load Balancer
                        |
          +-------------+-------------+
          |                           |
     App Server 1              App Server 2
          |                           |
          +-------------+-------------+
                        |
     +------------------+------------------+
     |                  |                  |
  PostgreSQL         Redis             MinIO
```

### Worker Scaling

To run multiple workers:

```yaml
# docker-compose.yml
services:
  worker:
    deploy:
      replicas: 3
```

Or scale manually:

```bash
docker-compose up -d --scale worker=3
```

## Deployment Checklist

### Pre-Deployment

- [ ] Generate secure `SECRET_KEY` with `openssl rand -hex 32`
- [ ] Set `DEBUG=false` in production
- [ ] Configure domain name and DNS
- [ ] Set `CORS_ORIGINS` to production domain
- [ ] Set `API_URL` appropriately (usually `/api`)
- [ ] Review and set `MAX_UPLOAD_SIZE` limit
- [ ] Configure reverse proxy with large upload support (`client_max_body_size 500M`)
- [ ] Obtain SSL certificate
- [ ] Review worker Dockerfile runs as non-root user
- [ ] Set up backup schedule

### Post-Deployment

- [ ] Verify `/health` endpoint returns healthy status
- [ ] Test user registration and login
- [ ] Test small file upload
- [ ] Test large file upload (>100MB)
- [ ] Test beat analysis completes
- [ ] Test timeline generation
- [ ] Test preview render completes
- [ ] Test final render completes
- [ ] Verify job timeout kills long-running FFmpeg processes
- [ ] Check logs for structured JSON output
- [ ] Verify SSL certificate is valid
- [ ] Test backup and restore procedures
- [ ] Set up monitoring alerts

### Security Checklist

- [ ] All services run behind reverse proxy
- [ ] Only ports 80/443 exposed externally
- [ ] Internal ports (8000, 6379) not accessible from internet
- [ ] Strong `SECRET_KEY` configured
- [ ] HTTPS enforced (HTTP redirects to HTTPS)
- [ ] CORS properly restricted
- [ ] Rate limiting enabled
- [ ] File upload validation enabled
- [ ] Worker runs as non-root user

## Troubleshooting

See [troubleshooting.md](./troubleshooting.md) for common issues and solutions.

## Support

For issues:

1. Check [troubleshooting.md](./troubleshooting.md)
2. Review logs: `make logs`
3. Check health endpoint: `curl http://localhost:8000/health`
4. Open an issue on GitHub
