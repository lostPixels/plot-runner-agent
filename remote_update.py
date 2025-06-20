"""
Remote Update Manager for NextDraw Plotter API
Handles remote code updates via git pull and system restart.
"""

import os
import subprocess
import logging
import threading
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

class RemoteUpdateManager:
    """Manages remote updates of the application code"""

    def __init__(self):
        self.update_in_progress = False
        self.last_update = None
        self.git_repo_path = os.path.dirname(os.path.abspath(__file__))

    def _check_git_available(self) -> bool:
        """Check if git command is available"""
        try:
            # Use 'which git' on Unix or 'where git' on Windows to check if git is in PATH
            cmd = 'which' if os.name != 'nt' else 'where'
            result = subprocess.run(
                [cmd, 'git'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def check_git_status(self) -> Dict[str, Any]:
        """Check git repository status"""
        try:
            # Check if git is available
            if not self._check_git_available():
                return {"error": "Git command not found. Please install git or add it to your PATH."}

            # Check if we're in a git repository
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.git_repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return {"error": "Not a git repository or git not available"}

            # Check for uncommitted changes
            has_changes = bool(result.stdout.strip())

            # Get current branch
            branch_result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.git_repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

            # Get current commit
            commit_result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.git_repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            current_commit = commit_result.stdout.strip()[:8] if commit_result.returncode == 0 else "unknown"

            # Check for remote changes
            try:
                subprocess.run(
                    ['git', 'fetch'],
                    cwd=self.git_repo_path,
                    capture_output=True,
                    timeout=30
                )

                ahead_behind_result = subprocess.run(
                    ['git', 'rev-list', '--left-right', '--count', f'HEAD...origin/{current_branch}'],
                    cwd=self.git_repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if ahead_behind_result.returncode == 0:
                    ahead, behind = ahead_behind_result.stdout.strip().split('\t')
                    updates_available = int(behind) > 0
                else:
                    updates_available = False

            except Exception:
                updates_available = False

            return {
                "current_branch": current_branch,
                "current_commit": current_commit,
                "has_uncommitted_changes": has_changes,
                "updates_available": updates_available,
                "last_update": self.last_update
            }

        except subprocess.TimeoutExpired:
            return {"error": "Git command timed out"}
        except Exception as e:
            return {"error": f"Error checking git status: {str(e)}"}

    def update(self, branch: str = "main", force: bool = False) -> Dict[str, Any]:
        """Perform remote update"""
        try:
            if self.update_in_progress:
                return {"error": "Update already in progress"}

            self.update_in_progress = True
            logger.info(f"Starting update to branch: {branch}")

            # Check if git is available
            if not self._check_git_available():
                return {
                    "error": "Git command not found. Please install git or add it to your PATH.",
                    "help": "You may need to install git with 'sudo apt-get install git' or equivalent for your system."
                }

            # Check git status first
            git_status = self.check_git_status()
            if "error" in git_status:
                return git_status

            # Check for uncommitted changes
            if git_status.get("has_uncommitted_changes") and not force:
                return {
                    "error": "Uncommitted changes detected. Use force=true to override.",
                    "git_status": git_status
                }

            # Stash changes if force is enabled
            if force and git_status.get("has_uncommitted_changes"):
                logger.info("Stashing uncommitted changes")
                stash_result = subprocess.run(
                    ['git', 'stash'],
                    cwd=self.git_repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if stash_result.returncode != 0:
                    logger.warning("Failed to stash changes")

            # Fetch latest changes
            logger.info("Fetching latest changes")
            fetch_result = subprocess.run(
                ['git', 'fetch', 'origin'],
                cwd=self.git_repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )

            if fetch_result.returncode != 0:
                return {"error": f"Failed to fetch changes: {fetch_result.stderr}"}

            # Switch to target branch if different
            current_branch = git_status.get("current_branch", "")
            if current_branch != branch:
                logger.info(f"Switching from {current_branch} to {branch}")
                checkout_result = subprocess.run(
                    ['git', 'checkout', branch],
                    cwd=self.git_repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if checkout_result.returncode != 0:
                    return {"error": f"Failed to checkout branch {branch}: {checkout_result.stderr}"}

            # Pull latest changes
            logger.info("Pulling latest changes")
            pull_result = subprocess.run(
                ['git', 'pull', 'origin', branch],
                cwd=self.git_repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )

            if pull_result.returncode != 0:
                return {"error": f"Failed to pull changes: {pull_result.stderr}"}

            # Check if any files were updated
            files_changed = "Already up to date" not in pull_result.stdout

            # Install/update dependencies if requirements.txt exists
            requirements_file = os.path.join(self.git_repo_path, 'requirements.txt')
            if os.path.exists(requirements_file) and files_changed:
                logger.info("Updating Python dependencies")
                pip_result = subprocess.run(
                    ['pip', 'install', '-r', 'requirements.txt'],
                    cwd=self.git_repo_path,
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if pip_result.returncode != 0:
                    logger.warning(f"Failed to update dependencies: {pip_result.stderr}")

            # Record successful update
            self.last_update = datetime.now().isoformat()

            # Schedule restart if files were changed
            restart_needed = files_changed
            if restart_needed:
                logger.info("Scheduling application restart")
                threading.Thread(target=self._delayed_restart, daemon=True).start()

            return {
                "success": True,
                "message": "Update completed successfully",
                "files_changed": files_changed,
                "restart_scheduled": restart_needed,
                "last_update": self.last_update,
                "branch": branch,
                "output": pull_result.stdout
            }

        except subprocess.TimeoutExpired:
            return {"error": "Update operation timed out"}
        except Exception as e:
            logger.error(f"Update failed: {str(e)}")
            return {"error": f"Update failed: {str(e)}"}
        finally:
            self.update_in_progress = False

    def _delayed_restart(self):
        """Restart the application after a delay"""
        import time
        time.sleep(5)  # Give time for the response to be sent

        try:
            logger.info("Restarting application")

            # Try systemctl restart first (for systemd service)
            try:
                subprocess.run(['sudo', 'systemctl', 'restart', 'nextdraw-api'], timeout=10)
                return
            except:
                pass

            # Try supervisorctl restart (for supervisor)
            try:
                subprocess.run(['sudo', 'supervisorctl', 'restart', 'nextdraw-api'], timeout=10)
                return
            except:
                pass

            # Fallback: exit the process (assuming it's managed by a process manager)
            logger.info("Exiting process for restart")
            os._exit(0)

        except Exception as e:
            logger.error(f"Failed to restart application: {str(e)}")

    def rollback(self, commit_hash: str | None = None) -> Dict[str, Any]:
        """Rollback to a previous commit"""
        try:
            if self.update_in_progress:
                return {"error": "Update in progress, cannot rollback"}

            # Check if git is available
            if not self._check_git_available():
                return {
                    "error": "Git command not found. Please install git or add it to your PATH.",
                    "help": "You may need to install git with 'sudo apt-get install git' or equivalent for your system."
                }

            self.update_in_progress = True

            if commit_hash is None:
                # Get the previous commit
                result = subprocess.run(
                    ['git', 'rev-parse', 'HEAD~1'],
                    cwd=self.git_repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    return {"error": "Could not determine previous commit"}

                commit_hash = result.stdout.strip() if result.stdout else "HEAD~1"

            logger.info(f"Rolling back to commit: {commit_hash}")

            # Reset to the specified commit
            # At this point commit_hash is guaranteed to be a string
            assert isinstance(commit_hash, str), "commit_hash must be a string"
            reset_result = subprocess.run(
                ['git', 'reset', '--hard', commit_hash],
                cwd=self.git_repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            if reset_result.returncode != 0:
                return {"error": f"Failed to rollback: {reset_result.stderr}"}

            self.last_update = datetime.now().isoformat()

            # Schedule restart
            threading.Thread(target=self._delayed_restart, daemon=True).start()

            return {
                "success": True,
                "message": f"Rolled back to commit {commit_hash[:8]}",
                "commit": commit_hash,
                "restart_scheduled": True
            }

        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}")
            return {"error": f"Rollback failed: {str(e)}"}
        finally:
            self.update_in_progress = False

    def get_update_status(self) -> Dict[str, Any]:
        """Get current update status"""
        if not self._check_git_available():
            git_status = {
                "error": "Git command not found. Please install git or add it to your PATH.",
                "help": "You may need to install git with 'sudo apt-get install git' or equivalent for your system."
            }
        else:
            git_status = self.check_git_status()

        return {
            "update_in_progress": self.update_in_progress,
            "last_update": self.last_update,
            "git_status": git_status,
            "git_available": self._check_git_available()
        }
