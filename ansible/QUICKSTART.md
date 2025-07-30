# NextDraw Plotter API - Ansible Quick Start Guide

Get your NextDraw Plotter API deployed to Raspberry Pis in under 5 minutes!

## 🚀 Quick Setup

### 1. Prerequisites Check
```bash
# Check Python 3
python3 --version

# Install Ansible (if not installed)
pip3 install ansible
```

### 2. Configure Your Hosts
Edit `inventory.ini` with your Raspberry Pi details:
```ini
[raspberry_pis]
# Use hostnames
nextdraw1.local ansible_user=james

# Or IP addresses
192.168.1.100 ansible_user=pi
```

### 3. Set Up SSH Access
```bash
# Generate SSH key (if you don't have one)
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""

# Copy to each Pi (replace with your hostname/IP)
ssh-copy-id james@nextdraw1.local
```

### 4. Deploy!
```bash
# Test connectivity first
./deploy.sh --test

# Run deployment
./deploy.sh

# Or deploy to specific host
./deploy.sh -l nextdraw1.local
```

## ✅ Verify Deployment

### Check Services
```bash
# Check all hosts at once
ansible -i inventory.ini all -m shell -a "systemctl status nextdraw-api" --become

# Or SSH to individual Pi
ssh james@nextdraw1.local
sudo systemctl status nextdraw-api
```

### Test the API
```bash
# Replace with your Pi's hostname or IP
curl http://nextdraw1.local/health
curl http://nextdraw1.local/status
```

## 📋 Common Commands

### Deploy Commands
```bash
# Full deployment
./deploy.sh

# Dry run (see what would change)
./deploy.sh --check

# Deploy with verbose output
./deploy.sh --verbose

# Deploy to specific hosts
./deploy.sh --limit "nextdraw1.local,nextdraw2.local"

# List all configured hosts
./deploy.sh --list-hosts
```

### Service Management
```bash
# Restart service on all hosts
ansible -i inventory.ini all -m systemd -a "name=nextdraw-api state=restarted" --become

# View logs
ssh james@nextdraw1.local 'sudo journalctl -u nextdraw-api -f'
```

## 🔧 Troubleshooting

### Can't Connect to Pi?
```bash
# Check if Pi is reachable
ping nextdraw1.local

# Test SSH directly
ssh -v james@nextdraw1.local

# Ensure SSH is enabled on Pi
# (Do this from Pi's console if needed)
sudo systemctl enable ssh
sudo systemctl start ssh
```

### Service Won't Start?
```bash
# Check service logs
ssh james@nextdraw1.local
sudo journalctl -u nextdraw-api -n 50

# Check if port is already in use
sudo netstat -tlnp | grep 5000

# Restart service manually
sudo systemctl restart nextdraw-api
```

### Plotter Not Detected?
```bash
# Trigger USB detection
ssh james@nextdraw1.local
sudo udevadm trigger

# Check USB devices
lsusb

# Check permissions
ls -la /dev/ttyUSB* /dev/ttyACM*
```

## 📁 File Locations on Pi

- **Application**: `/home/james/plot-runner-agent/`
- **Config**: `/home/james/plot-runner-agent/config.json`
- **Logs**: `/home/james/plot-runner-agent/logs/`
- **Service**: `/etc/systemd/system/nextdraw-api.service`
- **Nginx**: `/etc/nginx/sites-available/nextdraw-api`

## 🎯 Next Steps

1. **Configure your plotter** - Edit `config.json` on each Pi
2. **Upload a test plot** - Use the API to send a simple SVG
3. **Set up monitoring** - Check logs regularly
4. **Plan updates** - Use the update script or re-run Ansible

## 💡 Pro Tips

- Use `tmux` or `screen` when running long deployments
- Set up host-specific configs in `host_vars/` directory
- Create SSH config aliases for easier access:
  ```bash
  # Add to ~/.ssh/config
  Host nextdraw1
      HostName nextdraw1.local
      User james
      Port 22
  ```
- Use Ansible vault for sensitive data:
  ```bash
  ansible-vault create secret_vars.yml
  ```

## 📚 More Help

- Full documentation: See `README.md`
- API documentation: See main project's `api-documentation.md`
- Ansible help: `ansible-doc -h`
- Get deployment help: `./deploy.sh --help`
