#!/bin/bash
# BeatStitch Backup Script
#
# Creates backups of application data including:
#   - SQLite database
#   - Uploaded media files
#   - Derived/processed files
#   - Rendered outputs
#
# Usage:
#   ./scripts/backup.sh              # Create backup
#   ./scripts/backup.sh restore      # List available backups
#   ./scripts/backup.sh restore <timestamp>  # Restore specific backup
#
# Backups are stored in: ./backups/<timestamp>/

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
BACKUP_BASE="$PROJECT_ROOT/backups"

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

create_backup() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_dir="$BACKUP_BASE/$timestamp"

    print_header "Creating Backup: $timestamp"

    # Create backup directory
    mkdir -p "$backup_dir"

    # Check if services are running
    if ! docker compose -f "$COMPOSE_FILE" ps --quiet 2>/dev/null | grep -q .; then
        print_warning "Services are not running. Creating backup from volumes directly."
    fi

    # Backup SQLite database
    echo "Backing up database..."
    if docker compose -f "$COMPOSE_FILE" exec -T backend test -f /data/db/beatstitch.db 2>/dev/null; then
        # Create a consistent backup using sqlite3 .backup command if available
        docker compose -f "$COMPOSE_FILE" exec -T backend sh -c \
            'if command -v sqlite3 > /dev/null; then
                sqlite3 /data/db/beatstitch.db ".backup /tmp/beatstitch_backup.db" && cat /tmp/beatstitch_backup.db
            else
                cat /data/db/beatstitch.db
            fi' > "$backup_dir/beatstitch.db" 2>/dev/null || {
            # Fallback: copy directly from volume
            docker run --rm -v beatstitch_data:/data -v "$backup_dir:/backup" alpine \
                cp /data/db/beatstitch.db /backup/beatstitch.db 2>/dev/null || {
                print_warning "Could not backup database"
            }
        }
        if [ -f "$backup_dir/beatstitch.db" ]; then
            print_success "Database backed up: $(du -h "$backup_dir/beatstitch.db" | cut -f1)"
        fi
    else
        print_warning "Database file not found"
    fi

    # Backup uploads directory (media files)
    echo "Backing up uploads..."
    docker run --rm -v beatstitch_data:/data -v "$backup_dir:/backup" alpine \
        sh -c 'if [ -d /data/uploads ]; then tar czf /backup/uploads.tar.gz -C /data uploads; fi' 2>/dev/null || {
        print_warning "Could not backup uploads"
    }
    if [ -f "$backup_dir/uploads.tar.gz" ]; then
        print_success "Uploads backed up: $(du -h "$backup_dir/uploads.tar.gz" | cut -f1)"
    fi

    # Backup derived files (thumbnails, waveforms, etc.)
    echo "Backing up derived files..."
    docker run --rm -v beatstitch_data:/data -v "$backup_dir:/backup" alpine \
        sh -c 'if [ -d /data/derived ]; then tar czf /backup/derived.tar.gz -C /data derived; fi' 2>/dev/null || {
        print_warning "Could not backup derived files"
    }
    if [ -f "$backup_dir/derived.tar.gz" ]; then
        print_success "Derived files backed up: $(du -h "$backup_dir/derived.tar.gz" | cut -f1)"
    fi

    # Backup outputs (rendered videos)
    echo "Backing up outputs..."
    docker run --rm -v beatstitch_data:/data -v "$backup_dir:/backup" alpine \
        sh -c 'if [ -d /data/outputs ]; then tar czf /backup/outputs.tar.gz -C /data outputs; fi' 2>/dev/null || {
        print_warning "Could not backup outputs"
    }
    if [ -f "$backup_dir/outputs.tar.gz" ]; then
        print_success "Outputs backed up: $(du -h "$backup_dir/outputs.tar.gz" | cut -f1)"
    fi

    # Create backup manifest
    cat > "$backup_dir/manifest.txt" << EOF
BeatStitch Backup Manifest
===========================
Timestamp: $timestamp
Date: $(date)
Hostname: $(hostname)

Contents:
EOF

    # Add file listing to manifest
    ls -lh "$backup_dir" >> "$backup_dir/manifest.txt"

    # Calculate total size
    local total_size=$(du -sh "$backup_dir" | cut -f1)

    print_header "Backup Complete"
    print_success "Backup location: $backup_dir"
    print_success "Total size: $total_size"
    echo ""
    echo "Files created:"
    ls -lh "$backup_dir"

    # Clean up old backups (keep last 7)
    echo ""
    local backup_count=$(ls -1 "$BACKUP_BASE" 2>/dev/null | wc -l)
    if [ "$backup_count" -gt 7 ]; then
        print_warning "Cleaning up old backups (keeping last 7)..."
        ls -1t "$BACKUP_BASE" | tail -n +8 | while read old_backup; do
            rm -rf "$BACKUP_BASE/$old_backup"
            echo "  Removed: $old_backup"
        done
    fi
}

list_backups() {
    print_header "Available Backups"

    if [ ! -d "$BACKUP_BASE" ] || [ -z "$(ls -A "$BACKUP_BASE" 2>/dev/null)" ]; then
        print_warning "No backups found in $BACKUP_BASE"
        return 1
    fi

    echo "Timestamp            Size     Contents"
    echo "-------------------  -------  --------"

    for backup in $(ls -1t "$BACKUP_BASE"); do
        local size=$(du -sh "$BACKUP_BASE/$backup" 2>/dev/null | cut -f1)
        local contents=""
        [ -f "$BACKUP_BASE/$backup/beatstitch.db" ] && contents="${contents}db "
        [ -f "$BACKUP_BASE/$backup/uploads.tar.gz" ] && contents="${contents}uploads "
        [ -f "$BACKUP_BASE/$backup/derived.tar.gz" ] && contents="${contents}derived "
        [ -f "$BACKUP_BASE/$backup/outputs.tar.gz" ] && contents="${contents}outputs"
        printf "%-19s  %-7s  %s\n" "$backup" "$size" "$contents"
    done

    echo ""
    echo "To restore a backup: ./scripts/backup.sh restore <timestamp>"
}

restore_backup() {
    local timestamp="$1"
    local backup_dir="$BACKUP_BASE/$timestamp"

    if [ -z "$timestamp" ]; then
        list_backups
        return 0
    fi

    if [ ! -d "$backup_dir" ]; then
        print_error "Backup not found: $timestamp"
        list_backups
        return 1
    fi

    print_header "Restore Backup: $timestamp"
    print_warning "This will OVERWRITE existing data!"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled."
        return 0
    fi

    # Stop services
    echo ""
    echo "Stopping services..."
    docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true

    # Restore database
    if [ -f "$backup_dir/beatstitch.db" ]; then
        echo "Restoring database..."
        docker run --rm -v beatstitch_data:/data -v "$backup_dir:/backup" alpine \
            sh -c 'mkdir -p /data/db && cp /backup/beatstitch.db /data/db/beatstitch.db'
        print_success "Database restored"
    fi

    # Restore uploads
    if [ -f "$backup_dir/uploads.tar.gz" ]; then
        echo "Restoring uploads..."
        docker run --rm -v beatstitch_data:/data -v "$backup_dir:/backup" alpine \
            sh -c 'rm -rf /data/uploads && tar xzf /backup/uploads.tar.gz -C /data'
        print_success "Uploads restored"
    fi

    # Restore derived files
    if [ -f "$backup_dir/derived.tar.gz" ]; then
        echo "Restoring derived files..."
        docker run --rm -v beatstitch_data:/data -v "$backup_dir:/backup" alpine \
            sh -c 'rm -rf /data/derived && tar xzf /backup/derived.tar.gz -C /data'
        print_success "Derived files restored"
    fi

    # Restore outputs
    if [ -f "$backup_dir/outputs.tar.gz" ]; then
        echo "Restoring outputs..."
        docker run --rm -v beatstitch_data:/data -v "$backup_dir:/backup" alpine \
            sh -c 'rm -rf /data/outputs && tar xzf /backup/outputs.tar.gz -C /data'
        print_success "Outputs restored"
    fi

    print_header "Restore Complete"
    echo "You can now start services with: ./scripts/deploy.sh up"
}

# Main execution
cd "$PROJECT_ROOT"

case "${1:-backup}" in
    backup|"")
        create_backup
        ;;
    restore)
        restore_backup "$2"
        ;;
    list)
        list_backups
        ;;
    *)
        echo "Usage: $0 {backup|restore [timestamp]|list}"
        echo ""
        echo "Commands:"
        echo "  backup              - Create a new backup"
        echo "  list                - List available backups"
        echo "  restore             - List backups and restore instructions"
        echo "  restore <timestamp> - Restore specific backup"
        exit 1
        ;;
esac
