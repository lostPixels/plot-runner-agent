#!/bin/bash

# Quick Virtual Environment Fix for NextDraw API
# Run this directly on the Raspberry Pi to fix missing venv

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
APP_DIR="/home/james/plot-runner-agent"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="nextdraw-api"
USER="james"

echo "NextDraw API Virtual Environment Quick Fix"
echo "=========================================="
echo

# Stop service
echo -e "${YELLOW}Stopping service...${NC}"
sudo systemctl stop $SERVICE_NAME 2>/dev/null || true

# Remove broken venv if exists
if [ -d "$VENV_DIR" ] && [ ! -f "$VENV_DIR/bin/python" ]; then
    echo -e "${YELLOW}Removing broken virtual environment...${NC}"
    rm -rf "$VENV_DIR"
fi

# Create virtual environment
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo -e "${GREEN}Creating virtual environment...${NC}"
    cd "$APP_DIR"
    python3 -m venv "$VENV_DIR"

    # Activate and upgrade pip
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip setuptools wheel

    # Install requirements
    if [ -f "requirements.txt" ]; then
        echo -e "${GREEN}Installing requirements...${NC}"
        pip install -r requirements.txt
    else
        echo -e "${YELLOW}No requirements.txt found, installing basic dependencies...${NC}"
        pip install Flask Flask-CORS gunicorn requests watchdog python-dateutil
    fi

    # Try to install NextDraw
    echo -e "${GREEN}Installing NextDraw library...${NC}"
    pip install https://software-download.bantamtools.com/nd/api/nextdraw_api.zip || echo -e "${YELLOW}NextDraw installation failed (may work without plotter)${NC}"

    deactivate
else
    echo -e "${GREEN}Virtual environment already exists${NC}"
fi

# Fix permissions
echo -e "${GREEN}Fixing permissions...${NC}"
sudo chown -R $USER:$USER "$APP_DIR"

# Test imports
echo -e "${GREEN}Testing Python imports...${NC}"
cd "$APP_DIR"
$VENV_DIR/bin/python -c "
import sys
print(f'Python: {sys.version.split()[0]}')
try:
    import flask
    print('✓ Flask OK')
except: print('✗ Flask MISSING')
try:
    from app import app
    print('✓ app.py OK')
except Exception as e: print(f'✗ app.py ERROR: {e}')
"

# Start service
echo -e "${GREEN}Starting service...${NC}"
sudo systemctl daemon-reload
sudo systemctl start $SERVICE_NAME

# Check status
sleep 3
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}✓ Service is running!${NC}"

    # Test API
    echo -e "${GREEN}Testing API...${NC}"
    if curl -s http://localhost:5000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API is responding!${NC}"
        echo
        echo -e "${GREEN}SUCCESS! Access the API at:${NC}"
        echo "  http://$(hostname -I | awk '{print $1}')/"
    else
        echo -e "${RED}✗ API not responding${NC}"
    fi
else
    echo -e "${RED}✗ Service failed to start${NC}"
    echo
    echo "Check logs with:"
    echo "  sudo journalctl -u $SERVICE_NAME -n 50"
fi

echo
echo "Done!"
