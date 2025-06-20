# NextDraw Plotter API Server

A comprehensive Flask-based REST API server for controlling NextDraw plotters on Raspberry Pi. This application provides remote job management, configuration control, and real-time status monitoring for NextDraw pen plotters.

## Features

- **REST API Interface**: Complete HTTP API for plotter control
- **Job Queue Management**: Queue, prioritize, and track plot jobs
- **Real-time Status**: Monitor plotter status, queue, and job progress
- **Configuration Management**: Dynamic plotter settings with validation
- **Remote Updates**: Git-based code deployment and updates
- **Multi-plotter Support**: Designed for 1:1 Raspberry Pi to plotter deployment
- **Security**: USB permissions, process isolation, and resource limits
- **Monitoring**: Comprehensive logging and health checks

## API Endpoints

### Status & Health
- `GET /health` - Health check
- `GET /status` - Complete system status
- `GET /logs?lines=100` - Recent log entries

### Job Management
- `POST /plot` - Submit new plot job
- `GET /jobs` - List all jobs
- `GET /jobs/{id}` - Get job details
- `DELETE /jobs/{id}` - Cancel job

### Plotter Control
- `POST /pause` - Pause current job
- `POST /resume` - Resume paused job
- `POST /stop` - Stop current job

### Configuration
- `GET /config` - Get current configuration
- `PUT /config` - Update configuration
- `POST /config/reset` - Reset to defaults

### Utility Commands
- `POST /utility/home` - Move to home position
- `POST /utility/raise_pen` - Raise pen
- `POST /utility/lower_pen` - Lower pen
- `POST /utility/toggle_pen` - Toggle pen position
- `POST /utility/move` - Manual movement

### Remote Updates
- `POST /update` - Trigger code update

## Installation

### Prerequisites

- Raspberry Pi (4B recommended) with Raspberry Pi OS
- NextDraw plotter connected via USB
- Internet connection for installation
- SD card with at least 8GB space

### Quick Installation

1. **Clone the repository:**
```bash
cd /home/pi
git clone <your-repo-url> plot-runner-agent
cd plot-runner-agent
```

2. **Run the installation script:**
```bash
chmod +x deploy/install.sh
./deploy/install.sh
```

3. **Verify installation:**
```bash
sudo systemctl status nextdraw-api
curl http://localhost/health
```

### Manual Installation

If you prefer manual installation or need to customize the setup:

#### 1. System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor udev build-essential python3-dev libusb-1.0-0-dev libudev-dev
```

#### 2. NextDraw Python Library

```bash
pip3 install --user https://software-download.bantamtools.com/nd/api/nextdraw_api.zip
```

#### 3. Application Setup

```bash
cd /home/james/plot-runner-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install https://software-download.bantamtools.com/nd/api/nextdraw_api.zip
```

#### 4. USB Permissions

```bash
sudo tee /etc/udev/rules.d/99-nextdraw.rules > /dev/null <<EOF
SUBSYSTEM=="usb", ATTR{idVendor}=="04d8", ATTR{idProduct}=="fd92", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="04d8", ATTR{idProduct}=="fc18", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="04d8", ATTR{idProduct}=="fc19", MODE="0666", GROUP="plugdev"
EOF

sudo usermod -a -G plugdev pi
sudo udevadm control --reload-rules
sudo udevadm trigger
```

#### 5. SystemD Service

```bash
sudo cp deploy/nextdraw-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nextdraw-api
sudo systemctl start nextdraw-api
```

#### 6. Nginx Configuration

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/nextdraw-api
sudo ln -s /etc/nginx/sites-available/nextdraw-api /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

## Configuration

### Configuration File Structure

The application uses `config.json` for configuration:

```json
{
  "plotter_info": {
    "model": 8,
    "nickname": "RaspberryPi-Plotter",
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
  }
}
```

### Key Configuration Options

#### Plotter Settings
- **speed_pendown**: Pen-down movement speed (1-100%)
- **speed_penup**: Pen-up movement speed (1-100%)
- **pen_pos_down**: Pen down position (0-100%)
- **pen_pos_up**: Pen up position (0-100%)
- **handling**: Movement handling mode (1=Technical, 2=Handwriting, 3=Sketching, 4=Constant)
- **model**: NextDraw model (8=8511, 9=1117, 10=2234)

#### Update Configuration via API

```bash
curl -X PUT http://localhost/config \
  -H "Content-Type: application/json" \
  -d '{"plotter_settings": {"speed_pendown": 30}}'
```

## Usage Examples

### Submit a Plot Job

```bash
curl -X POST http://localhost/plot \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Plot",
    "svg_content": "<svg>...</svg>",
    "config": {
      "speed_pendown": 20,
      "pen_pos_down": 35
    }
  }'
```

#### Plot Job Parameters

The `/plot` endpoint accepts the following parameters:

**Required:**
- `svg_content` (string) OR `svg_file` (string): SVG content or file path
- `name` (string): Job name for identification

**Optional:**
- `description` (string): Job description
- `priority` (integer): Job priority (default: 1)
- `start_mm` (number): Start position in millimeters from beginning of plot
- `config` (object): Configuration overrides for this job

**Configuration Override Options:**
- `speed_pendown` (1-100): Pen-down movement speed percentage
- `speed_penup` (1-100): Pen-up movement speed percentage
- `pen_pos_down` (0-100): Pen down position percentage
- `pen_pos_up` (0-100): Pen up position percentage
- `handling` (1-4): Movement handling mode (1=Technical, 2=Handwriting, 3=Sketching, 4=Constant)
- `auto_rotate` (boolean): Enable auto-rotation for tall documents
- `reordering` (0-4): Path optimization level
- `report_time` (boolean): Report plotting time and statistics

### Submit a Plot Job with Start Position

You can specify a start position in millimeters to resume plotting from a specific point:

```bash
curl -X POST http://localhost/plot \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Resume Plot",
    "svg_content": "<svg>...</svg>",
    "start_mm": 25.5,
    "config": {
      "speed_pendown": 20
    }
  }'
```

This corresponds to the NextDraw Python API's `res_adj_mm` option and allows you to start plotting from a specific distance (in millimeters) into the drawing path. This is useful for:
- Resuming interrupted plots
- Testing specific portions of a drawing
- Creating partial plots

For multipart file uploads, include the `start_mm` parameter in the form data:

```bash
curl -X POST http://localhost/plot \
  -F "svg_file=@drawing.svg" \
  -F "name=Resume Plot" \
  -F "start_mm=25.5" \
  -F 'config={"speed_pendown": 20}'
```

### Check Status

```bash
curl http://localhost/status
```

### Get Job Queue

```bash
curl http://localhost/jobs
```

### Utility Commands

```bash
# Move to home position
curl -X POST http://localhost/utility/home

# Raise pen
curl -X POST http://localhost/utility/raise_pen

# Manual movement
curl -X POST http://localhost/utility/move \
  -H "Content-Type: application/json" \
  -d '{"direction": "x", "distance": 10, "units": "mm"}'
```

## Remote Updates

### Automatic Updates

```bash
curl -X POST http://localhost/update \
  -H "Content-Type: application/json" \
  -d '{"branch": "main", "force": false}'
```

### Manual Updates

```bash
cd /home/james/plot-runner-agent
./update.sh
```

## Service Management

### Control the Service

```bash
# Start
sudo systemctl start nextdraw-api

# Stop
sudo systemctl stop nextdraw-api

# Restart
sudo systemctl restart nextdraw-api

# Check status
sudo systemctl status nextdraw-api

# View logs
sudo journalctl -u nextdraw-api -f
```

### Check Service Health

```bash
# Application health
curl http://localhost/health

# System resources
htop

# USB devices
lsusb | grep -i axidraw
```

## Monitoring & Logs

### Log Locations

- Application logs: `/home/james/plot-runner-agent/logs/app.log`
- System logs: `sudo journalctl -u nextdraw-api`
- Nginx logs: `/var/log/nginx/`
- Gunicorn logs: `/home/james/plot-runner-agent/logs/gunicorn*.log`

### Log Monitoring

```bash
# Real-time application logs
tail -f /home/james/plot-runner-agent/logs/app.log

# Real-time system logs
sudo journalctl -u nextdraw-api -f

# API endpoint for logs
curl http://localhost/logs?lines=50
```

## Troubleshooting

### Common Issues

#### 1. Plotter Not Detected

```bash
# Check USB connection
lsusb | grep -i "04d8"

# Check permissions
groups pi | grep plugdev

# Reload USB rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Check device files
ls -la /dev/ttyACM*
```

#### 2. Service Won't Start

```bash
# Check service status
sudo systemctl status nextdraw-api

# Check logs
sudo journalctl -u nextdraw-api -n 50

# Check Python environment
cd /home/james/plot-runner-agent
source venv/bin/activate
python -c "import nextdraw; print('NextDraw imported successfully')"
```

#### 3. Permission Errors

```bash
# Fix file permissions
sudo chown -R pi:pi /home/james/plot-runner-agent
chmod +x /home/james/plot-runner-agent/app.py

# Check sudo permissions for restart
sudo -l | grep systemctl
```

#### 4. Network Issues

```bash
# Check if service is listening
sudo netstat -tlnp | grep :5000

# Check nginx status
sudo systemctl status nginx
sudo nginx -t

# Check firewall
sudo ufw status
```

### Diagnostic Commands

```bash
# Full system diagnostic
cd /home/james/plot-runner-agent
./diagnose.sh

# Manual diagnostic steps
curl http://localhost/health
curl http://localhost/status
sudo systemctl status nextdraw-api nginx
journalctl -u nextdraw-api --since "1 hour ago"
```

## Security Considerations

### Network Security

- The API runs on port 5000 locally
- Nginx proxy provides external access on port 80
- Configure firewall appropriately for your network
- Consider VPN access for remote management

### USB Security

- USB devices are restricted to plugdev group
- Service runs as non-root user (pi)
- File system permissions are restrictive

### Update Security

- Updates require git repository access
- Service restart requires sudo privileges
- Consider restricting update endpoint access

## Multiple Plotter Setup

For multiple plotters, deploy separate instances:

```bash
# Plotter 1 (default)
/home/james/plot-runner-agent-1 (port 5001)

# Plotter 2
/home/james/plot-runner-agent-2 (port 5002)

# Plotter 3
/home/james/plot-runner-agent-3 (port 5003)
```

Each instance should have:
- Unique port configuration
- Separate systemd service
- Separate nginx upstream
- Specific USB device targeting

## Performance Tuning

### Raspberry Pi Optimization

```bash
# Increase USB buffer size
echo 'dwc_otg.fiq_buffer_size=256' | sudo tee -a /boot/config.txt

# Optimize for stability
echo 'arm_freq=1400' | sudo tee -a /boot/config.txt
echo 'core_freq=500' | sudo tee -a /boot/config.txt

# Disable unnecessary services
sudo systemctl disable bluetooth hciuart
```

### Application Tuning

- Adjust worker count in `gunicorn.conf.py`
- Modify timeout values for long plots
- Configure job queue size limits
- Set appropriate log rotation

## API Integration Examples

### Python Client

```python
import requests

class NextDrawClient:
    def __init__(self, base_url):
        self.base_url = base_url

    def submit_plot(self, svg_content, config=None):
        response = requests.post(f"{self.base_url}/plot", json={
            "svg_content": svg_content,
            "config": config or {}
        })
        return response.json()

    def get_status(self):
        response = requests.get(f"{self.base_url}/status")
        return response.json()

# Usage
client = NextDrawClient("http://plotter-pi.local")
result = client.submit_plot("<svg>...</svg>", {"speed_pendown": 25})
```

### JavaScript/Node.js Client

```javascript
class NextDrawClient {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async submitPlot(svgContent, config = {}) {
        const response = await fetch(`${this.baseUrl}/plot`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                svg_content: svgContent,
                config: config
            })
        });
        return response.json();
    }

    async getStatus() {
        const response = await fetch(`${this.baseUrl}/status`);
        return response.json();
    }
}

// Usage
const client = new NextDrawClient('http://plotter-pi.local');
const result = await client.submitPlot('<svg>...</svg>', {speed_pendown: 25});
```

## Development

### Local Development

```bash
cd plot-runner-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# For development without actual NextDraw
export NEXTDRAW_MOCK=1
python app.py
```

### Testing

```bash
# Install test dependencies
pip install pytest pytest-flask

# Run tests
pytest tests/

# API testing
curl -X POST http://localhost:5000/plot \
  -H "Content-Type: application/json" \
  -d '{"svg_content": "<svg><circle cx=\"50\" cy=\"50\" r=\"40\"/></svg>"}'
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## Support

### Resources

- [NextDraw Documentation](https://bantam.tools/nd_py/)
- [NextDraw User Guide](https://bantam.tools/nextdraw/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Raspberry Pi Documentation](https://www.raspberrypi.org/documentation/)

### Getting Help

1. Check the troubleshooting section
2. Review logs for error messages
3. Test with minimal SVG files
4. Verify hardware connections
5. Create GitHub issue with:
   - System information
   - Error logs
   - Steps to reproduce
   - Expected vs actual behavior

## License

[Your License Here]

## Changelog

### v1.0.0
- Initial release
- Complete REST API
- Job queue management
- Remote update capability
- Raspberry Pi deployment automation
