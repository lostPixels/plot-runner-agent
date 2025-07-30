#!/bin/bash

# NextDraw Plotter API - Ansible Deployment Wrapper Script
# This script simplifies the deployment process

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INVENTORY_FILE="${SCRIPT_DIR}/inventory.ini"
PLAYBOOK_FILE="${SCRIPT_DIR}/deploy_app.yml"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"

# Default options
LIMIT=""
CHECK_MODE=""
VERBOSE=""
TAGS=""
SKIP_TAGS=""

# Functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy NextDraw Plotter API to Raspberry Pi devices using Ansible.

OPTIONS:
    -h, --help          Show this help message
    -l, --limit HOST    Deploy to specific host(s) only
    -c, --check         Run in check mode (dry run)
    -v, --verbose       Enable verbose output
    -t, --tags TAGS     Only run tasks with these tags
    -s, --skip TAGS     Skip tasks with these tags
    --setup             Install Ansible requirements only
    --test              Test connectivity to all hosts
    --list-hosts        List all configured hosts
    --troubleshoot      Run troubleshooting playbook for 502 errors
    --fix-502           Copy and run local troubleshooting script
    --emergency-fix     Fix missing application files
    --fix-venv          Fix missing or broken virtual environment
    --fix-all           Comprehensive fix for all common issues

EXAMPLES:
    # Deploy to all hosts
    $0

    # Deploy to specific host
    $0 -l nextdraw1.local

    # Dry run with verbose output
    $0 -c -v

    # Test connectivity
    $0 --test

    # Troubleshoot 502 errors
    $0 --troubleshoot

    # Fix 502 on specific host
    $0 --fix-502 -l nextdraw1.local

EOF
    exit 1
}

check_prerequisites() {
    log "Checking prerequisites..."

    # Check if Python is installed
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is not installed. Please install Python 3.7 or later."
        exit 1
    fi

    # Check if Ansible is installed
    if ! command -v ansible &> /dev/null; then
        warning "Ansible is not installed."
        read -p "Would you like to install Ansible now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            install_ansible
        else
            error "Ansible is required to run this deployment."
            exit 1
        fi
    fi

    # Check if inventory file exists
    if [ ! -f "$INVENTORY_FILE" ]; then
        error "Inventory file not found: $INVENTORY_FILE"
        error "Please create the inventory file with your Raspberry Pi hosts."
        exit 1
    fi

    # Check if playbook exists
    if [ ! -f "$PLAYBOOK_FILE" ]; then
        error "Playbook file not found: $PLAYBOOK_FILE"
        exit 1
    fi

    # Check for Node.js if frontend directory exists
    if [ -d "${SCRIPT_DIR}/../frontend" ]; then
        if ! command -v npm &> /dev/null; then
            warning "Frontend directory found but npm is not installed."
            warning "Frontend build will be skipped."
        fi
    fi

    log "Prerequisites check completed."
}

install_ansible() {
    log "Installing Ansible..."

    if [ -f "$REQUIREMENTS_FILE" ]; then
        pip3 install --user -r "$REQUIREMENTS_FILE"
    else
        pip3 install --user ansible
    fi

    # Add user's pip bin directory to PATH if needed
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        export PATH="$HOME/.local/bin:$PATH"
        info "Added ~/.local/bin to PATH for this session."
        info "Consider adding it permanently to your shell profile."
    fi
}

test_connectivity() {
    log "Testing connectivity to all hosts..."
    ansible -i "$INVENTORY_FILE" all -m ping

    if [ $? -eq 0 ]; then
        log "All hosts are reachable!"
    else
        error "Some hosts are not reachable. Please check your inventory and SSH configuration."
        exit 1
    fi
}

list_hosts() {
    log "Configured hosts in inventory:"
    ansible-inventory -i "$INVENTORY_FILE" --list --yaml | grep -E "^\s+[^:]+:$" | sed 's/://g' | sed 's/^[ \t]*/  - /'
}

run_deployment() {
    local ansible_args="-i $INVENTORY_FILE"

    # Add optional arguments
    [ -n "$LIMIT" ] && ansible_args="$ansible_args --limit $LIMIT"
    [ -n "$CHECK_MODE" ] && ansible_args="$ansible_args --check"
    [ -n "$VERBOSE" ] && ansible_args="$ansible_args -vvv"
    [ -n "$TAGS" ] && ansible_args="$ansible_args --tags $TAGS"
    [ -n "$SKIP_TAGS" ] && ansible_args="$ansible_args --skip-tags $SKIP_TAGS"

    log "Starting deployment..."

    if [ -n "$CHECK_MODE" ]; then
        info "Running in CHECK MODE (dry run) - no changes will be made"
    fi

    if [ -n "$LIMIT" ]; then
        info "Deploying to: $LIMIT"
    else
        info "Deploying to all hosts"
    fi

    # Run the playbook
    ansible-playbook $ansible_args "$PLAYBOOK_FILE"

    if [ $? -eq 0 ]; then
        log "Deployment completed successfully!"

        if [ -z "$CHECK_MODE" ]; then
            echo
            info "Next steps:"
            echo "  1. Check service status: ansible -i $INVENTORY_FILE all -m shell -a 'systemctl status nextdraw-api' --become"
            echo "  2. View logs: ssh <hostname> 'sudo journalctl -u nextdraw-api -f'"
            echo "  3. Test API: curl http://<hostname>/health"
        fi
    else
        error "Deployment failed. Please check the error messages above."
        exit 1
    fi
}

run_troubleshooting() {
    log "Running troubleshooting playbook for 502 errors..."

    local ansible_args="-i $INVENTORY_FILE"
    [ -n "$LIMIT" ] && ansible_args="$ansible_args --limit $LIMIT"
    [ -n "$VERBOSE" ] && ansible_args="$ansible_args -vvv"

    ansible-playbook $ansible_args "${SCRIPT_DIR}/troubleshoot.yml"

    if [ $? -eq 0 ]; then
        log "Troubleshooting completed!"
    else
        error "Troubleshooting failed. Please check the output above."
        exit 1
    fi
}

fix_502_local() {
    log "Copying and running local troubleshooting script..."

    if [ -z "$LIMIT" ]; then
        error "Please specify a host with -l option for --fix-502"
        exit 1
    fi

    # Copy the troubleshooting script to the host
    log "Copying troubleshooting script to $LIMIT..."
    scp "${SCRIPT_DIR}/troubleshoot_502.sh" "$LIMIT:/tmp/troubleshoot_502.sh"

    if [ $? -ne 0 ]; then
        error "Failed to copy troubleshooting script to $LIMIT"
        exit 1
    fi

    # Run the script on the host
    log "Running troubleshooting script on $LIMIT..."
    ssh "$LIMIT" "chmod +x /tmp/troubleshoot_502.sh && sudo /tmp/troubleshoot_502.sh"

    if [ $? -eq 0 ]; then
        log "Troubleshooting script completed!"
    else
        error "Troubleshooting script failed. Please check the output above."
        exit 1
    fi
}

run_emergency_fix() {
    log "Running emergency fix for missing application files..."

    local ansible_args="-i $INVENTORY_FILE"
    [ -n "$LIMIT" ] && ansible_args="$ansible_args --limit $LIMIT"
    [ -n "$VERBOSE" ] && ansible_args="$ansible_args -vvv"

    if [ ! -f "${SCRIPT_DIR}/fix_missing_app.yml" ]; then
        error "Emergency fix playbook not found: ${SCRIPT_DIR}/fix_missing_app.yml"
        exit 1
    fi

    ansible-playbook $ansible_args "${SCRIPT_DIR}/fix_missing_app.yml"

    if [ $? -eq 0 ]; then
        log "Emergency fix completed!"
        info "The application files should now be properly deployed."
    else
        error "Emergency fix failed. Please check the output above."
        exit 1
    fi
}

run_venv_fix() {
    log "Running virtual environment fix..."

    local ansible_args="-i $INVENTORY_FILE"
    [ -n "$LIMIT" ] && ansible_args="$ansible_args --limit $LIMIT"
    [ -n "$VERBOSE" ] && ansible_args="$ansible_args -vvv"

    if [ ! -f "${SCRIPT_DIR}/fix_venv.yml" ]; then
        error "Virtual environment fix playbook not found: ${SCRIPT_DIR}/fix_venv.yml"
        exit 1
    fi

    ansible-playbook $ansible_args "${SCRIPT_DIR}/fix_venv.yml"

    if [ $? -eq 0 ]; then
        log "Virtual environment fix completed!"
        info "The service should now be able to start properly."
    else
        error "Virtual environment fix failed. Please check the output above."
        exit 1
    fi
}

run_fix_all() {
    log "Running comprehensive fix for all issues..."

    local ansible_args="-i $INVENTORY_FILE"
    [ -n "$LIMIT" ] && ansible_args="$ansible_args --limit $LIMIT"
    [ -n "$VERBOSE" ] && ansible_args="$ansible_args -vvv"

    if [ ! -f "${SCRIPT_DIR}/fix_all.yml" ]; then
        error "Comprehensive fix playbook not found: ${SCRIPT_DIR}/fix_all.yml"
        exit 1
    fi

    ansible-playbook $ansible_args "${SCRIPT_DIR}/fix_all.yml"

    if [ $? -eq 0 ]; then
        log "Comprehensive fix completed!"
        info "All common issues should now be resolved."
    else
        error "Comprehensive fix failed. Please check the output above."
        exit 1
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        -l|--limit)
            LIMIT="$2"
            shift 2
            ;;
        -c|--check)
            CHECK_MODE="1"
            shift
            ;;
        -v|--verbose)
            VERBOSE="1"
            shift
            ;;
        -t|--tags)
            TAGS="$2"
            shift 2
            ;;
        -s|--skip)
            SKIP_TAGS="$2"
            shift 2
            ;;
        --setup)
            check_prerequisites
            exit 0
            ;;
        --test)
            check_prerequisites
            test_connectivity
            exit 0
            ;;
        --list-hosts)
            check_prerequisites
            list_hosts
            exit 0
            ;;
        --troubleshoot)
            check_prerequisites
            run_troubleshooting
            exit 0
            ;;
        --fix-502)
            check_prerequisites
            fix_502_local
            exit 0
            ;;
        --emergency-fix)
            check_prerequisites
            run_emergency_fix
            exit 0
            ;;
        --fix-venv)
            check_prerequisites
            run_venv_fix
            exit 0
            ;;
        --fix-all)
            check_prerequisites
            run_fix_all
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            usage
            ;;
    esac
done

# Main execution
log "NextDraw Plotter API Deployment Script"
echo "======================================"

# Check prerequisites
check_prerequisites

# Ask for confirmation if not in check mode
if [ -z "$CHECK_MODE" ]; then
    echo
    warning "This will deploy the NextDraw Plotter API to the following hosts:"
    list_hosts
    echo
    read -p "Do you want to proceed? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Deployment cancelled."
        exit 0
    fi
fi

# Test connectivity
info "Testing connectivity..."
if ! ansible -i "$INVENTORY_FILE" all -m ping ${LIMIT:+--limit $LIMIT} &> /dev/null; then
    error "Cannot connect to some hosts. Running detailed connectivity test..."
    test_connectivity
    exit 1
fi

# Run the deployment
run_deployment

# Exit successfully
exit 0
