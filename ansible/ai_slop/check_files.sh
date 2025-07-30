#!/bin/bash

# Quick file deployment status check
# Run this on the Raspberry Pi to check if files are properly deployed

APP_DIR="/home/james/plot-runner-agent"
REQUIRED_FILES=(
    "app.py"
    "config_manager.py"
    "job_queue.py"
    "plotter_controller.py"
    "requirements.txt"
    "wsgi.py"
    "config.json"
)

echo "NextDraw API File Deployment Check"
echo "=================================="
echo
echo "Checking directory: $APP_DIR"
echo

# Check if directory exists
if [ ! -d "$APP_DIR" ]; then
    echo "ERROR: Application directory does not exist!"
    exit 1
fi

cd "$APP_DIR"

# Check required files
echo "Required Files Status:"
echo "---------------------"
MISSING_COUNT=0
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✓ $file"
    else
        echo "✗ $file (MISSING)"
        ((MISSING_COUNT++))
    fi
done

echo
echo "Summary:"
echo "--------"
echo "Total required files: ${#REQUIRED_FILES[@]}"
echo "Missing files: $MISSING_COUNT"
echo

# List all Python files
echo "Python files found:"
echo "------------------"
find . -maxdepth 1 -name "*.py" -type f | sort

echo
echo "Total files in directory: $(find . -maxdepth 1 -type f | wc -l)"
echo

# Check virtual environment
echo "Virtual Environment:"
echo "-------------------"
if [ -d "venv" ]; then
    echo "✓ venv directory exists"
    if [ -f "venv/bin/python" ]; then
        echo "✓ Python executable found"
    else
        echo "✗ Python executable missing"
    fi
else
    echo "✗ venv directory missing"
fi

echo

# Quick service status
echo "Service Status:"
echo "--------------"
echo -n "nextdraw-api: "
systemctl is-active nextdraw-api || echo " (NOT RUNNING)"
echo -n "nginx: "
systemctl is-active nginx || echo " (NOT RUNNING)"

echo
echo "Quick Fix Commands:"
echo "------------------"
if [ $MISSING_COUNT -gt 0 ]; then
    echo "1. From your local machine, run:"
    echo "   cd plot-runner-agent/ansible"
    echo "   ./deploy.sh --emergency-fix -l $(hostname).local"
    echo
    echo "2. Or redeploy completely:"
    echo "   ./deploy.sh -l $(hostname).local"
else
    echo "All files present. If service isn't working, try:"
    echo "   sudo systemctl restart nextdraw-api"
    echo "   sudo journalctl -u nextdraw-api -f"
fi
