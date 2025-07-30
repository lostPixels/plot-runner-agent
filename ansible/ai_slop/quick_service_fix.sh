#!/bin/bash

# Quick fix for NextDraw API systemd service issues
# The problem: ProtectHome=yes prevents access to /home/james/

set -e

echo "NextDraw API Service Quick Fix"
echo "=============================="
echo

# Stop the service
echo "Stopping service..."
sudo systemctl stop nextdraw-api 2>/dev/null || true

# Backup existing service file
echo "Backing up service file..."
sudo cp /etc/systemd/system/nextdraw-api.service /etc/systemd/system/nextdraw-api.service.backup

# Create fixed service file
echo "Creating fixed service file..."
sudo tee /etc/systemd/system/nextdraw-api.service > /dev/null <<'EOF'
[Unit]
Description=NextDraw Plotter API Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=james
Group=james
WorkingDirectory=/home/james/plot-runner-agent
Environment="PATH=/home/james/plot-runner-agent/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/james/plot-runner-agent/venv/bin/python /home/james/plot-runner-agent/app.py
Restart=always
RestartSec=5

# Minimal security settings that don't break home directory access
PrivateTmp=yes
LimitNOFILE=65536
MemoryMax=512M

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nextdraw-api

[Install]
WantedBy=multi-user.target
EOF

# Test the Python executable
echo
echo "Testing Python executable..."
if sudo -u james /home/james/plot-runner-agent/venv/bin/python --version; then
    echo "✓ Python executable works"
else
    echo "✗ Python executable failed!"
    exit 1
fi

# Test app import
echo
echo "Testing app import..."
cd /home/james/plot-runner-agent
if sudo -u james /home/james/plot-runner-agent/venv/bin/python -c "import app; print('✓ App imported successfully')"; then
    echo "✓ App can be imported"
else
    echo "✗ App import failed!"
    exit 1
fi

# Reload systemd and start service
echo
echo "Reloading systemd and starting service..."
sudo systemctl daemon-reload
sudo systemctl start nextdraw-api

# Wait a moment
sleep 3

# Check status
echo
echo "Checking service status..."
if systemctl is-active --quiet nextdraw-api; then
    echo "✓ Service is running!"

    # Test API
    echo
    echo "Testing API..."
    if curl -s http://localhost:5000/health > /dev/null 2>&1; then
        echo "✓ API is responding!"
        echo
        echo "SUCCESS! NextDraw API is working!"
        echo "Access at: http://$(hostname -I | awk '{print $1}')/"
    else
        echo "✗ API not responding"
        echo "Check logs: sudo journalctl -u nextdraw-api -f"
    fi
else
    echo "✗ Service failed to start"
    echo
    echo "Recent logs:"
    sudo journalctl -u nextdraw-api -n 10 --no-pager
    echo
    echo "To restore original service file:"
    echo "  sudo cp /etc/systemd/system/nextdraw-api.service.backup /etc/systemd/system/nextdraw-api.service"
    echo "  sudo systemctl daemon-reload"
fi

echo
echo "Service file location: /etc/systemd/system/nextdraw-api.service"
echo "Backup saved at: /etc/systemd/system/nextdraw-api.service.backup"
