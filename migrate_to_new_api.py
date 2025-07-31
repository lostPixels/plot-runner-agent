#!/usr/bin/env python3
"""
Migration script to switch from old job-based API to new project-based API
"""

import os
import sys
import shutil
import datetime
import json

def create_backup_dir():
    """Create backup directory with timestamp"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backup_{timestamp}"
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir

def backup_files(backup_dir):
    """Backup important files before migration"""
    files_to_backup = [
        'app.py',
        'job_queue.py',
        'job_queue.json',
        'uploads'  # directory
    ]

    backed_up = []

    for file_path in files_to_backup:
        if os.path.exists(file_path):
            dest_path = os.path.join(backup_dir, file_path)

            if os.path.isdir(file_path):
                shutil.copytree(file_path, dest_path)
            else:
                # Create parent directory if needed
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(file_path, dest_path)

            backed_up.append(file_path)
            print(f"✓ Backed up: {file_path}")

    return backed_up

def migrate_config():
    """Migrate configuration if needed"""
    config_file = 'config.json'

    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)

            # Remove any job-queue specific settings
            if 'job_queue' in config:
                del config['job_queue']

            # Add project-specific defaults if missing
            if 'project_settings' not in config:
                config['project_settings'] = {
                    'max_layers': 10,
                    'storage_dir': 'projects'
                }

            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)

            print("✓ Updated configuration file")
        except Exception as e:
            print(f"⚠ Warning: Could not update config file: {e}")

def perform_migration():
    """Perform the actual migration"""
    print("\n=== NextDraw API Migration Tool ===")
    print("Migrating from job-based to project-based API\n")

    # Check if new app exists
    if not os.path.exists('app_new.py'):
        print("❌ Error: app_new.py not found!")
        print("Make sure you have the new API implementation file.")
        return False

    # Check if project_manager exists
    if not os.path.exists('project_manager.py'):
        print("❌ Error: project_manager.py not found!")
        print("Make sure you have the project manager module.")
        return False

    # Create backup
    print("Step 1: Creating backup...")
    backup_dir = create_backup_dir()
    backed_up = backup_files(backup_dir)

    if backed_up:
        print(f"\n✓ Backup created in: {backup_dir}")

    # Rename files
    print("\nStep 2: Switching to new API...")

    try:
        # Rename old app.py to app_old.py
        if os.path.exists('app.py'):
            shutil.move('app.py', 'app_old.py')
            print("✓ Renamed app.py to app_old.py")

        # Rename app_new.py to app.py
        shutil.move('app_new.py', 'app.py')
        print("✓ Renamed app_new.py to app.py")

    except Exception as e:
        print(f"❌ Error during file operations: {e}")
        return False

    # Update configuration
    print("\nStep 3: Updating configuration...")
    migrate_config()

    # Create project storage directory
    print("\nStep 4: Creating project storage...")
    os.makedirs('projects', exist_ok=True)
    print("✓ Created projects directory")

    # Clean up old job files
    print("\nStep 5: Cleaning up old job data...")
    if os.path.exists('job_queue.json'):
        os.rename('job_queue.json', 'job_queue.json.old')
        print("✓ Renamed job_queue.json to job_queue.json.old")

    print("\n=== Migration Complete! ===")
    print("\nImportant notes:")
    print("1. The old API is backed up in:", backup_dir)
    print("2. The old app.py is now app_old.py")
    print("3. Review API_DOCUMENTATION.md for new endpoints")
    print("4. Update your client applications using MIGRATION_GUIDE.md")
    print("\nTo revert this migration, restore files from the backup directory.")

    return True

def check_dependencies():
    """Check if all required dependencies are installed"""
    print("\nChecking dependencies...")

    required_modules = [
        'flask',
        'flask_cors',
        'werkzeug'
    ]

    missing = []

    for module in required_modules:
        try:
            __import__(module)
            print(f"✓ {module} is installed")
        except ImportError:
            missing.append(module)
            print(f"❌ {module} is missing")

    if missing:
        print("\n⚠ Missing dependencies detected!")
        print("Run: pip install -r requirements.txt")
        return False

    return True

def main():
    """Main migration function"""
    print("This script will migrate your NextDraw API to the new project-based system.")
    print("Your current files will be backed up before any changes are made.")

    # Check current directory
    if not os.path.exists('app.py'):
        print("\n❌ Error: app.py not found in current directory!")
        print("Please run this script from the plot-runner-agent directory.")
        sys.exit(1)

    # Check dependencies
    if not check_dependencies():
        print("\nPlease install missing dependencies before continuing.")
        sys.exit(1)

    # Confirm migration
    print("\nDo you want to proceed with the migration? (yes/no): ", end='')
    response = input().strip().lower()

    if response != 'yes':
        print("Migration cancelled.")
        sys.exit(0)

    # Perform migration
    if perform_migration():
        print("\n✅ Migration successful!")
        print("\nNext steps:")
        print("1. Restart your Flask application")
        print("2. Test the new endpoints with: curl http://localhost:5000/health")
        print("3. Update your client applications")
    else:
        print("\n❌ Migration failed!")
        print("Check the errors above and try again.")
        sys.exit(1)

if __name__ == "__main__":
    main()
