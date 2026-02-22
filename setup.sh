#!/bin/bash

# =============================================================================
# BeatStitch Setup Script
# =============================================================================
# Interactive setup script for managing the BeatStitch development environment
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Project directory (where this script is located)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# =============================================================================
# Helper Functions
# =============================================================================

print_header() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if docker daemon is running (tries without sudo first, falls back to sudo)
docker_is_running() {
    docker info >/dev/null 2>&1 || sudo docker info >/dev/null 2>&1
}

# Check if docker is accessible WITHOUT sudo (i.e. user is in docker group)
docker_accessible_without_sudo() {
    docker info >/dev/null 2>&1
}

# Re-exec this script with docker group active so the user never has to
# manually run "newgrp docker". Uses 'sg' (part of shadow-utils / login).
reexec_with_docker_group() {
    if command_exists sg; then
        print_info "Applying docker group to this session automatically..."
        sleep 1
        exec sg docker "$0"
    else
        # sg not available (some minimal distros); give clear manual instruction
        echo ""
        echo -e "${YELLOW}Run the following command to apply the group, then re-run setup:${NC}"
        echo -e "         ${CYAN}newgrp docker${NC}"
        echo ""
        exit 0
    fi
}

# Get local IP address (not localhost)
get_local_ip() {
    local ip=""

    # Try different methods to get local IP
    if command_exists ip; then
        # Linux with ip command - get the default route interface IP
        ip=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[\d.]+' | head -1)
    fi

    if [ -z "$ip" ] && command_exists hostname; then
        # Try hostname -I (Linux)
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi

    if [ -z "$ip" ] && command_exists ifconfig; then
        # macOS / BSD fallback
        ip=$(ifconfig 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | head -1)
    fi

    # Final fallback
    if [ -z "$ip" ]; then
        ip="127.0.0.1"
    fi

    echo "$ip"
}

# =============================================================================
# Requirements Installation
# =============================================================================

install_requirements() {
    print_header "Installing Requirements"

    local os_type=""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        os_type="macos"
    elif [[ -f /etc/os-release ]]; then
        . /etc/os-release
        os_type="$ID"   # e.g. ubuntu, debian, fedora, centos, rhel
    else
        print_error "Unsupported OS. Please install Docker manually: https://docs.docker.com/get-docker/"
        return 1
    fi

    # ── Docker ────────────────────────────────────────────────────────────────
    if command_exists docker; then
        print_success "Docker already installed – skipping"
    else
        print_info "Installing Docker..."
        case "$os_type" in
            macos)
                if command_exists brew; then
                    brew install --cask docker
                    print_success "Docker Desktop installed via Homebrew"
                    print_warning "Open Docker Desktop once to finish setup, then re-run this script"
                    return 0
                else
                    print_error "Homebrew not found. Install it first: https://brew.sh"
                    print_info "Or install Docker Desktop manually: https://docs.docker.com/desktop/mac/"
                    return 1
                fi
                ;;
            ubuntu|debian|raspbian|linuxmint|pop)
                print_info "Using official Docker install script (requires sudo)..."
                curl -fsSL https://get.docker.com | sudo sh
                sudo usermod -aG docker "$USER"
                print_success "Docker installed"
                print_warning "Log out and back in (or run: newgrp docker) for group changes to take effect"
                ;;
            fedora)
                sudo dnf -y install dnf-plugins-core
                sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
                sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
                sudo usermod -aG docker "$USER"
                print_success "Docker installed"
                ;;
            centos|rhel|rocky|almalinux)
                sudo yum install -y yum-utils
                sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
                sudo yum -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
                sudo usermod -aG docker "$USER"
                print_success "Docker installed"
                ;;
            arch|manjaro)
                sudo pacman -Sy --noconfirm docker docker-compose
                sudo usermod -aG docker "$USER"
                print_success "Docker installed"
                ;;
            *)
                print_error "Auto-install not supported for OS: $os_type"
                print_info "Please install Docker manually: https://docs.docker.com/get-docker/"
                return 1
                ;;
        esac
    fi

    # ── Docker Compose ────────────────────────────────────────────────────────
    if command_exists docker-compose || docker compose version >/dev/null 2>&1; then
        print_success "Docker Compose already available – skipping"
    else
        print_info "Installing Docker Compose plugin..."
        case "$os_type" in
            macos)
                # Already handled with Docker Desktop above
                ;;
            ubuntu|debian|raspbian|linuxmint|pop)
                sudo apt-get update -qq
                sudo apt-get install -y docker-compose-plugin
                print_success "Docker Compose plugin installed"
                ;;
            fedora|centos|rhel|rocky|almalinux)
                # Already installed with Docker above; fall back to standalone
                sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
                    -o /usr/local/bin/docker-compose
                sudo chmod +x /usr/local/bin/docker-compose
                print_success "Docker Compose standalone installed"
                ;;
            arch|manjaro)
                # Already installed with Docker above
                ;;
        esac
    fi

    # ── Start Docker daemon ───────────────────────────────────────────────────
    if [[ "$os_type" != "macos" ]]; then
        if ! docker_is_running 2>/dev/null; then
            print_info "Starting Docker daemon (requires sudo)..."
            sudo systemctl enable docker 2>/dev/null || true
            sudo systemctl start docker  2>/dev/null || true
            sleep 3
            if docker_is_running; then
                print_success "Docker daemon started"
            else
                print_warning "Could not start Docker daemon automatically"
                print_info "Try manually: sudo systemctl start docker"
            fi
        else
            print_success "Docker daemon is already running"
        fi
    fi

    # ── Python packages ───────────────────────────────────────────────────────
    local req_file="$SCRIPT_DIR/tools/requirements.txt"
    if [[ -f "$req_file" ]]; then
        print_info "Installing Python packages from tools/requirements.txt ..."
        local pip_cmd
        if [[ -n "${VIRTUAL_ENV:-}" ]]; then
            pip_cmd="$VIRTUAL_ENV/bin/pip"
        else
            pip_cmd="pip3"
        fi
        if $pip_cmd install -r "$req_file"; then
            print_success "Python packages installed"
        else
            print_warning "pip install failed — check that pip/virtualenv is available"
        fi
    else
        print_info "No tools/requirements.txt found — skipping Python packages"
    fi

    echo ""
    print_success "All requirements installed!"
    echo ""

    # If docker is now running but not yet accessible without sudo,
    # re-exec automatically with the docker group applied.
    if docker_is_running && ! docker_accessible_without_sudo; then
        print_info "Applying docker group to this session..."
        sudo usermod -aG docker "$USER" 2>/dev/null || true
        reexec_with_docker_group
    fi
}

# =============================================================================
# Prerequisites Check
# =============================================================================

check_prerequisites() {
    print_header "Checking Prerequisites"

    local missing_installs=0   # Docker / Compose binary missing
    local daemon_down=0        # Binaries OK but daemon not running

    # Check Docker binary
    if command_exists docker; then
        print_success "Docker is installed"
    else
        print_error "Docker is not installed"
        echo "        Please install Docker: https://docs.docker.com/get-docker/"
        missing_installs=1
    fi

    # Check Docker Compose
    if command_exists docker-compose || docker compose version >/dev/null 2>&1; then
        print_success "Docker Compose is available"
    else
        print_error "Docker Compose is not installed"
        echo "        Please install Docker Compose: https://docs.docker.com/compose/install/"
        missing_installs=1
    fi

    # Check Docker daemon (only meaningful if Docker binary is present)
    if [ $missing_installs -eq 0 ]; then
        if docker_is_running; then
            print_success "Docker daemon is running"
        else
            print_error "Docker daemon is not running"
            daemon_down=1
        fi
    fi

    # ── Nothing wrong ─────────────────────────────────────────────────────────
    if [ $missing_installs -eq 0 ] && [ $daemon_down -eq 0 ]; then
        return 0
    fi

    echo ""

    # ── Only the daemon is down (binaries are fine) ───────────────────────────
    if [ $missing_installs -eq 0 ] && [ $daemon_down -eq 1 ]; then
        # First check: maybe the daemon IS running but this user lacks socket access
        if sudo docker info >/dev/null 2>&1; then
            print_warning "Docker daemon is running but your user cannot reach it"
            print_info "Your user is not yet in the 'docker' group (or the group change"
            print_info "hasn't been applied to this shell session)."
            echo ""
            print_info "Fixing group membership now (requires sudo)..."
            sudo usermod -aG docker "$USER" 2>/dev/null || true
            reexec_with_docker_group
        fi

        print_warning "Docker is installed but the daemon is not running"
        echo ""
        read -p "$(echo -e "${YELLOW}Would you like to start the Docker daemon now? (y/N): ${NC}")" start_daemon
        if [[ "$start_daemon" =~ ^[Yy]$ ]]; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                print_info "Opening Docker Desktop..."
                open -a Docker 2>/dev/null || print_warning "Could not open Docker Desktop automatically"
                print_info "Waiting 15 seconds for Docker Desktop to start..."
                sleep 15
            else
                print_info "Starting Docker daemon (requires sudo)..."
                sudo systemctl enable docker 2>/dev/null || true
                sudo systemctl start docker  2>/dev/null || true
                sleep 3
            fi

            if sudo docker info >/dev/null 2>&1; then
                print_success "Docker daemon is running"
                # Check if user can reach it without sudo
                if ! docker_accessible_without_sudo; then
                    echo ""
                    print_warning "Docker requires sudo in this shell (group change not yet active)"
                    sudo usermod -aG docker "$USER" 2>/dev/null || true
                    reexec_with_docker_group
                fi
                return 0
            else
                print_warning "Docker daemon still not responding"
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    print_info "Please open Docker Desktop manually and wait for it to finish starting"
                else
                    print_info "Check daemon status: sudo systemctl status docker"
                    print_info "View logs:           sudo journalctl -u docker --no-pager -n 20"
                fi
                return 1
            fi
        else
            print_error "Docker daemon must be running to continue"
            return 1
        fi
    fi

    # ── One or more binaries are missing ─────────────────────────────────────
    print_error "Missing software detected"
    echo ""
    read -p "$(echo -e "${YELLOW}Would you like to install missing requirements automatically? (y/N): ${NC}")" auto_install
    if [[ "$auto_install" =~ ^[Yy]$ ]]; then
        install_requirements
        echo ""
        print_info "Re-checking prerequisites..."
        echo ""
        local recheck_missing=0
        command_exists docker          || recheck_missing=1
        { command_exists docker-compose || docker compose version >/dev/null 2>&1; } || recheck_missing=1
        docker_is_running              || recheck_missing=1
        if [ $recheck_missing -eq 0 ]; then
            print_success "All prerequisites satisfied!"
            return 0
        else
            print_warning "Some prerequisites are still missing (a re-login may be required)"
            print_info "Try: newgrp docker   (or open a new terminal and re-run this script)"
            return 1
        fi
    else
        print_error "Please install missing dependencies and try again"
        return 1
    fi
}

# =============================================================================
# Environment Setup
# =============================================================================

setup_environment() {
    print_header "Setting Up Environment"

    # Always recreate .env from .env.example
    if [ -f .env.example ]; then
        cp .env.example .env
        print_success "Created .env from .env.example"
    else
        print_error ".env.example not found!"
        return 1
    fi

    # Generate secure SECRET_KEY if it's still the default
    if grep -q "your-secret-key-min-32-chars-change-in-production" .env 2>/dev/null; then
        print_info "Generating secure SECRET_KEY..."
        SECRET_KEY=$(openssl rand -hex 32)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s/your-secret-key-min-32-chars-change-in-production/$SECRET_KEY/" .env
        else
            # Linux
            sed -i "s/your-secret-key-min-32-chars-change-in-production/$SECRET_KEY/" .env
        fi
        print_success "Generated and set secure SECRET_KEY"
    else
        print_info "SECRET_KEY already configured"
    fi

    return 0
}

# =============================================================================
# Container Management
# =============================================================================

start_containers() {
    print_header "Starting Docker Containers (Quick Rebuild)"

    # Determine docker compose command
    local compose_cmd
    if docker compose version >/dev/null 2>&1; then
        compose_cmd="docker compose"
    else
        compose_cmd="docker-compose"
    fi

    print_info "Building and starting containers (preserving data)..."
    echo ""

    $compose_cmd up -d --build

    echo ""
    print_success "Containers started successfully!"

    # Wait for services to be ready
    print_info "Waiting for services to initialize (10 seconds)..."
    sleep 10

    # Run database migrations
    print_info "Running database migrations..."
    if $compose_cmd exec -T backend alembic upgrade head 2>/dev/null; then
        print_success "Database migrations completed!"
    else
        print_warning "Could not run migrations (backend may still be starting)"
        print_info "You can run migrations manually: docker compose exec backend alembic upgrade head"
    fi

    return 0
}

full_reset() {
    print_header "Full Reset (Wipe Everything)"

    # Determine docker compose command
    local compose_cmd
    if docker compose version >/dev/null 2>&1; then
        compose_cmd="docker compose"
    else
        compose_cmd="docker-compose"
    fi

    echo -e "${RED}WARNING: This will delete ALL data including:${NC}"
    echo -e "  - Database (all users, projects, media)"
    echo -e "  - Uploaded files"
    echo -e "  - Redis data"
    echo -e "  - Docker build cache"
    echo ""
    read -p "Are you sure you want to continue? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Cancelled."
        return 0
    fi

    print_info "Stopping and removing containers and volumes..."
    $compose_cmd down -v

    print_info "Clearing Docker build cache..."
    docker builder prune -af 2>/dev/null || true

    print_info "Building and starting fresh containers..."
    echo ""

    $compose_cmd up -d --build

    echo ""
    print_success "Fresh environment created!"

    # Wait for services to be ready
    print_info "Waiting for services to initialize (15 seconds)..."
    sleep 15

    # Run database migrations
    print_info "Running database migrations..."
    if $compose_cmd exec -T backend alembic upgrade head 2>/dev/null; then
        print_success "Database migrations completed!"
    else
        print_warning "Could not run migrations (backend may still be starting)"
        print_info "You can run migrations manually: docker compose exec backend alembic upgrade head"
    fi

    return 0
}

stop_containers() {
    print_header "Stopping Docker Containers"

    local compose_cmd
    if docker compose version >/dev/null 2>&1; then
        compose_cmd="docker compose"
    else
        compose_cmd="docker-compose"
    fi

    $compose_cmd down

    print_success "Containers stopped successfully!"
    return 0
}

show_container_status() {
    print_header "Container Status"

    local compose_cmd
    if docker compose version >/dev/null 2>&1; then
        compose_cmd="docker compose"
    else
        compose_cmd="docker-compose"
    fi

    $compose_cmd ps

    return 0
}

# =============================================================================
# URL Display and Testing
# =============================================================================

display_urls() {
    print_header "Available URLs for Testing"

    # Get local IP address
    local LOCAL_IP=$(get_local_ip)
    echo -e "${BOLD}Local IP Address:${NC} ${CYAN}$LOCAL_IP${NC}"
    echo ""
    echo -e "${BOLD}Application URLs:${NC}"
    echo ""

    # Define URLs to check (using local IP)
    declare -a urls=(
        "http://${LOCAL_IP}:3001|Frontend (React UI)|Main application interface"
        "http://${LOCAL_IP}:8080|Backend API|FastAPI REST API base"
        "http://${LOCAL_IP}:8080/docs|API Documentation|Swagger/OpenAPI interactive docs"
        "http://${LOCAL_IP}:8080/redoc|API Documentation (ReDoc)|Alternative API documentation"
        "http://${LOCAL_IP}:8080/health|Health Check|Service health endpoint"
    )

    # Check each URL
    for url_entry in "${urls[@]}"; do
        IFS='|' read -r url name description <<< "$url_entry"

        # Try to get HTTP status
        if command_exists curl; then
            status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$url" 2>/dev/null || echo "000")
        else
            status="---"
        fi

        # Determine status color
        if [[ "$status" == "200" || "$status" == "301" || "$status" == "302" ]]; then
            status_color="${GREEN}[UP]${NC}"
            status_icon="OK"
        elif [[ "$status" == "000" ]]; then
            status_color="${RED}[DOWN]${NC}"
            status_icon="--"
        else
            status_color="${YELLOW}[HTTP $status]${NC}"
            status_icon="$status"
        fi

        echo -e "  $status_color ${BOLD}$name${NC}"
        echo -e "         URL: ${CYAN}$url${NC}"
        echo -e "         $description"
        echo ""
    done

    echo -e "${BOLD}Redis:${NC}"
    echo -e "         Host: ${CYAN}${LOCAL_IP}:6379${NC} (internal only)"
    echo -e "         Used for job queue and caching"
    echo ""

    echo -e "${BOLD}Authentication:${NC}"
    echo ""

    # Try to list existing users from the database
    local compose_cmd
    if docker compose version >/dev/null 2>&1; then
        compose_cmd="docker compose"
    else
        compose_cmd="docker-compose"
    fi

    # Query existing users
    local users_output
    users_output=$($compose_cmd exec -T backend python -c "
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.user import User

async def list_users():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.username, User.created_at).order_by(User.created_at))
        users = result.fetchall()
        for u in users:
            print(f'{u[0]}')

asyncio.run(list_users())
" 2>/dev/null)

    if [ -n "$users_output" ]; then
        echo -e "         ${BOLD}Existing Users:${NC}"
        while IFS= read -r username; do
            echo -e "           - ${GREEN}$username${NC}"
        done <<< "$users_output"
        echo ""
    else
        echo -e "         ${YELLOW}No users registered yet - you must register first!${NC}"
        echo ""
    fi

    echo -e "         ${CYAN}Register API:${NC} POST http://${LOCAL_IP}:8080/api/auth/register"
    echo -e "         ${CYAN}Login API:${NC}    POST http://${LOCAL_IP}:8080/api/auth/login"
    echo ""
    echo -e "         ${BOLD}Username requirements:${NC} 3-50 chars, alphanumeric + underscores"
    echo -e "         ${BOLD}Password requirements:${NC} 8-128 characters"
    echo ""
    echo -e "         ${CYAN}# Register a new user (example):${NC}"
    echo -e "         curl -X POST http://${LOCAL_IP}:8080/api/auth/register \\"
    echo -e "           -H 'Content-Type: application/json' \\"
    echo -e "           -d '{\"username\": \"demo\", \"password\": \"demo1234\"}'"
    echo ""
    echo -e "         ${CYAN}# Login and get token:${NC}"
    echo -e "         curl -X POST http://${LOCAL_IP}:8080/api/auth/login \\"
    echo -e "           -H 'Content-Type: application/json' \\"
    echo -e "           -d '{\"username\": \"demo\", \"password\": \"demo1234\"}'"
    echo ""

    echo -e "${BOLD}Quick Test Commands:${NC}"
    echo ""
    echo -e "  ${CYAN}# Test Backend Health${NC}"
    echo -e "  curl http://${LOCAL_IP}:8080/health"
    echo ""
    echo -e "  ${CYAN}# Open Frontend in Browser${NC}"
    echo -e "  open http://${LOCAL_IP}:3001    # macOS"
    echo -e "  xdg-open http://${LOCAL_IP}:3001    # Linux"
    echo ""
    echo -e "  ${CYAN}# View Container Logs${NC}"
    echo -e "  docker compose logs -f"
    echo -e "  docker compose logs -f backend"
    echo -e "  docker compose logs -f frontend"
    echo -e "  docker compose logs -f worker"
    echo ""

    return 0
}

# =============================================================================
# Main Menu
# =============================================================================

show_menu() {
    echo ""
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN}       BeatStitch Setup Menu${NC}"
    echo -e "${CYAN}============================================${NC}"
    echo ""
    echo -e "  ${BOLD}1)${NC} Quick start/rebuild"
    echo -e "     ${YELLOW}(Build & start containers, preserve data)${NC}"
    echo ""
    echo -e "  ${BOLD}2)${NC} Full reset (wipe everything)"
    echo -e "     ${RED}(Delete all data, rebuild from scratch)${NC}"
    echo ""
    echo -e "  ${BOLD}3)${NC} Display URLs for testing"
    echo -e "     ${YELLOW}(Show all available endpoints with status)${NC}"
    echo ""
    echo -e "  ${BOLD}4)${NC} Show container status"
    echo -e "     ${YELLOW}(Display running containers)${NC}"
    echo ""
    echo -e "  ${BOLD}5)${NC} Stop all containers"
    echo -e "     ${YELLOW}(Shut down all services)${NC}"
    echo ""
    echo -e "  ${BOLD}6)${NC} View logs"
    echo -e "     ${YELLOW}(Follow container logs)${NC}"
    echo ""
    echo -e "  ${BOLD}7)${NC} Run tests"
    echo -e "     ${GREEN}(Non-container local + container suites)${NC}"
    echo ""
    echo -e "  ${BOLD}8)${NC} Install requirements"
    echo -e "     ${CYAN}(Auto-install Docker & Docker Compose on a new machine)${NC}"
    echo ""
    echo -e "  ${BOLD}0)${NC} Exit"
    echo ""
    echo -e "${CYAN}============================================${NC}"
}

view_logs() {
    print_header "Container Logs"

    local compose_cmd
    if docker compose version >/dev/null 2>&1; then
        compose_cmd="docker compose"
    else
        compose_cmd="docker-compose"
    fi

    echo "Select service to view logs (or 'all' for all services):"
    echo ""
    echo "  1) All services"
    echo "  2) Backend"
    echo "  3) Frontend"
    echo "  4) Worker"
    echo "  5) Redis"
    echo "  0) Back to main menu"
    echo ""
    read -p "Enter choice: " log_choice

    case $log_choice in
        1)
            print_info "Showing all logs (Ctrl+C to stop)..."
            $compose_cmd logs -f
            ;;
        2)
            print_info "Showing backend logs (Ctrl+C to stop)..."
            $compose_cmd logs -f backend
            ;;
        3)
            print_info "Showing frontend logs (Ctrl+C to stop)..."
            $compose_cmd logs -f frontend
            ;;
        4)
            print_info "Showing worker logs (Ctrl+C to stop)..."
            $compose_cmd logs -f worker
            ;;
        5)
            print_info "Showing redis logs (Ctrl+C to stop)..."
            $compose_cmd logs -f redis
            ;;
        0)
            return 0
            ;;
        *)
            print_warning "Invalid choice"
            ;;
    esac
}

# =============================================================================
# Test Runner
# =============================================================================

run_tests() {
    print_header "Run Tests"

    # Python interpreter — respects active virtualenv
    local python_cmd
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        python_cmd="$VIRTUAL_ENV/bin/python"
    else
        python_cmd="python3"
    fi

    # Docker Compose command
    local compose_cmd
    if docker compose version >/dev/null 2>&1; then
        compose_cmd="docker compose"
    else
        compose_cmd="docker-compose"
    fi

    echo ""
    echo -e "  ${GREEN}${BOLD}── NON-CONTAINER  (runs directly on this host) ─────────────────${NC}"
    echo ""
    echo -e "  ${BOLD}1)${NC} Renderer unit tests       ${YELLOW}(no ffmpeg needed)${NC}"
    echo -e "     tools/tests/unit/"
    echo ""
    echo -e "  ${BOLD}2)${NC} Renderer all tests        ${YELLOW}(ffmpeg required for slow/golden/integration)${NC}"
    echo -e "     tools/ — unit + golden + integration"
    echo ""
    echo -e "  ${BOLD}3)${NC} EDL schema contract       ${YELLOW}(standalone, no backend app deps)${NC}"
    echo -e "     backend/tests/contract/test_schema_validation.py"
    echo ""
    echo -e "  ${BOLD}4)${NC} Contracts verifier        ${YELLOW}(standalone)${NC}"
    echo -e "     third_party/contracts/tools/verify_contracts.py"
    echo ""
    echo -e "  ${BOLD}5)${NC} ${GREEN}Run ALL non-container tests${NC}  (all of 1–4; slow tests auto-skip if no ffmpeg)"
    echo ""
    echo -e "  ${RED}${BOLD}── CONTAINER-REQUIRED  (start containers first: main menu → 1) ──${NC}"
    echo ""
    echo -e "  ${BOLD}6)${NC}  All container tests            backend + worker"
    echo -e "  ${BOLD}7)${NC}  Backend — all tests"
    echo -e "  ${BOLD}8)${NC}  Backend — unit tests only"
    echo -e "  ${BOLD}9)${NC}  Backend — integration tests only"
    echo -e "  ${BOLD}10)${NC} Backend — e2e tests only"
    echo -e "  ${BOLD}11)${NC} Backend — contract tests        determinism + roundtrip"
    echo -e "  ${BOLD}12)${NC} Worker — all tests"
    echo -e "  ${BOLD}13)${NC} Worker — unit tests only"
    echo -e "  ${BOLD}14)${NC} Worker — golden tests only"
    echo -e "  ${BOLD}15)${NC} AI contract tests              EditPlanV1 + AI endpoints + optional E2E"
    echo -e "  ${BOLD}16)${NC} Worker render_real integration  host-side, generates assets"
    echo ""
    echo -e "  ${BOLD}0)${NC}  Back to main menu"
    echo ""
    read -p "Enter choice [0-16]: " test_choice

    local _rc

    case $test_choice in

        # ══════════════════════════════════════════════════════════════════════
        # NON-CONTAINER
        # ══════════════════════════════════════════════════════════════════════

        1)
            print_header "Renderer Unit Tests (no ffmpeg)"
            if $python_cmd -m pytest tools/tests/unit/ -v --tb=short; then
                print_success "Renderer unit tests PASSED"
            else
                print_warning "Renderer unit tests FAILED"
            fi
            ;;

        2)
            print_header "Renderer All Tests (ffmpeg required for slow tests)"
            if $python_cmd -m pytest -v --tb=short; then
                print_success "Renderer all tests PASSED"
            else
                print_warning "Renderer all tests FAILED"
            fi
            ;;

        3)
            print_header "EDL Schema Contract Tests (standalone)"
            if (cd "$SCRIPT_DIR/backend" && \
                $python_cmd -m pytest tests/contract/test_schema_validation.py \
                    --noconftest -v --tb=short); then
                print_success "EDL schema contract tests PASSED"
            else
                print_warning "EDL schema contract tests FAILED"
            fi
            ;;

        4)
            print_header "Contracts Verifier"
            if $python_cmd third_party/contracts/tools/verify_contracts.py; then
                print_success "Contracts verifier PASSED"
            else
                print_warning "Contracts verifier FAILED"
            fi
            ;;

        5)
            print_header "ALL Non-Container Tests"
            print_info "Slow tests auto-skip if ffmpeg is not on PATH."
            _rc=0
            echo ""
            print_info "── 1/3  Renderer tests (unit + golden + integration) ─────────────"
            if $python_cmd -m pytest -q --tb=short; then
                print_success "Renderer tests PASSED"
            else
                print_warning "Renderer tests FAILED"
                _rc=1
            fi
            echo ""
            print_info "── 2/3  EDL schema contract ──────────────────────────────────────"
            if (cd "$SCRIPT_DIR/backend" && \
                $python_cmd -m pytest tests/contract/test_schema_validation.py \
                    --noconftest -q --tb=short); then
                print_success "EDL schema contract PASSED"
            else
                print_warning "EDL schema contract FAILED"
                _rc=1
            fi
            echo ""
            print_info "── 3/3  Contracts verifier ───────────────────────────────────────"
            if $python_cmd third_party/contracts/tools/verify_contracts.py; then
                print_success "Contracts verifier PASSED"
            else
                print_warning "Contracts verifier FAILED"
                _rc=1
            fi
            echo ""
            if [[ $_rc -eq 0 ]]; then
                print_success "ALL non-container tests PASSED"
            else
                print_warning "One or more non-container tests FAILED (see output above)"
            fi
            ;;

        # ══════════════════════════════════════════════════════════════════════
        # CONTAINER-REQUIRED
        # ══════════════════════════════════════════════════════════════════════

        6|7|8|9|10|11|12|13|14|15|16)
            # Gate: containers must be running
            if ! $compose_cmd ps 2>/dev/null | grep -qE "Up|running"; then
                print_error "No containers are running."
                print_info  "Start them first: main menu → option 1"
                return 1
            fi

            case $test_choice in

                6)
                    print_header "All Container Tests (backend + worker)"
                    $compose_cmd exec -T backend pip install pytest pytest-asyncio jsonschema -q 2>/dev/null || true
                    $compose_cmd exec -T worker  pip install pytest -q 2>/dev/null || true
                    echo ""
                    print_info "── Backend ───────────────────────────────────────────────────"
                    if $compose_cmd exec -T backend python -m pytest tests/ -v --tb=short 2>&1; then
                        print_success "Backend PASSED"
                    else
                        print_warning "Backend FAILED"
                    fi
                    echo ""
                    print_info "── Worker ────────────────────────────────────────────────────"
                    if $compose_cmd exec -T -e PYTHONPATH=/app worker \
                            python -m pytest tests/ -v --tb=short 2>&1; then
                        print_success "Worker PASSED"
                    else
                        print_warning "Worker FAILED"
                    fi
                    ;;

                7)
                    print_header "Backend — All Tests"
                    $compose_cmd exec -T backend pip install pytest pytest-asyncio jsonschema -q 2>/dev/null || true
                    if $compose_cmd exec -T backend python -m pytest tests/ -v --tb=short 2>&1; then
                        print_success "Backend all tests PASSED"
                    else
                        print_warning "Backend all tests FAILED"
                    fi
                    ;;

                8)
                    print_header "Backend — Unit Tests"
                    $compose_cmd exec -T backend pip install pytest pytest-asyncio jsonschema -q 2>/dev/null || true
                    if $compose_cmd exec -T backend python -m pytest tests/unit/ -v --tb=short 2>&1; then
                        print_success "Backend unit tests PASSED"
                    else
                        print_warning "Backend unit tests FAILED"
                    fi
                    ;;

                9)
                    print_header "Backend — Integration Tests"
                    $compose_cmd exec -T backend pip install pytest pytest-asyncio jsonschema -q 2>/dev/null || true
                    if $compose_cmd exec -T backend python -m pytest tests/integration/ -v --tb=short 2>&1; then
                        print_success "Backend integration tests PASSED"
                    else
                        print_warning "Backend integration tests FAILED"
                    fi
                    ;;

                10)
                    print_header "Backend — E2E Tests"
                    $compose_cmd exec -T backend pip install pytest pytest-asyncio jsonschema -q 2>/dev/null || true
                    if $compose_cmd exec -T backend python -m pytest tests/e2e/ -v --tb=short 2>&1; then
                        print_success "Backend e2e tests PASSED"
                    else
                        print_warning "Backend e2e tests FAILED"
                    fi
                    ;;

                11)
                    print_header "Backend — Contract Tests (determinism + roundtrip)"
                    $compose_cmd exec -T backend pip install pytest pytest-asyncio jsonschema -q 2>/dev/null || true
                    if $compose_cmd exec -T backend python -m pytest \
                            tests/contract/determinism_test.py \
                            tests/contract/roundtrip_test.py \
                            -v --tb=short 2>&1; then
                        print_success "Backend contract tests PASSED"
                    else
                        print_warning "Backend contract tests FAILED"
                    fi
                    ;;

                12)
                    print_header "Worker — All Tests"
                    $compose_cmd exec -T worker pip install pytest -q 2>/dev/null || true
                    if $compose_cmd exec -T -e PYTHONPATH=/app worker \
                            python -m pytest tests/ -v --tb=short 2>&1; then
                        print_success "Worker all tests PASSED"
                    else
                        print_warning "Worker all tests FAILED"
                    fi
                    ;;

                13)
                    print_header "Worker — Unit Tests"
                    $compose_cmd exec -T worker pip install pytest -q 2>/dev/null || true
                    if $compose_cmd exec -T -e PYTHONPATH=/app worker \
                            python -m pytest tests/unit/ -v --tb=short 2>&1; then
                        print_success "Worker unit tests PASSED"
                    else
                        print_warning "Worker unit tests FAILED"
                    fi
                    ;;

                14)
                    print_header "Worker — Golden Tests"
                    $compose_cmd exec -T worker pip install pytest -q 2>/dev/null || true
                    if $compose_cmd exec -T -e PYTHONPATH=/app worker \
                            python -m pytest tests/golden/ -v --tb=short 2>&1; then
                        print_success "Worker golden tests PASSED"
                    else
                        print_warning "Worker golden tests FAILED"
                    fi
                    ;;

                15)
                    print_header "AI Contract Tests (EditPlanV1 + AI endpoints)"
                    $compose_cmd exec -T backend pip install pytest pytest-asyncio jsonschema -q 2>/dev/null || true
                    echo ""
                    print_info "── pytest: AI schema + endpoint tests ───────────────────────"
                    if $compose_cmd exec -T backend python -m pytest \
                            tests/integration/test_ai_endpoints.py \
                            tests/unit/test_edit_plan.py \
                            -v --tb=short 2>&1; then
                        print_success "AI pytest contract tests PASSED"
                    else
                        print_warning "AI pytest contract tests FAILED"
                    fi
                    echo ""
                    print_info "── validate_ai_contract.sh ──────────────────────────────────"
                    if [[ -n "${OPENAI_API_KEY:-}" ]]; then
                        print_info "OPENAI_API_KEY detected — E2E round-trip will run."
                    elif [[ "${RUN_OPENAI_ROUNDTRIP:-0}" == "1" ]]; then
                        print_info "RUN_OPENAI_ROUNDTRIP=1 — E2E round-trip with stub planner will run."
                    else
                        print_info "No OPENAI_API_KEY / RUN_OPENAI_ROUNDTRIP=1 — contract-only mode."
                        print_info "  To enable E2E: set OPENAI_API_KEY or RUN_OPENAI_ROUNDTRIP=1"
                    fi
                    if bash scripts/validate_ai_contract.sh 2>&1; then
                        print_success "validate_ai_contract.sh PASSED"
                    else
                        print_warning "validate_ai_contract.sh FAILED (see above)"
                    fi
                    ;;

                16)
                    print_header "Worker render_real Integration Tests"
                    print_info "Generating test assets and running host-side render_real tests..."
                    echo ""
                    bash "${SCRIPT_DIR}/scripts/run_integration_render_real.sh"
                    ;;

            esac
            ;;

        0)
            return 0
            ;;

        *)
            print_warning "Invalid choice. Please enter 0-17."
            ;;

    esac
}

# =============================================================================
# Main Script
# =============================================================================

main() {
    # If docker isn't accessible in the current session (user is in the docker
    # group but the group hasn't been applied yet), re-exec the whole script
    # under 'sg docker' so every option works without manual 'newgrp docker'.
    if ! docker_accessible_without_sudo; then
        reexec_with_docker_group
    fi

    clear
    echo ""
    echo -e "${CYAN}  ____             _   ____  _   _ _       _     ${NC}"
    echo -e "${CYAN} | __ )  ___  __ _| |_/ ___|| |_(_) |_ ___| |__  ${NC}"
    echo -e "${CYAN} |  _ \ / _ \/ _\` | __\___ \| __| | __/ __| '_ \ ${NC}"
    echo -e "${CYAN} | |_) |  __/ (_| | |_ ___) | |_| | || (__| | | |${NC}"
    echo -e "${CYAN} |____/ \___|\__,_|\__|____/ \__|_|\__\___|_| |_|${NC}"
    echo ""
    echo -e "${BOLD}       Beat-Synced Video Editor${NC}"
    echo ""

    while true; do
        show_menu
        read -p "Enter your choice [0-8]: " choice

        case $choice in
            1)
                if check_prerequisites; then
                    setup_environment
                    start_containers
                    echo ""
                    print_info "Environment is ready! Use option 3 to see available URLs."
                fi
                ;;
            2)
                if check_prerequisites; then
                    setup_environment
                    full_reset
                    echo ""
                    print_info "Fresh environment ready! Use option 3 to see available URLs."
                fi
                ;;
            3)
                display_urls
                ;;
            4)
                show_container_status
                ;;
            5)
                stop_containers
                ;;
            6)
                view_logs
                ;;
            7)
                run_tests
                ;;
            8)
                install_requirements
                ;;
            0)
                echo ""
                print_info "Goodbye!"
                echo ""
                exit 0
                ;;
            *)
                print_warning "Invalid option. Please enter 0-8."
                ;;
        esac

        echo ""
        read -p "Press Enter to continue..."
    done
}

# Run main function
main "$@"
