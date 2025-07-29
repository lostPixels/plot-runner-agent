#!/bin/bash
# deploy.sh - Script to update the plot-runner-agent repository and restart the service
# Based on functionality in remote_update.py

set -e  # Exit immediately if a command exits with a non-zero status

# Configuration
REPO_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="nextdraw-api"
BRANCH="main"
FORCE=false
UPDATE_DEPS=true

# Parse command line arguments
while getopts "b:fd" opt; do
  case $opt in
    b)
      BRANCH="$OPTARG"
      ;;
    f)
      FORCE=true
      ;;
    d)
      UPDATE_DEPS=false
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      echo "Usage: $0 [-b branch] [-f] [-d]" >&2
      echo "  -b branch: Specify the branch to update to (default: main)" >&2
      echo "  -f: Force update even if there are uncommitted changes" >&2
      echo "  -d: Skip dependency updates" >&2
      exit 1
      ;;
  esac
done

# Function to log messages with timestamp
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Check if git is installed
if ! command -v git &> /dev/null; then
  log "Error: git is not installed. Please install git and try again."
  exit 1
fi

# Navigate to the repository directory
cd "$REPO_PATH"
log "Working in directory: $REPO_PATH"

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree &> /dev/null; then
  log "Error: Not a git repository"
  exit 1
fi

# Check for uncommitted changes
if [[ $FORCE == false ]] && [[ -n "$(git status --porcelain)" ]]; then
  log "Error: Uncommitted changes detected. Use -f to force update."
  log "Current git status:"
  git status --short
  exit 1
fi

# Stash uncommitted changes if force is enabled
if [[ $FORCE == true ]] && [[ -n "$(git status --porcelain)" ]]; then
  log "Stashing uncommitted changes..."
  git stash
fi

# Get current branch and commit for logging
CURRENT_BRANCH=$(git branch --show-current)
CURRENT_COMMIT=$(git rev-parse --short HEAD)
log "Current state: branch=$CURRENT_BRANCH, commit=$CURRENT_COMMIT"

# Fetch latest changes
log "Fetching latest changes..."
git fetch origin

# Switch to target branch if different
if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
  log "Switching from $CURRENT_BRANCH to $BRANCH..."
  git checkout "$BRANCH"
fi

# Pull latest changes
log "Pulling latest changes from origin/$BRANCH..."
PULL_OUTPUT=$(git pull origin "$BRANCH")
log "$PULL_OUTPUT"

# Check if any files were updated
if [[ "$PULL_OUTPUT" == *"Already up to date"* ]]; then
  UPDATED=false
  log "Repository is already up to date."
else
  UPDATED=true
  NEW_COMMIT=$(git rev-parse --short HEAD)
  log "Updated from $CURRENT_COMMIT to $NEW_COMMIT"
fi

# Install/update dependencies if requirements.txt exists and updates were applied
if [[ $UPDATE_DEPS == true ]] && [[ $UPDATED == true ]] && [[ -f "requirements.txt" ]]; then
  log "Updating Python dependencies..."
  if ! pip install -r requirements.txt; then
    log "Warning: Failed to update dependencies"
  fi
fi

# Restart the service if files were changed
if [[ $UPDATED == true ]]; then
  log "Restarting $SERVICE_NAME service..."

  # Try systemctl restart first (for systemd service)
  if command -v systemctl &> /dev/null; then
    if systemctl is-active --quiet "$SERVICE_NAME"; then
      log "Restarting using systemctl..."
      if ! sudo systemctl restart "$SERVICE_NAME"; then
        log "Warning: Failed to restart using systemctl"
      else
        log "Service restarted successfully with systemctl"
      fi
    fi
  fi

  # Try supervisorctl restart (for supervisor)
  if command -v supervisorctl &> /dev/null; then
    if supervisorctl status "$SERVICE_NAME" &> /dev/null; then
      log "Restarting using supervisorctl..."
      if ! sudo supervisorctl restart "$SERVICE_NAME"; then
        log "Warning: Failed to restart using supervisorctl"
      else
        log "Service restarted successfully with supervisorctl"
      fi
    fi
  fi

  log "Deployment completed successfully"
else
  log "No changes to deploy"
fi

exit 0
