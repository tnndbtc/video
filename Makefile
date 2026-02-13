# BeatStitch Makefile
# ====================
#
# Common commands for development and deployment.
# Run 'make help' to see all available commands.
#

.PHONY: dev prod build logs logs-worker logs-backend logs-frontend stop clean \
        migrate shell-backend shell-worker shell-redis help init-env \
        test test-backend test-worker test-frontend lint format \
        backup restore health status ps restart

# Default target
help:
	@echo "BeatStitch Development Commands"
	@echo "================================"
	@echo ""
	@echo "Getting Started:"
	@echo "  make init-env     - Create .env from template (first time setup)"
	@echo "  make dev          - Start all services in development mode"
	@echo "  make stop         - Stop all services"
	@echo ""
	@echo "Development:"
	@echo "  make build        - Build all Docker images"
	@echo "  make restart      - Restart all services"
	@echo "  make clean        - Stop and remove containers, volumes, and images"
	@echo ""
	@echo "Production:"
	@echo "  make prod         - Start all services in production mode (detached)"
	@echo ""
	@echo "Logs:"
	@echo "  make logs         - Follow logs for all services"
	@echo "  make logs-worker  - Follow logs for worker service"
	@echo "  make logs-backend - Follow logs for backend service"
	@echo "  make logs-frontend- Follow logs for frontend service"
	@echo ""
	@echo "Status:"
	@echo "  make ps           - Show running containers"
	@echo "  make status       - Show container status"
	@echo "  make health       - Check system health"
	@echo ""
	@echo "Database:"
	@echo "  make migrate      - Run database migrations"
	@echo "  make backup       - Create database backup"
	@echo "  make restore      - Restore from backup (requires BACKUP_FILE)"
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run all tests"
	@echo "  make test-backend - Run backend tests"
	@echo "  make test-worker  - Run worker tests"
	@echo "  make test-frontend- Run frontend tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         - Run linters"
	@echo "  make format       - Format code"
	@echo ""
	@echo "Shell Access:"
	@echo "  make shell-backend - Open shell in backend container"
	@echo "  make shell-worker  - Open shell in worker container"
	@echo "  make shell-redis   - Open Redis CLI"

# =============================================================================
# Getting Started
# =============================================================================

# Initialize environment file
init-env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
		echo ""; \
		echo "IMPORTANT: Edit .env and set a secure SECRET_KEY before starting!"; \
		echo "Generate one with: openssl rand -hex 32"; \
	else \
		echo ".env already exists"; \
	fi

# =============================================================================
# Development
# =============================================================================

# Development mode (with build, attached)
dev:
	docker-compose up --build

# Production mode (detached)
prod:
	docker-compose up -d --build

# Build images without starting
build:
	docker-compose build

# Stop all services
stop:
	docker-compose down

# Restart all services
restart:
	docker-compose restart

# Clean everything (including volumes) - WARNING: destroys data!
clean:
	@echo "WARNING: This will delete all data including uploads and database!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker-compose down -v --rmi local

# =============================================================================
# Logs
# =============================================================================

# Follow all logs
logs:
	docker-compose logs -f

# Follow worker logs
logs-worker:
	docker-compose logs -f worker

# Follow backend logs
logs-backend:
	docker-compose logs -f backend

# Follow frontend logs
logs-frontend:
	docker-compose logs -f frontend

# =============================================================================
# Status
# =============================================================================

# Show running containers
ps:
	docker-compose ps

# Show container status with details
status:
	@echo "=== Container Status ==="
	@docker-compose ps
	@echo ""
	@echo "=== Resource Usage ==="
	@docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null || true

# Check system health
health:
	@echo "Checking system health..."
	@curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || \
		echo "Health check failed - is the backend running?"

# =============================================================================
# Database
# =============================================================================

# Run database migrations
migrate:
	docker-compose exec backend alembic upgrade head

# Create database backup
backup:
	@mkdir -p backups
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S); \
	docker-compose exec -T backend cat /data/db/beatstitch.db > backups/beatstitch_$$TIMESTAMP.db; \
	echo "Backup created: backups/beatstitch_$$TIMESTAMP.db"

# Restore from backup (usage: make restore BACKUP_FILE=backups/beatstitch_xxx.db)
restore:
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "Usage: make restore BACKUP_FILE=backups/beatstitch_xxx.db"; \
		exit 1; \
	fi
	@if [ ! -f "$(BACKUP_FILE)" ]; then \
		echo "Backup file not found: $(BACKUP_FILE)"; \
		exit 1; \
	fi
	@echo "Restoring from $(BACKUP_FILE)..."
	docker-compose stop backend worker
	cat $(BACKUP_FILE) | docker-compose exec -T backend tee /data/db/beatstitch.db > /dev/null
	docker-compose start backend worker
	@echo "Restore complete"

# =============================================================================
# Testing
# =============================================================================

# Run all tests
test: test-backend test-worker

# Run backend tests
test-backend:
	docker-compose exec backend pytest -v

# Run worker tests
test-worker:
	docker-compose exec worker pytest -v

# Run frontend tests
test-frontend:
	docker-compose exec frontend npm test

# =============================================================================
# Code Quality
# =============================================================================

# Run linters
lint:
	docker-compose exec backend flake8 app/
	docker-compose exec worker flake8 app/
	docker-compose exec frontend npm run lint

# Format code
format:
	docker-compose exec backend black app/
	docker-compose exec backend isort app/
	docker-compose exec worker black app/
	docker-compose exec worker isort app/

# =============================================================================
# Shell Access
# =============================================================================

# Shell access
shell-backend:
	docker-compose exec backend /bin/bash

shell-worker:
	docker-compose exec worker /bin/bash

# Redis CLI access
shell-redis:
	docker-compose exec redis redis-cli
