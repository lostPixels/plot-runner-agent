"""
Configuration Manager for NextDraw Plotter API
Handles loading, saving, and managing plotter configuration settings.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages plotter configuration settings"""

    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.config = {}
        self.default_config = self._get_default_config()
        self.load_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration settings"""
        return {
            "plotter_info": {
                "model": 8,  # NextDraw 8511 by default
                "nickname": "",
                "firmware_version": "",
                "software_version": "",
                "port": None,
                "port_config": 0
            },
            "plotter_settings": {
                # Speed settings
                "speed_pendown": 25,
                "speed_penup": 75,
                "accel": 75,

                # Pen position settings
                "pen_pos_down": 40,
                "pen_pos_up": 60,
                "pen_rate_lower": 50,
                "pen_rate_raise": 50,

                # Handling mode (1=Technical, 2=Handwriting, 3=Sketching, 4=Constant)
                "handling": 1,

                # Homing and model settings
                "homing": True,
                "model": 8,
                "penlift": 1,

                # Plot settings
                "auto_rotate": True,
                "reordering": 0,
                "random_start": False,
                "hiding": False,
                "report_time": True
            },
            "api_settings": {
                "host": "0.0.0.0",
                "port": 5000,
                "debug": False,
                "cors_enabled": True,
                "max_job_queue": 100,
                "job_timeout": 3600,  # 1 hour
                "log_level": "INFO"
            },
            "file_settings": {
                "upload_directory": "uploads",
                "output_directory": "output",
                "max_file_size": 10485760,  # 10MB
                "allowed_extensions": [".svg"],
                "auto_cleanup": True,
                "cleanup_age_days": 7
            },
            "safety_settings": {
                "max_plot_time": 7200,  # 2 hours
                "emergency_stop_enabled": True,
                "pen_height_limits": {
                    "min": 0,
                    "max": 100
                },
                "speed_limits": {
                    "min_pendown": 1,
                    "max_pendown": 100,
                    "min_penup": 1,
                    "max_penup": 100
                }
            },
            "notification_settings": {
                "webhook_enabled": False,
                "webhook_url": "",
                "email_enabled": False,
                "email_settings": {
                    "smtp_server": "",
                    "smtp_port": 587,
                    "username": "",
                    "password": "",
                    "recipient": ""
                }
            },
            "version": "1.0.0",
            "last_updated": datetime.now().isoformat()
        }

    def load_config(self):
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
                logger.info(f"Configuration loaded from {self.config_file}")

                # Merge with defaults to ensure all keys exist
                self.config = self._merge_configs(self.default_config, self.config)
            else:
                logger.info("Configuration file not found, using defaults")
                self.config = self.default_config.copy()
                self.save_config()

        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            logger.info("Using default configuration")
            self.config = self.default_config.copy()

    def save_config(self):
        """Save current configuration to file"""
        try:
            self.config['last_updated'] = datetime.now().isoformat()

            # Create backup of existing config
            if os.path.exists(self.config_file):
                backup_file = f"{self.config_file}.backup"
                os.rename(self.config_file, backup_file)

            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

            logger.info(f"Configuration saved to {self.config_file}")

        except Exception as e:
            logger.error(f"Error saving configuration: {str(e)}")
            # Restore backup if save failed
            backup_file = f"{self.config_file}.backup"
            if os.path.exists(backup_file):
                os.rename(backup_file, self.config_file)
            raise

    def _merge_configs(self, default: Dict, user: Dict) -> Dict:
        """Recursively merge user config with default config"""
        result = default.copy()

        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    def get_current_config(self) -> Dict[str, Any]:
        """Get current configuration"""
        return self.config.copy()

    def get_plotter_settings(self) -> Dict[str, Any]:
        """Get plotter-specific settings"""
        return self.config.get('plotter_settings', {}).copy()

    def update_config(self, updates: Dict[str, Any], save: bool = True):
        """Update configuration with new values"""
        try:
            # Validate updates before applying
            validated_updates = self._validate_config_updates(updates)

            # Apply updates
            self.config = self._merge_configs(self.config, validated_updates)

            if save:
                self.save_config()

            logger.info("Configuration updated successfully")

        except Exception as e:
            logger.error(f"Error updating configuration: {str(e)}")
            raise

    def update_plotter_settings(self, settings: Dict[str, Any], save: bool = True):
        """Update plotter-specific settings"""
        try:
            validated_settings = self._validate_plotter_settings(settings)

            if 'plotter_settings' not in self.config:
                self.config['plotter_settings'] = {}

            self.config['plotter_settings'].update(validated_settings)

            if save:
                self.save_config()

            logger.info("Plotter settings updated successfully")

        except Exception as e:
            logger.error(f"Error updating plotter settings: {str(e)}")
            raise

    def update_plotter_info(self, info: Dict[str, Any], save: bool = True):
        """Update plotter information"""
        try:
            if 'plotter_info' not in self.config:
                self.config['plotter_info'] = {}

            self.config['plotter_info'].update(info)

            if save:
                self.save_config()

            logger.debug("Plotter info updated")

        except Exception as e:
            logger.error(f"Error updating plotter info: {str(e)}")
            raise

    def _validate_config_updates(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Validate configuration updates"""
        validated = {}

        for key, value in updates.items():
            if key == 'plotter_settings':
                validated[key] = self._validate_plotter_settings(value)
            elif key == 'plotter_info':
                validated[key] = self._validate_plotter_info(value)
            elif key == 'api_settings':
                validated[key] = self._validate_api_settings(value)
            elif key == 'safety_settings':
                validated[key] = self._validate_safety_settings(value)
            else:
                validated[key] = value

        return validated

    def _validate_plotter_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Validate plotter settings"""
        validated = {}
        safety = self.config.get('safety_settings', {})

        for key, value in settings.items():
            if key in ['speed_pendown', 'speed_penup']:
                # Validate speed settings
                min_val = safety.get('speed_limits', {}).get(f'min_{key.split("_")[1]}', 1)
                max_val = safety.get('speed_limits', {}).get(f'max_{key.split("_")[1]}', 100)
                validated[key] = max(min_val, min(max_val, int(value)))

            elif key in ['pen_pos_down', 'pen_pos_up']:
                # Validate pen height settings
                pen_limits = safety.get('pen_height_limits', {})
                min_val = pen_limits.get('min', 0)
                max_val = pen_limits.get('max', 100)
                validated[key] = max(min_val, min(max_val, int(value)))

            elif key in ['pen_rate_lower', 'pen_rate_raise']:
                # Validate pen rates (1-100)
                validated[key] = max(1, min(100, int(value)))

            elif key == 'accel':
                # Validate acceleration (1-100)
                validated[key] = max(1, min(100, int(value)))

            elif key == 'handling':
                # Validate handling mode (1-4)
                validated[key] = max(1, min(4, int(value)))

            elif key == 'model':
                # Validate model selection (1-10)
                validated[key] = max(1, min(10, int(value)))

            elif key == 'penlift':
                # Validate penlift setting (1-3)
                validated[key] = max(1, min(3, int(value)))

            elif key == 'reordering':
                # Validate reordering (0-4)
                validated[key] = max(0, min(4, int(value)))

            elif key in ['homing', 'auto_rotate', 'random_start', 'hiding', 'report_time']:
                # Boolean settings
                validated[key] = bool(value)

            elif key == 'port':
                # Port can be string or None
                validated[key] = str(value) if value is not None else None

            elif key == 'port_config':
                # Port config (0 or 1)
                validated[key] = 1 if value else 0

            else:
                validated[key] = value

        return validated

    def _validate_plotter_info(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """Validate plotter info"""
        validated = {}

        for key, value in info.items():
            if key in ['nickname', 'firmware_version', 'software_version']:
                validated[key] = str(value)
            elif key == 'model':
                validated[key] = max(1, min(10, int(value)))
            elif key == 'port':
                validated[key] = str(value) if value is not None else None
            elif key == 'port_config':
                validated[key] = 1 if value else 0
            else:
                validated[key] = value

        return validated

    def _validate_api_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Validate API settings"""
        validated = {}

        for key, value in settings.items():
            if key == 'port':
                validated[key] = max(1, min(65535, int(value)))
            elif key in ['debug', 'cors_enabled']:
                validated[key] = bool(value)
            elif key in ['max_job_queue', 'job_timeout']:
                validated[key] = max(1, int(value))
            elif key == 'log_level':
                valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
                validated[key] = value if value in valid_levels else 'INFO'
            else:
                validated[key] = value

        return validated

    def _validate_safety_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Validate safety settings"""
        validated = {}

        for key, value in settings.items():
            if key == 'max_plot_time':
                validated[key] = max(60, int(value))  # Minimum 1 minute
            elif key == 'emergency_stop_enabled':
                validated[key] = bool(value)
            elif key in ['pen_height_limits', 'speed_limits']:
                validated[key] = value if isinstance(value, dict) else {}
            else:
                validated[key] = value

        return validated

    def reset_to_defaults(self, save: bool = True):
        """Reset configuration to default values"""
        try:
            self.config = self.default_config.copy()

            if save:
                self.save_config()

            logger.info("Configuration reset to defaults")

        except Exception as e:
            logger.error(f"Error resetting configuration: {str(e)}")
            raise

    def export_config(self, file_path: str):
        """Export current configuration to a file"""
        try:
            with open(file_path, 'w') as f:
                json.dump(self.config, f, indent=2)

            logger.info(f"Configuration exported to {file_path}")

        except Exception as e:
            logger.error(f"Error exporting configuration: {str(e)}")
            raise

    def import_config(self, file_path: str, save: bool = True):
        """Import configuration from a file"""
        try:
            with open(file_path, 'r') as f:
                imported_config = json.load(f)

            # Validate imported config
            validated_config = self._validate_config_updates(imported_config)

            # Merge with current config
            self.config = self._merge_configs(self.config, validated_config)

            if save:
                self.save_config()

            logger.info(f"Configuration imported from {file_path}")

        except Exception as e:
            logger.error(f"Error importing configuration: {str(e)}")
            raise

    def get_config_schema(self) -> Dict[str, Any]:
        """Get configuration schema for validation/documentation"""
        return {
            "plotter_settings": {
                "speed_pendown": {"type": "integer", "min": 1, "max": 100, "description": "Pen-down speed percentage"},
                "speed_penup": {"type": "integer", "min": 1, "max": 100, "description": "Pen-up speed percentage"},
                "accel": {"type": "integer", "min": 1, "max": 100, "description": "Acceleration percentage"},
                "pen_pos_down": {"type": "integer", "min": 0, "max": 100, "description": "Pen down position percentage"},
                "pen_pos_up": {"type": "integer", "min": 0, "max": 100, "description": "Pen up position percentage"},
                "pen_rate_lower": {"type": "integer", "min": 1, "max": 100, "description": "Pen lowering speed"},
                "pen_rate_raise": {"type": "integer", "min": 1, "max": 100, "description": "Pen raising speed"},
                "handling": {"type": "integer", "min": 1, "max": 4, "description": "Handling mode (1=Technical, 2=Handwriting, 3=Sketching, 4=Constant)"},
                "model": {"type": "integer", "min": 1, "max": 10, "description": "Plotter model number"},
                "homing": {"type": "boolean", "description": "Enable automatic homing"},
                "auto_rotate": {"type": "boolean", "description": "Enable auto-rotation for landscape plots"},
                "reordering": {"type": "integer", "min": 0, "max": 4, "description": "Path reordering level"},
                "random_start": {"type": "boolean", "description": "Randomize start positions of closed paths"},
                "hiding": {"type": "boolean", "description": "Enable hidden-line removal"},
                "report_time": {"type": "boolean", "description": "Report time and distance after plotting"}
            }
        }
