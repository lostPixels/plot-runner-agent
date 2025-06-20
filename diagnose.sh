#!/bin/bash

# NextDraw API Diagnostic Script
# Performs comprehensive system check for troubleshooting

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

APP_DIR="/home/pi/plot-runner-agent"
SERVICE_NAME="nextdraw-api"

echo -e "${BLUE}NextDraw API Diagnostic Script${NC}"
echo "==============================="
echo

# System Information
echo -e "${BLUE}System Information:${NC}"
echo "Hostname: $(hostname)"
echo "OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
echo "Kernel: $(uname -r)"
echo "Architecture: $(uname -m)"
echo "Uptime: $(uptime -p)"
echo "Date: $(date)"
echo

# Hardware Check
echo -e "${BLUE}Hardware Check:${NC}"
if grep -q "Raspberry Pi" /proc/cpuinfo; then
    echo -e "${GREEN}✓${NC} Running on Raspberry Pi"
    PI_MODEL=$(grep "Model" /proc/cpuinfo | cut -d':' -f2 | sed 's/^ *//')
    echo "  Model: $PI_MODEL"
else
    echo -e "${YELLOW}⚠${NC} Not running on Raspberry Pi"
fi

# Memory and disk usage
echo "Memory: $(free -h | grep Mem | awk '{print $3"/"$2}')"
echo "Disk: $(df -h / | tail -1 | awk '{print $3"/"$2" ("$5" used)"}')"
echo

# USB Devices
echo -e "${BLUE}USB Devices:${NC}"
USB_DEVICES=$(lsusb)
echo "$USB_DEVICES"
echo

# NextDraw specific USB check
echo -e "${BLUE}NextDraw USB Check:${NC}"
NEXTDRAW_USB=$(lsusb | grep -E "(04d8:fd92|04d8:fc18|04d8:fc19)" || echo "Not found")
if [[ "$NEXTDRAW_USB" != "Not found" ]]; then
    echo -e "${GREEN}✓${NC} NextDraw USB device detected:"
    echo "  $NEXTDRAW_USB"
else
    echo -e "${RED}✗${NC} NextDraw USB device not detected"
fi
echo

# USB Permissions
echo -e "${BLUE}USB Permissions:${NC}"
if groups pi | grep -q plugdev; then
    echo -e "${GREEN}✓${NC} User 'pi' is in plugdev group"
else
    echo -e "${RED}✗${NC} User 'pi' is NOT in plugdev group"
fi

if [[ -f "/etc/udev/rules.d/99-nextdraw.rules" ]]; then
    echo -e "${GREEN}✓${NC} NextDraw udev rules exist"
else
    echo -e "${RED}✗${NC} NextDraw udev rules missing"
fi

# Check for ACM devices
ACM_DEVICES=$(ls /dev/ttyACM* 2>/dev/null || echo "None")
echo "ACM devices: $ACM_DEVICES"
echo

# Python Environment
echo -e "${BLUE}Python Environment:${NC}"
PYTHON_VERSION=$(python3 --version)
echo "Python: $PYTHON_VERSION"

# Check for required system packages
echo "System Python packages:"
for pkg in python3-venv python3-dev python3-full libusb-1.0-0-dev libudev-dev; do
    if dpkg -l | grep -q " $pkg "; then
        echo -e "  ${GREEN}✓${NC} $pkg installed"
    else
        echo -e "  ${RED}✗${NC} $pkg not installed"
    fi
done

if [[ -d "$APP_DIR/venv" ]]; then
    echo -e "${GREEN}✓${NC} Virtual environment exists"
    VENV_PYTHON="$APP_DIR/venv/bin/python"
    if [[ -f "$VENV_PYTHON" ]]; then
        VENV_VERSION=$($VENV_PYTHON --version)
        echo "  Virtual env Python: $VENV_VERSION"
    fi

    # Check venv structure
    if [[ -f "$APP_DIR/venv/bin/activate" ]]; then
        echo -e "  ${GREEN}✓${NC} Activation script exists"
    else
        echo -e "  ${RED}✗${NC} Activation script missing"
    fi

    if [[ -f "$APP_DIR/venv/bin/pip" ]]; then
        echo -e "  ${GREEN}✓${NC} pip exists in venv"
    else
        echo -e "  ${RED}✗${NC} pip missing from venv"
    fi
else
    echo -e "${RED}✗${NC} Virtual environment missing"
fi

# NextDraw Library Check
echo -e "${BLUE}NextDraw Library Check:${NC}"
cd "$APP_DIR"
if [[ -f "venv/bin/activate" ]]; then
    source venv/bin/activate
    echo "Checking for NextDraw module..."
    if python -c "import nextdraw; print('NextDraw version:', getattr(nextdraw, '__version__', 'unknown'))" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} NextDraw library accessible"

        # List key installed packages
        echo "Python packages in virtual environment:"
        pip list | grep -E "(flask|gunicorn|requests|nextdraw)" || echo "  No key packages found"
    else
        echo -e "${RED}✗${NC} NextDraw library not accessible"
        echo "Error details:"
        python -c "import nextdraw" 2>&1 | head -3

        echo -e "${YELLOW}⚠${NC} Try reinstalling with:"
        echo "  source venv/bin/activate && pip install https://software-download.bantamtools.com/nd/api/nextdraw_api.zip"
    fi
    deactivate
else
    echo -e "${RED}✗${NC} Cannot activate virtual environment"
    echo -e "${YELLOW}⚠${NC} Try recreating with: python3 -m venv --clear $APP_DIR/venv"
fi
echo

# Service Status
echo -e "${BLUE}Service Status:${NC}"
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}✓${NC} $SERVICE_NAME service is running"
else
    echo -e "${RED}✗${NC} $SERVICE_NAME service is not running"
fi

if systemctl is-enabled --quiet $SERVICE_NAME; then
    echo -e "${GREEN}✓${NC} $SERVICE_NAME service is enabled"
else
    echo -e "${RED}✗${NC} $SERVICE_NAME service is not enabled"
fi

if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓${NC} nginx service is running"
else
    echo -e "${RED}✗${NC} nginx service is not running"
fi

# Check service configuration
if [[ -f "/etc/systemd/system/$SERVICE_NAME.service" ]]; then
    echo "Service configuration:"
    VENV_PATH=$(grep "Environment=PATH=" /etc/systemd/system/$SERVICE_NAME.service | grep -o "/.*bin")
    EXEC_PATH=$(grep "ExecStart=" /etc/systemd/system/$SERVICE_NAME.service | grep -o "/.*python")

    if [[ "$VENV_PATH" == *"venv"* ]]; then
        echo -e "  ${GREEN}✓${NC} Service using virtual environment path"
    else
        echo -e "  ${RED}✗${NC} Service not using virtual environment path"
        echo "    Found: $VENV_PATH"
    fi

    if [[ "$EXEC_PATH" == *"venv"* ]]; then
        echo -e "  ${GREEN}✓${NC} Service using virtual environment Python"
    else
        echo -e "  ${RED}✗${NC} Service not using virtual environment Python"
        echo "    Found: $EXEC_PATH"
    fi
fi
echo

# Network Status
echo -e "${BLUE}Network Status:${NC}"
IP_ADDRESS=$(hostname -I | awk '{print $1}')
echo "IP Address: $IP_ADDRESS"

# Check if API is responding
if curl -s http://localhost:5000/health >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} API responding on port 5000"
else
    echo -e "${RED}✗${NC} API not responding on port 5000"
fi

if curl -s http://localhost/health >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Nginx proxy working on port 80"
else
    echo -e "${RED}✗${NC} Nginx proxy not working on port 80"
fi

# Port check
PORT_5000=$(netstat -tlnp 2>/dev/null | grep :5000 || echo "Not listening")
echo "Port 5000: $PORT_5000"
echo

# Configuration Files
echo -e "${BLUE}Configuration Files:${NC}"
if [[ -f "$APP_DIR/config.json" ]]; then
    echo -e "${GREEN}✓${NC} config.json exists"
    CONFIG_SIZE=$(stat -c%s "$APP_DIR/config.json")
    echo "  Size: $CONFIG_SIZE bytes"
else
    echo -e "${RED}✗${NC} config.json missing"
fi

if [[ -f "/etc/systemd/system/$SERVICE_NAME.service" ]]; then
    echo -e "${GREEN}✓${NC} systemd service file exists"
else
    echo -e "${RED}✗${NC} systemd service file missing"
fi

if [[ -f "/etc/nginx/sites-enabled/$SERVICE_NAME" ]]; then
    echo -e "${GREEN}✓${NC} nginx configuration enabled"
else
    echo -e "${RED}✗${NC} nginx configuration not enabled"
fi
echo

# Log Files
echo -e "${BLUE}Log Files:${NC}"
LOG_DIR="$APP_DIR/logs"
if [[ -d "$LOG_DIR" ]]; then
    echo -e "${GREEN}✓${NC} Log directory exists"
    for logfile in app.log gunicorn.log gunicorn_access.log gunicorn_error.log; do
        if [[ -f "$LOG_DIR/$logfile" ]]; then
            SIZE=$(stat -c%s "$LOG_DIR/$logfile")
            LINES=$(wc -l < "$LOG_DIR/$logfile" 2>/dev/null || echo "0")
            echo "  $logfile: $SIZE bytes, $LINES lines"
        else
            echo "  $logfile: missing"
        fi
    done
else
    echo -e "${RED}✗${NC} Log directory missing"
fi
echo

# Recent Errors
echo -e "${BLUE}Recent Service Errors (last 10):${NC}"
journalctl -u $SERVICE_NAME --since "1 hour ago" --no-pager -p err -n 10 | grep -v "^--" || echo "No recent errors"
echo

# API Health Check
echo -e "${BLUE}API Health Check:${NC}"
if curl -s http://localhost/health 2>/dev/null; then
    echo -e "${GREEN}✓${NC} API health check successful"
else
    echo -e "${RED}✗${NC} API health check failed"
fi
echo

# File Permissions
echo -e "${BLUE}File Permissions Check:${NC}"
if [[ -O "$APP_DIR" ]]; then
    echo -e "${GREEN}✓${NC} Application directory owned by current user"
else
    echo -e "${RED}✗${NC} Application directory not owned by current user"
fi

if [[ -x "$APP_DIR/app.py" ]]; then
    echo -e "${GREEN}✓${NC} app.py is executable"
else
    echo -e "${YELLOW}⚠${NC} app.py is not executable"
fi
echo

# Disk Space Check
echo -e "${BLUE}Disk Space:${NC}"
df -h / | tail -1 | awk '{
    if ($5+0 > 90)
        print "\033[0;31m✗\033[0m Root partition is " $5 " full (critical)"
    else if ($5+0 > 80)
        print "\033[1;33m⚠\033[0m Root partition is " $5 " full (warning)"
    else
        print "\033[0;32m✓\033[0m Root partition is " $5 " full (ok)"
}'
echo

# Process Check
echo -e "${BLUE}Process Check:${NC}"
PYTHON_PROCESSES=$(pgrep -f "python.*app.py" | wc -l)
echo "Python app processes: $PYTHON_PROCESSES"

NGINX_PROCESSES=$(pgrep nginx | wc -l)
echo "Nginx processes: $NGINX_PROCESSES"
echo

# Firewall Status
echo -e "${BLUE}Firewall Status:${NC}"
if command -v ufw >/dev/null 2>&1; then
    UFW_STATUS=$(sudo ufw status | head -1)
    echo "UFW: $UFW_STATUS"
else
    echo "UFW: not installed"
fi
echo

# Summary
echo -e "${BLUE}Diagnostic Summary:${NC}"
echo "========================"

# Quick connectivity test
if curl -s http://localhost/health >/dev/null 2>&1; then
    echo -e "${GREEN}✓ System appears to be working correctly${NC}"
else
    echo -e "${RED}✗ System has issues that need attention${NC}"
    echo
    echo "Common troubleshooting steps:"
    echo "1. Check if NextDraw is connected: lsusb | grep 04d8"
    echo "2. Restart the service: sudo systemctl restart $SERVICE_NAME"
    echo "3. Check service logs: sudo journalctl -u $SERVICE_NAME -f"
    echo "4. Verify USB permissions: sudo udevadm trigger"
    echo "5. Test Python import: cd $APP_DIR && source venv/bin/activate && python -c 'import nextdraw'"

    # Display venv fix command if nextdraw import fails
    if ! (cd "$APP_DIR" && source venv/bin/activate 2>/dev/null && python -c "import nextdraw" 2>/dev/null); then
        echo -e "\n${YELLOW}Virtual environment issue detected!${NC}"
        echo "To fix NextDraw installation issues, run:"
        if [[ -f "$APP_DIR/deploy/fix_nextdraw_install.sh" ]]; then
            echo "  cd $APP_DIR && bash deploy/fix_nextdraw_install.sh"
        else
            echo "  cd $APP_DIR && source venv/bin/activate"
            echo "  pip install https://software-download.bantamtools.com/nd/api/nextdraw_api.zip"
            echo "  sudo systemctl restart $SERVICE_NAME"
        fi
    fi
fi

echo
echo "For more detailed logs, run:"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo "  tail -f $APP_DIR/logs/app.log"
echo
echo "For advanced virtual environment diagnostics, run:"
if [[ -f "$APP_DIR/deploy/venv_check.sh" ]]; then
    echo "  cd $APP_DIR && bash deploy/venv_check.sh"
else
    echo "  cd $APP_DIR && source venv/bin/activate && python -c 'import sys; print(sys.executable)'"
fi
