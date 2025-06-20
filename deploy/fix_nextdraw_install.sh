#!/bin/bash

# NextDraw Plotter API Installation Fix Script for Raspberry Pi
# This script fixes installation issues with the NextDraw API library

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="nextdraw-api"
APP_DIR="/home/james/plot-runner-agent"
VENV_DIR="$APP_DIR/venv"

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

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   error "This script should not be run as root. Run as the pi user."
fi

log "Starting NextDraw API installation fix..."

# Check if we're in the right directory
if [ ! -d "$APP_DIR" ]; then
    error "Application directory $APP_DIR not found. Make sure you're running this on a Raspberry Pi with NextDraw API installed."
fi

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    log "Virtual environment not found. Creating a new one..."

    # Install python3-full if needed
    if ! dpkg -l | grep -q " python3-full "; then
        log "Installing python3-full package..."
        sudo apt update
        sudo apt install -y python3-full
    fi

    # Create virtual environment
    cd "$APP_DIR"
    python3 -m venv "$VENV_DIR"

    if [ $? -ne 0 ]; then
        error "Failed to create virtual environment. Make sure python3-venv is installed."
    fi
else
    log "Found existing virtual environment at $VENV_DIR"
fi

# Install system dependencies
log "Making sure all required system dependencies are installed..."
sudo apt update
sudo apt install -y python3-dev libusb-1.0-0-dev libudev-dev build-essential

# Activate virtual environment
log "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

if [ $? -ne 0 ]; then
    error "Failed to activate virtual environment. Try recreating it with 'python3 -m venv --clear $VENV_DIR'"
fi

# Upgrade pip
log "Upgrading pip..."
pip install --upgrade pip

# Install/reinstall NextDraw library
log "Installing NextDraw library in virtual environment..."
pip install --upgrade https://software-download.bantamtools.com/nd/api/nextdraw_api.zip

if [ $? -ne 0 ]; then
    error "Failed to install NextDraw library. Check the error message above for details."
fi

# Install project requirements
if [ -f "$APP_DIR/requirements.txt" ]; then
    log "Installing project requirements..."
    pip install -r "$APP_DIR/requirements.txt"

    if [ $? -ne 0 ]; then
        warning "Some requirements could not be installed. The application might not work correctly."
    fi
fi

# Check if service file exists and update it if needed
if [ -f "/etc/systemd/system/$APP_NAME.service" ]; then
    log "Checking service configuration..."

    # Update service file paths if needed
    if ! grep -q "Environment=PATH=$VENV_DIR/bin" "/etc/systemd/system/$APP_NAME.service" || \
       ! grep -q "ExecStart=$VENV_DIR/bin/python" "/etc/systemd/system/$APP_NAME.service"; then

        log "Updating service file to use virtual environment..."
        sudo sed -i "s|Environment=PATH=.*|Environment=PATH=$VENV_DIR/bin|g" "/etc/systemd/system/$APP_NAME.service"
        sudo sed -i "s|ExecStart=.*|ExecStart=$VENV_DIR/bin/python $APP_DIR/app.py|g" "/etc/systemd/system/$APP_NAME.service"

        sudo systemctl daemon-reload
    else
        log "Service file already configured correctly"
    fi
fi

# Set correct permissions
log "Setting file permissions..."
sudo chown -R "$(whoami):$(whoami)" "$APP_DIR"
chmod +x "$APP_DIR/app.py" 2>/dev/null || true
chmod +x "$APP_DIR/deploy/venv_check.sh" 2>/dev/null || true

# Create update script if it doesn't exist
if [ ! -f "$APP_DIR/update.sh" ] || ! grep -q "nextdraw_api.zip" "$APP_DIR/update.sh"; then
    log "Creating/updating update script..."
    cat > "$APP_DIR/update.sh" <<'EOF'
#!/bin/bash
cd "$(dirname "$0")"
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
# Also update NextDraw library
pip install --upgrade https://software-download.bantamtools.com/nd/api/nextdraw_api.zip
sudo systemctl restart nextdraw-api
EOF
    chmod +x "$APP_DIR/update.sh"
fi

# Restart service if it exists
if systemctl is-enabled --quiet "$APP_NAME"; then
    log "Restarting $APP_NAME service..."
    sudo systemctl restart "$APP_NAME"

    # Wait a moment for service to start
    sleep 3

    # Check if service started successfully
    if systemctl is-active --quiet "$APP_NAME"; then
        log "$APP_NAME service restarted successfully"
    else
        warning "$APP_NAME service failed to start. Check logs with 'sudo journalctl -u $APP_NAME -f'"
    fi
else
    warning "The $APP_NAME service is not enabled. You may need to manually start it."
fi

# Test if NextDraw library can be imported
log "Testing NextDraw library import..."
if source "$VENV_DIR/bin/activate" && python -c "import nextdraw; print('NextDraw library successfully imported')" 2>/dev/null; then
    log "NextDraw library is installed correctly!"
else
    warning "NextDraw library import test failed. Something might still be wrong."
    warning "Try running the diagnostic script: $APP_DIR/deploy/venv_check.sh"
fi

log "Fix script completed!"
echo
echo "======================================"
echo "NextDraw API Fix Completed"
echo "======================================"
echo
echo "If you encounter any issues:"
echo "1. Run the diagnostic script: $APP_DIR/deploy/venv_check.sh"
echo "2. Check service logs with: sudo journalctl -u $APP_NAME -f"
echo "3. Try a full reinstallation with the updated install script"
echo
echo "Service Status: $(systemctl is-active $APP_NAME)"
echo
echo "You may need to log out and back in for USB permissions to take effect."
