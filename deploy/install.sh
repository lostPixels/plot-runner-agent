#!/bin/bash

# NextDraw Plotter API Installation Script for Raspberry Pi
# This script sets up the NextDraw API server on a fresh Raspberry Pi

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="nextdraw-api"
APP_USER="james"
APP_DIR="/home/james/plot-runner-agent"
VENV_DIR="$APP_DIR/venv"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"
NGINX_CONFIG="/etc/nginx/sites-available/$APP_NAME"
NGINX_ENABLED="/etc/nginx/sites-enabled/$APP_NAME"

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   error "This script should not be run as root. Run as the pi user."
   exit 1
fi

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    warning "This doesn't appear to be a Raspberry Pi. Continuing anyway..."
fi

log "Starting NextDraw API installation..."

# Update system packages
log "Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install required system packages
log "Installing system dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    nginx \
    supervisor \
    udev \
    build-essential \
    python3-dev \
    libusb-1.0-0-dev \
    libudev-dev

# We'll install NextDraw Python library in the virtual environment later
log "Preparing for NextDraw Python library installation..."

# Create application directory if it doesn't exist
if [ ! -d "$APP_DIR" ]; then
    log "Creating application directory: $APP_DIR"
    mkdir -p "$APP_DIR"
fi

cd "$APP_DIR"

# Create Python virtual environment
log "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# Install python3-full if needed for venv
if [ $? -ne 0 ]; then
    log "Virtual environment creation failed. Installing python3-full and retrying..."
    sudo apt install -y python3-full
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
fi

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
if [ -f "requirements.txt" ]; then
    log "Installing Python dependencies..."
    pip install -r requirements.txt
else
    log "Installing basic Python dependencies..."
    pip install Flask Flask-CORS gunicorn requests watchdog
fi

# Install NextDraw library in virtual environment
log "Installing NextDraw library in virtual environment..."
pip install https://software-download.bantamtools.com/nd/api/nextdraw_api.zip
if [ $? -ne 0 ]; then
    warning "NextDraw installation failed. This might be because we're missing development libraries."
    warning "Installing additional development packages and retrying..."
    sudo apt install -y python3-dev libusb-1.0-0-dev libudev-dev
    pip install https://software-download.bantamtools.com/nd/api/nextdraw_api.zip
fi

# Set up USB permissions for NextDraw
log "Setting up USB permissions..."
sudo tee /etc/udev/rules.d/99-nextdraw.rules > /dev/null <<EOF
# NextDraw USB permissions
SUBSYSTEM=="usb", ATTR{idVendor}=="04d8", ATTR{idProduct}=="fd92", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="04d8", ATTR{idProduct}=="fc18", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="04d8", ATTR{idProduct}=="fc19", MODE="0666", GROUP="plugdev"
EOF

# Add user to plugdev group
sudo usermod -a -G plugdev "$APP_USER"

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Create necessary directories
log "Creating application directories..."
mkdir -p logs uploads output

# Set up systemd service
if [ -f "deploy/$APP_NAME.service" ]; then
    log "Installing systemd service..."
    sudo cp "deploy/$APP_NAME.service" "$SERVICE_FILE"

    # Update service file paths if needed
    sudo sed -i "s|/home/james/plot-runner-agent|$APP_DIR|g" "$SERVICE_FILE"

    sudo systemctl daemon-reload
    sudo systemctl enable "$APP_NAME"
else
    log "Creating systemd service file..."
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=NextDraw Plotter API Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PATH=$VENV_DIR/bin
ExecStart=$VENV_DIR/bin/python $APP_DIR/app.py
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

    sudo systemctl daemon-reload
    sudo systemctl enable "$APP_NAME"
fi

# Create nginx temp upload directory
log "Creating nginx temporary upload directory..."
sudo mkdir -p /tmp/nginx_uploads
sudo chown www-data:www-data /tmp/nginx_uploads
sudo chmod 755 /tmp/nginx_uploads

# Set up nginx reverse proxy
log "Setting up nginx reverse proxy..."
sudo tee "$NGINX_CONFIG" > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    # Large file upload settings
    client_max_body_size 1G;
    client_body_buffer_size 128k;
    client_body_timeout 300s;
    client_header_timeout 300s;

    # Temporary file settings for large uploads
    client_body_temp_path /tmp/nginx_uploads 1 2;

    # Main application proxy
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        # Extended timeouts for large uploads and long plots
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;

        # Buffer settings for large requests
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_max_temp_file_size 0;
    }

    # Special handling for upload endpoints
    location ~ ^/(plot|plot/upload|plot/chunk) {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # Extended settings for large file uploads
        client_max_body_size 1G;
        client_body_timeout 600s;
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;

        # Disable buffering for uploads
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_max_temp_file_size 0;

        # Progress tracking
        proxy_set_header X-Content-Length \$content_length;
    }

    # Static file serving for uploads/downloads
    location /uploads/ {
        alias $APP_DIR/uploads/;
        expires 1h;
        add_header Cache-Control "public, immutable";

        # Enable range requests for large files
        add_header Accept-Ranges bytes;

        # Security headers
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
    }

    location /output/ {
        alias $APP_DIR/output/;
        expires 1h;
        add_header Cache-Control "public, immutable";

        # Enable range requests for large files
        add_header Accept-Ranges bytes;

        # Security headers
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
    }

    # Health check endpoint optimization
    location /health {
        proxy_pass http://127.0.0.1:5000;
        proxy_cache_valid 200 10s;
        proxy_connect_timeout 5s;
        proxy_send_timeout 5s;
        proxy_read_timeout 5s;
    }

    # Logging
    access_log /var/log/nginx/nextdraw_access.log combined;
    error_log /var/log/nginx/nextdraw_error.log warn;

    # Security headers
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
EOF

# Enable nginx site
sudo ln -sf "$NGINX_CONFIG" "$NGINX_ENABLED"

# Remove default nginx site
sudo rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
sudo nginx -t

# Create log rotation configuration
log "Setting up log rotation..."
sudo tee /etc/logrotate.d/$APP_NAME > /dev/null <<EOF
$APP_DIR/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0644 $APP_USER $APP_USER
    postrotate
        sudo systemctl reload $APP_NAME
    endscript
}
EOF

# Set up firewall (if ufw is available)
if command -v ufw &> /dev/null; then
    log "Configuring firewall..."
    sudo ufw allow 22/tcp
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw allow 5000/tcp
    echo "y" | sudo ufw enable || true
fi

# Create initial configuration if it doesn't exist
if [ ! -f "config.json" ]; then
    log "Creating initial configuration..."
    cat > config.json <<EOF
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
fi

# Set correct permissions
log "Setting file permissions..."
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod +x "$APP_DIR/app.py" 2>/dev/null || true

# Create update script
log "Creating update script..."
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

# Start services
log "Starting services..."
sudo systemctl restart nginx
sudo systemctl start "$APP_NAME"

# Wait a moment for service to start
sleep 3

# Check service status
if sudo systemctl is-active --quiet "$APP_NAME"; then
    log "NextDraw API service is running successfully!"
else
    error "NextDraw API service failed to start. Check logs with: sudo journalctl -u $APP_NAME -f"
fi

if sudo systemctl is-active --quiet nginx; then
    log "Nginx is running successfully!"
else
    error "Nginx failed to start. Check logs with: sudo journalctl -u nginx -f"
fi

# Get IP address
IP_ADDRESS=$(hostname -I | awk '{print $1}')

log "Installation completed successfully!"
echo
echo "======================================"
echo "NextDraw API Installation Complete"
echo "======================================"
echo
echo "Service Status:"
echo "  NextDraw API: $(sudo systemctl is-active $APP_NAME)"
echo "  Nginx:        $(sudo systemctl is-active nginx)"
echo
echo "Access URLs:"
echo "  API Endpoint:    http://$IP_ADDRESS/"
echo "  Health Check:    http://$IP_ADDRESS/health"
echo "  Status:          http://$IP_ADDRESS/status"
echo
echo "Useful Commands:"
echo "  Start service:   sudo systemctl start $APP_NAME"
echo "  Stop service:    sudo systemctl stop $APP_NAME"
echo "  Restart service: sudo systemctl restart $APP_NAME"
echo "  View logs:       sudo journalctl -u $APP_NAME -f"
echo "  Update app:      cd $APP_DIR && ./update.sh"
echo
echo "Configuration file: $APP_DIR/config.json"
echo "Log files:          $APP_DIR/logs/"
echo
echo "IMPORTANT: You may need to log out and back in for USB permissions to take effect."
echo "           If the plotter is not detected, try: sudo udevadm trigger"
