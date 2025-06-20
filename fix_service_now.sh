#!/bin/bash

# NextDraw Plotter API - Quick Service Fix Script
# This script fixes service user/path issues causing 502 Bad Gateway errors

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get current user and directory
CURRENT_USER=$(whoami)
APP_DIR=$(pwd)
SERVICE_NAME="nextdraw-api"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}NextDraw Service Fix - Quick Fix Script${NC}"
echo -e "${GREEN}=========================================${NC}"
echo "Current user: $CURRENT_USER"
echo "App directory: $APP_DIR"
echo

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}ERROR: Service file not found at $SERVICE_FILE${NC}"
    exit 1
fi

# Create backup of service file
echo -e "${GREEN}Creating backup of service file...${NC}"
sudo cp "$SERVICE_FILE" "${SERVICE_FILE}.backup-$(date +%Y%m%d%H%M%S)"

# Update service file with correct user and paths
echo -e "${GREEN}Updating service file to use current user ($CURRENT_USER) and paths...${NC}"
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
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/gunicorn -c $APP_DIR/gunicorn.conf.py wsgi:application
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
ProtectHome=yes

# Resource limits
LimitNOFILE=65536
MemoryMax=512M

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd daemon
echo -e "${GREEN}Reloading systemd daemon...${NC}"
sudo systemctl daemon-reload

# Make sure venv exists and has gunicorn
if [ ! -d "$APP_DIR/venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating it...${NC}"
    python3 -m venv "$APP_DIR/venv"

    # Install requirements
    echo -e "${GREEN}Installing requirements...${NC}"
    source "$APP_DIR/venv/bin/activate"
    pip install --upgrade pip
    pip install gunicorn Flask

    if [ -f "$APP_DIR/requirements.txt" ]; then
        pip install -r "$APP_DIR/requirements.txt"
    fi

    # Try to install NextDraw API
    echo -e "${GREEN}Installing NextDraw API...${NC}"
    pip install https://software-download.bantamtools.com/nd/api/nextdraw_api.zip || true

    deactivate
else
    # Make sure gunicorn is installed
    if [ ! -f "$APP_DIR/venv/bin/gunicorn" ]; then
        echo -e "${YELLOW}Installing gunicorn in virtual environment...${NC}"
        source "$APP_DIR/venv/bin/activate"
        pip install gunicorn
        deactivate
    fi
fi

# Make sure wsgi.py exists
if [ ! -f "$APP_DIR/wsgi.py" ]; then
    echo -e "${YELLOW}Creating wsgi.py file...${NC}"
    cat > "$APP_DIR/wsgi.py" <<EOF
from app import app as application

if __name__ == "__main__":
    application.run()
EOF
fi

# Set permissions
echo -e "${GREEN}Setting correct permissions...${NC}"
sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$APP_DIR"
chmod +x "$APP_DIR/app.py" 2>/dev/null || true

# Restart the service
echo -e "${GREEN}Restarting service...${NC}"
sudo systemctl restart $SERVICE_NAME

# Check if service started successfully
sleep 2
if sudo systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}✓ Service started successfully!${NC}"
else
    echo -e "${RED}✗ Service failed to start.${NC}"
    echo -e "${YELLOW}Checking service logs:${NC}"
    sudo journalctl -u $SERVICE_NAME -n 20
fi

# Check nginx configuration
echo -e "${GREEN}Checking and updating nginx configuration...${NC}"
NGINX_CONF="/etc/nginx/sites-enabled/$SERVICE_NAME"
if [ -f "$NGINX_CONF" ]; then
    # Update paths in nginx config
    if grep -q "/home/" "$NGINX_CONF"; then
        sudo sed -i "s|/home/[^/]*/plot-runner-agent|$APP_DIR|g" "$NGINX_CONF"
        echo -e "${GREEN}Updated paths in nginx configuration${NC}"

        # Test and restart nginx
        if sudo nginx -t; then
            sudo systemctl restart nginx
            echo -e "${GREEN}✓ Nginx configuration updated and service restarted${NC}"
        else
            echo -e "${RED}✗ Nginx configuration test failed${NC}"
        fi
    fi
else
    echo -e "${YELLOW}Nginx configuration not found at $NGINX_CONF${NC}"
fi

# Final status check
echo
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Final Status:${NC}"
echo -e "${GREEN}======================================${NC}"
echo -e "NextDraw API service: $(systemctl is-active $SERVICE_NAME)"
echo -e "Nginx service: $(systemctl is-active nginx)"
echo
echo -e "To test API directly: curl http://localhost:5000/health"
echo -e "To test via nginx: curl http://localhost/health"
echo
echo -e "If still having issues, check logs with:"
echo -e "  sudo journalctl -u $SERVICE_NAME -n 50"
echo -e "  sudo journalctl -u nginx -n 20"
