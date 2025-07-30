#!/bin/bash

# NextDraw Plotter API Service Fix Script
# This script updates the service configuration to match the current user and paths

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="nextdraw-api"
CURRENT_USER=$(whoami)
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/venv"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

# Banner
echo "=========================================="
echo "NextDraw API Service Fix Script"
echo "=========================================="
echo "Current user: $CURRENT_USER"
echo "App directory: $APP_DIR"
echo "Service file: $SERVICE_FILE"
echo

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    error "Service file not found: $SERVICE_FILE"
fi

# Create backup of service file
log "Creating backup of service file..."
sudo cp "$SERVICE_FILE" "$SERVICE_FILE.backup"
status_check $? "Failed to create backup"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    log "Virtual environment not found. Creating it..."
    python3 -m venv "$VENV_DIR"

    if [ $? -ne 0 ]; then
        warning "Failed to create virtual environment. Installing python3-venv..."
        sudo apt update
        sudo apt install -y python3-venv python3-full
        python3 -m venv "$VENV_DIR"
    fi
fi

# Install dependencies
log "Installing dependencies in virtual environment..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"

# Install NextDraw library
log "Installing NextDraw library..."
pip install --upgrade https://software-download.bantamtools.com/nd/api/nextdraw_api.zip

# Update service file
log "Updating service file to use current user and paths..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=NextDraw Plotter API Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$APP_DIR
Environment=PATH=$VENV_DIR/bin
ExecStart=$VENV_DIR/bin/gunicorn -c $APP_DIR/gunicorn.conf.py wsgi:application
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=mixed
Restart=always
RestartSec=5
TimeoutStopSec=30

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=$APP_DIR
ProtectHome=no

# Resource limits
LimitNOFILE=65536
MemoryMax=512M

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$APP_NAME

[Install]
WantedBy=multi-user.target
EOF

# Function to check status
status_check() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        error "$3"
    fi
}

# Reload daemon and restart service
log "Reloading systemd daemon..."
sudo systemctl daemon-reload
status_check $? "Daemon reloaded" "Failed to reload daemon"

log "Restarting service..."
sudo systemctl restart $APP_NAME
status_check $? "Service restarted" "Failed to restart service"

# Wait for service to start
sleep 3

# Check service status
log "Checking service status..."
if sudo systemctl is-active --quiet $APP_NAME; then
    log "Service is now running"
else
    warning "Service is not running. Checking logs..."
    sudo journalctl -u $APP_NAME -n 20
fi

# Check if we can connect to the API
log "Testing API connection..."
if curl -s http://localhost:5000/health > /dev/null; then
    log "API is responding on port 5000"
else
    warning "API is not responding on port 5000"
fi

# Check nginx configuration
log "Checking nginx configuration..."
if [ -f "/etc/nginx/sites-enabled/$APP_NAME" ]; then
    # Update nginx configuration if paths don't match
    if ! grep -q "$APP_DIR" "/etc/nginx/sites-enabled/$APP_NAME"; then
        log "Updating nginx configuration with correct paths..."
        sudo sed -i "s|/home/pi/plot-runner-agent|$APP_DIR|g" "/etc/nginx/sites-enabled/$APP_NAME"
        sudo nginx -t && sudo systemctl restart nginx
        status_check $? "Nginx configuration updated and restarted" "Failed to update nginx configuration"
    else
        log "Nginx configuration appears correct"
    fi
else
    warning "Nginx configuration not found"
fi

# Final status
echo
echo "===================================="
echo "Service Fix Completed"
echo "===================================="
echo
echo "Service status: $(systemctl is-active $APP_NAME)"
echo "Nginx status: $(systemctl is-active nginx)"
echo
echo "If you're still experiencing issues:"
echo "1. Check logs: sudo journalctl -u $APP_NAME -f"
echo "2. Verify nginx config: sudo nginx -t"
echo "3. Check if gunicorn is running: ps aux | grep gunicorn"
echo "4. Test direct API access: curl http://localhost:5000/health"
echo

exit 0
