#!/bin/bash

# NextDraw Plotter API Virtual Environment Diagnostic Script
# This script checks for virtual environment issues and installation problems

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/home/james/plot-runner-agent"
VENV_DIR="$APP_DIR/venv"

# Function to log output
log() {
    echo -e "${GREEN}[INFO] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

header() {
    echo -e "\n${BLUE}========== $1 ==========${NC}"
}

status_check() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $1${NC}"
    else
        echo -e "${RED}✗ $1${NC}"
        if [ -n "$2" ]; then
            echo -e "   ${YELLOW}→ $2${NC}"
        fi
    fi
}

# Basic header
echo "==========================================="
echo "NextDraw Plotter API Virtual Environment Check"
echo "==========================================="
echo "Date: $(date)"
echo "Hostname: $(hostname)"

# Check Python version
header "Python Version"
python3 --version
status_check "Python version check" "Python 3.7+ is recommended"

# Check for required system packages
header "System Packages"
echo "Checking for required packages..."

pkg_check() {
    if dpkg -l | grep -q " $1 "; then
        echo -e "${GREEN}✓ $1 installed${NC}"
    else
        echo -e "${RED}✗ $1 missing${NC}"
        echo "   → Install with: sudo apt install $1"
    fi
}

pkg_check "python3-full"
pkg_check "python3-venv"
pkg_check "python3-dev"
pkg_check "libusb-1.0-0-dev"
pkg_check "libudev-dev"

# Check if virtual environment exists
header "Virtual Environment"
if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}✓ Virtual environment exists at $VENV_DIR${NC}"

    # Check activation
    if [ -f "$VENV_DIR/bin/activate" ]; then
        echo -e "${GREEN}✓ Virtual environment activation script exists${NC}"
    else
        error "Virtual environment activation script missing"
        echo "   → Recreate with: python3 -m venv $VENV_DIR"
    fi
else
    error "Virtual environment not found at $VENV_DIR"
    echo "   → Create with: python3 -m venv $VENV_DIR"
fi

# Test activating the virtual environment if it exists
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "Testing virtual environment activation..."
    if source "$VENV_DIR/bin/activate" 2>/dev/null; then
        echo -e "${GREEN}✓ Virtual environment activation successful${NC}"

        # Check Python version in venv
        echo "Python version in virtual environment: $(python --version 2>&1)"

        # Check pip
        if command -v pip >/dev/null 2>&1; then
            echo -e "${GREEN}✓ pip is available in virtual environment${NC}"
            echo "pip version: $(pip --version)"
        else
            error "pip not found in virtual environment"
            echo "   → Try reinstalling venv with: python3 -m venv --clear $VENV_DIR"
        fi

        # Check if NextDraw is installed
        echo "Checking for NextDraw library..."
        if python -c "import nextdraw" 2>/dev/null; then
            echo -e "${GREEN}✓ NextDraw library is installed${NC}"
            # Try to get version if possible
            ND_VERSION=$(python -c "import nextdraw; print(getattr(nextdraw, '__version__', 'unknown'))" 2>/dev/null)
            echo "   → NextDraw version: $ND_VERSION"
        else
            error "NextDraw library is not installed in virtual environment"
            echo "   → Install with: pip install https://software-download.bantamtools.com/nd/api/nextdraw_api.zip"
        fi

        # List installed packages
        echo "Top 10 installed packages:"
        pip list | head -n 12

        # Check for Flask and other requirements
        for pkg in Flask gunicorn requests Flask-CORS; do
            if pip show $pkg >/dev/null 2>&1; then
                echo -e "${GREEN}✓ $pkg is installed${NC}"
            else
                error "$pkg is not installed"
                echo "   → Install with: pip install $pkg"
            fi
        done

        # Deactivate the virtual environment
        deactivate
    else
        error "Failed to activate virtual environment"
        echo "   → Recreate with: python3 -m venv --clear $VENV_DIR"
    fi
fi

# Check service configuration
header "Service Configuration"
if [ -f "/etc/systemd/system/nextdraw-api.service" ]; then
    echo -e "${GREEN}✓ Service file exists${NC}"

    # Check if service is using the venv
    if grep -q "Environment=PATH=$VENV_DIR/bin" "/etc/systemd/system/nextdraw-api.service"; then
        echo -e "${GREEN}✓ Service is configured to use the virtual environment${NC}"
    else
        warning "Service may not be using the virtual environment"
        echo "Service Environment PATH: $(grep "Environment=PATH=" "/etc/systemd/system/nextdraw-api.service")"
    fi

    # Check ExecStart path
    if grep -q "ExecStart=$VENV_DIR/bin/python" "/etc/systemd/system/nextdraw-api.service"; then
        echo -e "${GREEN}✓ Service ExecStart is using virtual environment python${NC}"
    else
        warning "Service ExecStart may not be using the virtual environment python"
        echo "Service ExecStart: $(grep "ExecStart=" "/etc/systemd/system/nextdraw-api.service")"
    fi
else
    error "Service file not found at /etc/systemd/system/nextdraw-api.service"
fi

# Check service status
if systemctl is-active --quiet nextdraw-api; then
    echo -e "${GREEN}✓ nextdraw-api service is active${NC}"
else
    warning "nextdraw-api service is not active"
    echo "   → Service status: $(systemctl is-active nextdraw-api)"
    echo "   → Start with: sudo systemctl start nextdraw-api"
fi

# Provide recommendations based on findings
header "Recommendations"

if [ ! -d "$VENV_DIR" ]; then
    echo "1. Create a new virtual environment:"
    echo "   cd $APP_DIR"
    echo "   python3 -m venv $VENV_DIR"
    echo ""
fi

echo "If you need to reinstall the NextDraw library:"
echo "1. Activate the virtual environment:"
echo "   cd $APP_DIR"
echo "   source $VENV_DIR/bin/activate"
echo ""
echo "2. Install or reinstall the NextDraw library:"
echo "   pip install --upgrade https://software-download.bantamtools.com/nd/api/nextdraw_api.zip"
echo ""
echo "3. Install other requirements:"
echo "   pip install -r requirements.txt"
echo ""
echo "4. Restart the service:"
echo "   sudo systemctl restart nextdraw-api"
echo ""
echo "For complete reinstallation, see the installation script at:"
echo "$APP_DIR/deploy/install.sh"

# Final tips
header "Additional Tips"
echo "1. If installing the NextDraw library fails, ensure you have the required development packages:"
echo "   sudo apt install -y python3-full python3-dev libusb-1.0-0-dev libudev-dev"
echo ""
echo "2. You might need to log out and back in for USB permissions to take effect"
echo ""
echo "3. Check detailed service logs with:"
echo "   sudo journalctl -u nextdraw-api -f"
echo ""
echo "4. Use 'curl http://localhost/health' to check if the API is responding"
