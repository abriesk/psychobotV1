#!/bin/bash
# scripts/manage.sh - PsychoBot Management Script
# Usage: ./scripts/manage.sh [command] [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKUP_DIR="./backups"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

# Detect compose command (docker-compose vs docker compose)
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

print_header() {
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${BLUE}  PsychoBot Management Script${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo ""
}

print_usage() {
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  start [dev|prod]    Start services (default: prod)"
    echo "  stop                Stop all services"
    echo "  restart [service]   Restart all or specific service"
    echo "  logs [service]      View logs (optional: specific service)"
    echo "  status              Show container status"
    echo "  backup              Backup PostgreSQL database"
    echo "  restore [file]      Restore from backup file"
    echo "  shell [service]     Open shell in container"
    echo "  migrate             Run database migrations"
    echo "  rebuild [service]   Rebuild and restart service"
    echo "  clean               Remove stopped containers and unused images"
    echo ""
    echo "Examples:"
    echo "  $0 start dev        # Start in development mode"
    echo "  $0 logs bot         # View bot logs"
    echo "  $0 backup           # Create database backup"
    echo "  $0 restart web      # Restart only web service"
}

cmd_start() {
    local mode="${1:-prod}"
    
    if [ "$mode" == "dev" ]; then
        COMPOSE_FILE="docker-compose.dev.yml"
        echo -e "${YELLOW}Starting in DEVELOPMENT mode...${NC}"
    else
        COMPOSE_FILE="docker-compose.prod.yml"
        echo -e "${GREEN}Starting in PRODUCTION mode...${NC}"
    fi
    
    # Create data directories if they don't exist
    mkdir -p ./data/postgres ./data/npm/data ./data/npm/letsencrypt ./landings
    
    $COMPOSE_CMD -f $COMPOSE_FILE up -d
    
    echo ""
    echo -e "${GREEN}✅ Services started!${NC}"
    echo ""
    cmd_status
}

cmd_stop() {
    echo -e "${YELLOW}Stopping all services...${NC}"
    $COMPOSE_CMD -f $COMPOSE_FILE down
    echo -e "${GREEN}✅ Services stopped${NC}"
}

cmd_restart() {
    local service="$1"
    
    if [ -n "$service" ]; then
        echo -e "${YELLOW}Restarting $service...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE restart "$service"
    else
        echo -e "${YELLOW}Restarting all services...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE restart
    fi
    
    echo -e "${GREEN}✅ Restart complete${NC}"
}

cmd_logs() {
    local service="$1"
    
    if [ -n "$service" ]; then
        $COMPOSE_CMD -f $COMPOSE_FILE logs -f --tail=100 "$service"
    else
        $COMPOSE_CMD -f $COMPOSE_FILE logs -f --tail=100
    fi
}

cmd_status() {
    echo -e "${BLUE}Container Status:${NC}"
    echo ""
    $COMPOSE_CMD -f $COMPOSE_FILE ps
    echo ""
    
    # Check if services are healthy
    echo -e "${BLUE}Health Check:${NC}"
    
    if docker exec psychobot-db pg_isready -U postgres &> /dev/null; then
        echo -e "  Database:  ${GREEN}✅ Healthy${NC}"
    else
        echo -e "  Database:  ${RED}❌ Unhealthy${NC}"
    fi
    
    if curl -s http://localhost:8000/health &> /dev/null; then
        echo -e "  Web API:   ${GREEN}✅ Healthy${NC}"
    else
        echo -e "  Web API:   ${YELLOW}⚠️  Not accessible (may be behind NPM)${NC}"
    fi
    
    if docker exec psychobot-bot pgrep -f "app.main" &> /dev/null; then
        echo -e "  Telegram:  ${GREEN}✅ Running${NC}"
    else
        echo -e "  Telegram:  ${RED}❌ Not running${NC}"
    fi
}

cmd_backup() {
    mkdir -p "$BACKUP_DIR"
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${BACKUP_DIR}/psychobot_backup_${timestamp}.sql"
    
    echo -e "${YELLOW}Creating database backup...${NC}"
    
    docker exec psychobot-db pg_dump -U postgres psychobot > "$backup_file"
    
    # Compress
    gzip "$backup_file"
    
    echo -e "${GREEN}✅ Backup created: ${backup_file}.gz${NC}"
    
    # Show backup size
    ls -lh "${backup_file}.gz"
    
    # Keep only last 10 backups
    echo ""
    echo -e "${YELLOW}Cleaning old backups (keeping last 10)...${NC}"
    ls -t ${BACKUP_DIR}/psychobot_backup_*.sql.gz 2>/dev/null | tail -n +11 | xargs -r rm
    
    echo ""
    echo -e "${BLUE}Available backups:${NC}"
    ls -lht ${BACKUP_DIR}/psychobot_backup_*.sql.gz 2>/dev/null | head -5
}

cmd_restore() {
    local backup_file="$1"
    
    if [ -z "$backup_file" ]; then
        echo -e "${YELLOW}Available backups:${NC}"
        ls -lht ${BACKUP_DIR}/psychobot_backup_*.sql.gz 2>/dev/null
        echo ""
        echo "Usage: $0 restore <backup_file>"
        exit 1
    fi
    
    if [ ! -f "$backup_file" ]; then
        echo -e "${RED}❌ Backup file not found: $backup_file${NC}"
        exit 1
    fi
    
    echo -e "${RED}⚠️  WARNING: This will OVERWRITE the current database!${NC}"
    read -p "Are you sure? (type 'yes' to confirm): " confirm
    
    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled."
        exit 0
    fi
    
    echo -e "${YELLOW}Restoring from $backup_file...${NC}"
    
    # Decompress if gzipped
    if [[ "$backup_file" == *.gz ]]; then
        gunzip -c "$backup_file" | docker exec -i psychobot-db psql -U postgres psychobot
    else
        cat "$backup_file" | docker exec -i psychobot-db psql -U postgres psychobot
    fi
    
    echo -e "${GREEN}✅ Database restored!${NC}"
}

cmd_shell() {
    local service="${1:-bot}"
    
    echo -e "${YELLOW}Opening shell in $service...${NC}"
    docker exec -it "psychobot-${service}" /bin/bash || docker exec -it "psychobot-${service}" /bin/sh
}

cmd_migrate() {
    echo -e "${YELLOW}Running database migrations...${NC}"
    
    docker exec psychobot-bot alembic upgrade head
    
    echo -e "${GREEN}✅ Migrations complete${NC}"
}

cmd_rebuild() {
    local service="$1"
    
    if [ -n "$service" ]; then
        echo -e "${YELLOW}Rebuilding $service...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE build --no-cache "$service"
        $COMPOSE_CMD -f $COMPOSE_FILE up -d "$service"
    else
        echo -e "${YELLOW}Rebuilding all services...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE build --no-cache
        $COMPOSE_CMD -f $COMPOSE_FILE up -d
    fi
    
    echo -e "${GREEN}✅ Rebuild complete${NC}"
}

cmd_clean() {
    echo -e "${YELLOW}Cleaning up Docker resources...${NC}"
    
    # Remove stopped containers
    docker container prune -f
    
    # Remove unused images
    docker image prune -f
    
    # Remove unused volumes (BE CAREFUL!)
    echo ""
    echo -e "${RED}⚠️  Remove unused volumes? This may delete data!${NC}"
    read -p "Type 'yes' to remove unused volumes: " confirm
    
    if [ "$confirm" == "yes" ]; then
        docker volume prune -f
    fi
    
    echo -e "${GREEN}✅ Cleanup complete${NC}"
}

# Main
print_header

case "${1:-}" in
    start)
        cmd_start "$2"
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart "$2"
        ;;
    logs)
        cmd_logs "$2"
        ;;
    status)
        cmd_status
        ;;
    backup)
        cmd_backup
        ;;
    restore)
        cmd_restore "$2"
        ;;
    shell)
        cmd_shell "$2"
        ;;
    migrate)
        cmd_migrate
        ;;
    rebuild)
        cmd_rebuild "$2"
        ;;
    clean)
        cmd_clean
        ;;
    *)
        print_usage
        exit 1
        ;;
esac
