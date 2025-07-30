#!/bin/bash

# NextDraw API 502 Bad Gateway Troubleshooting Script
# This script helps diagnose and fix 502 errors

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="nextdraw-api"
APP_DIR="/home/james/plot-runner-agent"
VENV_DIR="$APP_DIR/venv"
API_PORT="5000"

# Functions
log() {
    echo -e "${GREEN}[✓] $1${NC}"
}

error() {
    echo -e "${RED}[✗] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[!] $1${NC}"
}

info() {
    echo -e "${BLUE}[i] $1${NC}"
}

header() {
    echo
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Start troubleshooting
echo "NextDraw API 502 Bad Gateway Troubleshooter"
echo "=========================================="
echo

# 1. Check service status
header "1. Checking Service Status"

if systemctl is-active --quiet $APP_NAME; then
    log "Service $APP_NAME is active"
    info "Service details:"
    systemctl status $APP_NAME --no-pager | head -n 10
else
    error "Service $APP_NAME is not running!"

    # Try to start it
    warning "Attempting to start the service..."
    sudo systemctl start $APP_NAME
    sleep 3

    if systemctl is-active --quiet $APP_NAME; then
        log "Service started successfully!"
    else
        error "Failed to start service. Checking logs..."
        sudo journalctl -u $APP_NAME -n 50 --no-pager
    fi
fi

# 2. Check if app is listening on port
header "2. Checking Port Binding"

if sudo netstat -tlnp | grep -q ":$API_PORT"; then
    log "Something is listening on port $API_PORT"
    sudo netstat -tlnp | grep ":$API_PORT"
else
    error "Nothing is listening on port $API_PORT!"
    warning "The Flask app may not be starting correctly."
fi

# 3. Check recent service logs
header "3. Recent Service Logs"

info "Last 20 lines of service logs:"
sudo journalctl -u $APP_NAME -n 20 --no-pager

# 4. Check for Python/import errors
header "4. Checking Python Environment"

if [ -f "$VENV_DIR/bin/python" ]; then
    log "Virtual environment exists at $VENV_DIR"

    # Test if we can import Flask
    info "Testing Python imports..."
    cd "$APP_DIR"
    if $VENV_DIR/bin/python -c "import flask; print('Flask imported successfully')" 2>/dev/null; then
        log "Flask can be imported"
    else
        error "Cannot import Flask!"
        warning "Reinstalling dependencies..."
        $VENV_DIR/bin/pip install -r requirements.txt
    fi

    # Test if NextDraw is installed
    if $VENV_DIR/bin/python -c "import nd" 2>/dev/null; then
        log "NextDraw library is installed"
    else
        warning "NextDraw library not found. This may be expected if no plotter is connected."
    fi
else
    error "Virtual environment not found at $VENV_DIR!"
    warning "Creating virtual environment..."
    cd "$APP_DIR"
    python3 -m venv "$VENV_DIR"
    $VENV_DIR/bin/pip install -r requirements.txt
fi

# 5. Check file permissions
header "5. Checking File Permissions"

APP_USER=$(stat -c '%U' "$APP_DIR")
SERVICE_USER=$(systemctl show -p User $APP_NAME | cut -d= -f2)

if [ "$APP_USER" = "$SERVICE_USER" ]; then
    log "File ownership is correct ($APP_USER)"
else
    error "File ownership mismatch! Files owned by $APP_USER, service runs as $SERVICE_USER"
    warning "Fixing ownership..."
    sudo chown -R $SERVICE_USER:$SERVICE_USER "$APP_DIR"
fi

# 6. Test Flask app directly
header "6. Testing Flask App Directly"

info "Attempting to run Flask app manually..."
cd "$APP_DIR"

# Kill any existing processes on the port
sudo fuser -k $API_PORT/tcp 2>/dev/null || true
sleep 2

# Try to start the app
timeout 10s $VENV_DIR/bin/python app.py &
APP_PID=$!
sleep 5

if kill -0 $APP_PID 2>/dev/null; then
    log "Flask app started successfully!"

    # Test with curl
    if curl -s http://localhost:$API_PORT/health > /dev/null; then
        log "Flask app is responding to requests!"
    else
        error "Flask app is running but not responding to requests"
    fi

    # Kill the test process
    kill $APP_PID 2>/dev/null || true
else
    error "Flask app failed to start. Check for errors above."
fi

# 7. Check nginx configuration
header "7. Checking Nginx Configuration"

if nginx -t 2>/dev/null; then
    log "Nginx configuration is valid"
else
    error "Nginx configuration has errors!"
    sudo nginx -t
fi

# Check if nginx is running
if systemctl is-active --quiet nginx; then
    log "Nginx is running"
else
    error "Nginx is not running!"
    sudo systemctl start nginx
fi

# 8. Check for common issues
header "8. Common Issues Check"

# Check for missing config file
if [ -f "$APP_DIR/config.json" ]; then
    log "Configuration file exists"
else
    error "Configuration file missing!"
    warning "Creating default configuration..."
    cat > "$APP_DIR/config.json" <<EOF
{
  "plotter_info": {
    "model": 8,
    "nickname": "RaspberryPi-Plotter-$(hostname)",
    "port": null,
    "port_config": 0
  },
  "plotter_settings": {
    "speed_pendown": 25,
    "speed_penup": 75,
    "accel": 75,
    "pen_pos_down": 40,
    "pen_pos_up": 60,
    "pen_rate_lower": 50,
    "pen_rate_raise": 50,
    "handling": 1,
    "homing": true,
    "model": 8,
    "auto_rotate": true,
    "reordering": 0,
    "report_time": true
  },
  "api_settings": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false,
    "cors_enabled": true
  },
  "version": "1.0.0",
  "last_updated": "$(date -Iseconds)"
}
EOF
    sudo chown $SERVICE_USER:$SERVICE_USER "$APP_DIR/config.json"
fi

# Check for required directories
for dir in logs uploads output; do
    if [ -d "$APP_DIR/$dir" ]; then
        log "Directory $dir exists"
    else
        warning "Creating missing directory: $dir"
        mkdir -p "$APP_DIR/$dir"
        sudo chown $SERVICE_USER:$SERVICE_USER "$APP_DIR/$dir"
    fi
done

# 9. Attempt fixes
header "9. Attempting Automatic Fixes"

# Restart services
info "Restarting services..."
sudo systemctl daemon-reload
sudo systemctl restart $APP_NAME
sleep 3
sudo systemctl restart nginx

# Final check
header "10. Final Status Check"

if systemctl is-active --quiet $APP_NAME && systemctl is-active --quiet nginx; then
    log "Both services are running"

    # Test the endpoint
    sleep 2
    if curl -s http://localhost/health > /dev/null 2>&1; then
        log "SUCCESS! The API is now responding correctly!"
        echo
        info "You should now be able to access:"
        echo "  - http://$(hostname -I | awk '{print $1}')/"
        echo "  - http://$(hostname).local/"
    else
        error "Services are running but still getting 502 error"
        echo
        warning "Manual intervention may be required. Check the logs above for clues."
    fi
else
    error "One or more services failed to start"
fi

# Summary and recommendations
header "Summary & Recommendations"

echo "If the issue persists, try these manual steps:"
echo
echo "1. Check Python app directly:"
echo "   cd $APP_DIR"
echo "   source $VENV_DIR/bin/activate"
echo "   python app.py"
echo
echo "2. View detailed logs:"
echo "   sudo journalctl -u $APP_NAME -f"
echo
echo "3. Check nginx error log:"
echo "   sudo tail -f /var/log/nginx/error.log"
echo
echo "4. Verify USB permissions (if plotter connected):"
echo "   ls -la /dev/ttyUSB* /dev/ttyACM*"
echo "   sudo udevadm trigger"
echo
echo "5. Reinstall from scratch:"
echo "   cd ~/plot-runner-agent/ansible"
echo "   ./deploy.sh -l $(hostname).local"

exit 0
