#!/bin/bash
# BeatStitch Production Deployment Script
#
# This script builds and deploys the BeatStitch application
# using Docker Compose production configuration.
#
# Usage:
#   ./scripts/deploy.sh         # Full deployment
#   ./scripts/deploy.sh build   # Build only
#   ./scripts/deploy.sh up      # Start only (uses existing images)
#   ./scripts/deploy.sh down    # Stop services
#   ./scripts/deploy.sh logs    # View logs
#   ./scripts/deploy.sh status  # Check service status

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.prod.yml"
ENV_FILE="$PROJECT_ROOT/.env"

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    print_header "Checking Requirements"

    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    print_success "Docker found: $(docker --version)"

    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not available"
        exit 1
    fi
    print_success "Docker Compose found: $(docker compose version)"

    # Check .env file
    if [ ! -f "$ENV_FILE" ]; then
        print_warning ".env file not found"
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            print_warning "Creating .env from .env.example"
            cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
            print_warning "Please edit .env and set secure values before production deployment!"
        else
            print_error ".env.example not found. Cannot continue."
            exit 1
        fi
    fi
    print_success ".env file found"

    # Check compose file
    if [ ! -f "$COMPOSE_FILE" ]; then
        print_error "docker-compose.prod.yml not found"
        exit 1
    fi
    print_success "docker-compose.prod.yml found"

    echo ""
}

build_images() {
    print_header "Building Production Images"
    docker compose -f "$COMPOSE_FILE" build --no-cache
    print_success "Images built successfully"
    echo ""
}

start_services() {
    print_header "Starting Services"
    docker compose -f "$COMPOSE_FILE" up -d
    print_success "Services started"
    echo ""
}

wait_for_healthy() {
    print_header "Waiting for Services to be Healthy"

    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        echo "Checking health (attempt $attempt/$max_attempts)..."

        # Check if all services are healthy
        local unhealthy=$(docker compose -f "$COMPOSE_FILE" ps --format json 2>/dev/null | \
            grep -c '"Health":"unhealthy"' || true)

        if [ "$unhealthy" = "0" ]; then
            # Double-check with a direct health endpoint call
            if curl -sf http://localhost/health > /dev/null 2>&1; then
                print_success "All services are healthy!"
                return 0
            fi
        fi

        sleep 5
        attempt=$((attempt + 1))
    done

    print_warning "Some services may not be fully healthy yet"
    return 1
}

show_status() {
    print_header "Service Status"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
}

show_logs() {
    print_header "Service Logs (last 100 lines)"
    docker compose -f "$COMPOSE_FILE" logs --tail=100
}

follow_logs() {
    print_header "Following Service Logs (Ctrl+C to exit)"
    docker compose -f "$COMPOSE_FILE" logs -f
}

stop_services() {
    print_header "Stopping Services"
    docker compose -f "$COMPOSE_FILE" down
    print_success "Services stopped"
}

# Main execution
cd "$PROJECT_ROOT"

case "${1:-deploy}" in
    build)
        check_requirements
        build_images
        ;;
    up|start)
        check_requirements
        start_services
        wait_for_healthy
        show_status
        ;;
    down|stop)
        stop_services
        ;;
    restart)
        stop_services
        start_services
        wait_for_healthy
        show_status
        ;;
    status|ps)
        show_status
        ;;
    logs)
        show_logs
        ;;
    logs-f|follow)
        follow_logs
        ;;
    deploy|"")
        check_requirements
        build_images
        start_services
        wait_for_healthy
        show_status
        print_header "Deployment Complete!"
        echo -e "BeatStitch is now running at: ${GREEN}http://localhost${NC}"
        echo -e "API available at: ${GREEN}http://localhost/api${NC}"
        echo ""
        echo "Useful commands:"
        echo "  View logs:    ./scripts/deploy.sh logs"
        echo "  Follow logs:  ./scripts/deploy.sh logs-f"
        echo "  Stop:         ./scripts/deploy.sh down"
        echo "  Status:       ./scripts/deploy.sh status"
        ;;
    *)
        echo "Usage: $0 {deploy|build|up|down|restart|status|logs|logs-f}"
        echo ""
        echo "Commands:"
        echo "  deploy   - Full deployment (build + start + health check)"
        echo "  build    - Build images only"
        echo "  up       - Start services (use existing images)"
        echo "  down     - Stop all services"
        echo "  restart  - Stop and start services"
        echo "  status   - Show service status"
        echo "  logs     - Show recent logs"
        echo "  logs-f   - Follow logs in real-time"
        exit 1
        ;;
esac
