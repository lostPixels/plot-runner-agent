# NextDraw Plotter API - Ansible Deployment

This directory contains Ansible playbooks and configuration for deploying the NextDraw Plotter API to multiple Raspberry Pi devices.

## Overview

The deployment process:
1. Builds the frontend locally (if present)
2. Synchronizes all application files to target Raspberry Pis
3. Sets up system dependencies and Python environment
4. Configures services (systemd, nginx)
5. Establishes USB permissions for plotter access
6. Starts and verifies the application

## Prerequisites

### Control Machine (Your Computer)
- Python 3.7+
- Ansible 2.9+
- SSH access to all Raspberry Pis
- Node.js and npm (if frontend exists)

### Target Raspberry Pis
- Raspberry Pi OS (Bullseye or newer recommended)
- SSH enabled
- User account with sudo privileges
- Network connectivity

## Setup Instructions

### 1. Install Ansible on Control Machine

```bash
# Using pip
pip install -r requirements.txt

# Or using system package manager (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install ansible

# Or on macOS
brew install ansible
```

### 2. Configure Inventory

Edit `inventory.ini` to list your Raspberry Pi devices:

```ini
[raspberry_pis]
nextdraw1.local ansible_user=james
axidraw1.local ansible_user=james
plotter3.local ansible_user=pi

# Or use IP addresses
192.168.1.100 ansible_user=james
192.168.1.101 ansible_user=james
```

### 3. Set Up SSH Keys (Recommended)

Generate SSH keys if you haven't already:
```bash
ssh-keygen -t rsa -b 4096
```

Copy your public key to each Raspberry Pi:
```bash
ssh-copy-id james@nextdraw1.local
ssh-copy-id james@axidraw1.local
```

### 4. Test Connectivity

Verify Ansible can connect to all hosts:
```bash
ansible -i inventory.ini all -m ping
```

## Running the Deployment

### Basic Deployment

Deploy to all Raspberry Pis:
```bash
ansible-playbook -i inventory.ini deploy_app.yml
```

### Deploy to Specific Hosts

Deploy to a single host:
```bash
ansible-playbook -i inventory.ini deploy_app.yml --limit nextdraw1.local
```

### Dry Run

Test what would be changed without making modifications:
```bash
ansible-playbook -i inventory.ini deploy_app.yml --check
```

### Verbose Output

For debugging:
```bash
ansible-playbook -i inventory.ini deploy_app.yml -vvv
```

## Configuration Options

### Playbook Variables

The playbook uses these variables (defined in `deploy_app.yml`):

- `app_name`: Service name (default: `nextdraw-api`)
- `app_user`: User to run the service (default: `james`)
- `app_dir`: Installation directory (default: `/home/james/plot-runner-agent`)
- `frontend_dir`: Local frontend directory path

### Per-Host Configuration

You can override variables per host in the inventory:

```ini
[raspberry_pis]
nextdraw1.local ansible_user=james app_dir=/opt/plotter
axidraw1.local ansible_user=pi app_user=pi
```

## Frontend Build Process

If you have a frontend directory:

1. Place it in the project root (same level as the ansible directory)
2. Ensure `package.json` exists with a `build` script
3. The playbook will automatically:
   - Run `npm install`
   - Run `npm run build`
   - Deploy the built files

If no frontend exists, the playbook will skip this step.

## Post-Deployment

### Verify Services

After deployment, services should be running on each Pi:

```bash
# Check via Ansible
ansible -i inventory.ini all -m systemd -a "name=nextdraw-api" --become

# Or SSH to a Pi and check
ssh james@nextdraw1.local
sudo systemctl status nextdraw-api
sudo systemctl status nginx
```

### Access the API

Each Raspberry Pi will be accessible at:
- API: `http://<pi-hostname>/` or `http://<pi-ip>/`
- Health check: `http://<pi-hostname>/health`
- Status: `http://<pi-hostname>/status`

### View Logs

```bash
# Via SSH
sudo journalctl -u nextdraw-api -f

# Application logs
tail -f /home/james/plot-runner-agent/logs/*.log
```

## Updating Deployed Applications

### Using the Update Script

Each Pi has an update script at `/home/james/plot-runner-agent/update.sh`:

```bash
# Run on each Pi
ssh james@nextdraw1.local
cd /home/james/plot-runner-agent
./update.sh
```

### Re-run Ansible Deployment

To update all Pis with latest code:
```bash
ansible-playbook -i inventory.ini deploy_app.yml
```

## Troubleshooting

### Common Issues

1. **SSH Connection Failed**
   - Ensure SSH is enabled on the Pi
   - Check hostname/IP is correct
   - Verify SSH keys are set up

2. **Service Won't Start**
   - Check logs: `sudo journalctl -u nextdraw-api -n 50`
   - Verify Python dependencies installed correctly
   - Check USB permissions: `ls -la /dev/ttyUSB*`

3. **Plotter Not Detected**
   - Run: `sudo udevadm trigger`
   - Logout and login again for group permissions
   - Check USB cable and connections

4. **Frontend Build Fails**
   - Ensure Node.js and npm are installed locally
   - Check `package.json` exists in frontend directory
   - Run build manually to debug: `cd frontend && npm run build`

### Manual Service Management

```bash
# Start/stop/restart service
sudo systemctl start nextdraw-api
sudo systemctl stop nextdraw-api
sudo systemctl restart nextdraw-api

# Enable/disable autostart
sudo systemctl enable nextdraw-api
sudo systemctl disable nextdraw-api

# Reload after config changes
sudo systemctl daemon-reload
```

## Security Considerations

1. **SSH Keys**: Always use SSH keys instead of passwords
2. **Firewall**: The playbook configures ufw if available
3. **User Permissions**: Service runs as non-root user
4. **Resource Limits**: Memory limited to 512MB per service

## Additional Playbooks

You can create additional playbooks for specific tasks:

### update_config.yml
```yaml
---
- name: Update configuration only
  hosts: raspberry_pis
  tasks:
    - name: Update config.json
      copy:
        src: ../config.json
        dest: /home/james/plot-runner-agent/config.json
    - name: Restart service
      systemd:
        name: nextdraw-api
        state: restarted
      become: yes
```

### restart_services.yml
```yaml
---
- name: Restart all services
  hosts: raspberry_pis
  become: yes
  tasks:
    - name: Restart services
      systemd:
        name: "{{ item }}"
        state: restarted
      loop:
        - nextdraw-api
        - nginx
```

## Support

For issues specific to:
- Ansible deployment: Check this README and Ansible documentation
- NextDraw API: See the main project README
- Plotter hardware: Consult NextDraw documentation
