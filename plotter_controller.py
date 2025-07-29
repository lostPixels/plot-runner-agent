"""
NextDraw Plotter Controller
Handles direct communication with NextDraw plotters using the NextDraw Python API.
"""

import os
import time
import threading
from datetime import datetime
import logging
from nextdraw import NextDraw
# try:
#     from nextdraw import NextDraw
# except ImportError:
#     # For development/testing when NextDraw library is not available
#     class NextDrawOptions:
#         def __init__(self):
#             self.mode = None
#             self.utility_cmd = None
#             self.dist = 0.0
#     class NextDraw:
#         def __init__(self):
#             self.options = NextDrawOptions()
#         def plot_setup(self, *args, **kwargs):
#             pass
#         def plot_run(self, *args, **kwargs):
#             return True
#         def interactive(self):
#             pass
#         def connect(self):
#             return True
#         def disconnect(self):
#             pass

logger = logging.getLogger(__name__)

class PlotterController:
    """Controls NextDraw plotter operations"""

    def __init__(self, config_manager, job_queue):
        self.config_manager = config_manager
        self.job_queue = job_queue
        self.nextdraw = None
        self.status = "DISCONNECTED"
        self.current_job = None
        self.is_plotting = False
        self.is_paused = False
        self.last_error = None
        self.lock = threading.Lock()
        self.plot_thread = None

        # Status tracking
        self.stats = {
            "total_jobs": 0,
            "successful_jobs": 0,
            "failed_jobs": 0,
            "total_plot_time": 0,
            "last_job_time": None
        }

    def initialize(self):
        """Initialize connection to NextDraw plotter"""
        try:
            with self.lock:
                logger.info("Initializing NextDraw plotter...")
                self.nextdraw = NextDraw()

                # Load configuration
                config = self.config_manager.get_current_config()
                self._apply_config(config)

                # Test connection in interactive mode
                self.nextdraw.interactive()
                if self.nextdraw.connect():
                    self.status = "IDLE"
                    logger.info("NextDraw plotter connected successfully")

                    # Get plotter info
                    self._get_plotter_info()

                    self.nextdraw.disconnect()
                else:
                    self.status = "CONNECTION_ERROR"
                    raise Exception("Failed to connect to NextDraw plotter")

        except Exception as e:
            self.status = "ERROR"
            self.last_error = str(e)
            logger.error(f"Failed to initialize plotter: {str(e)}")
            raise

    def _apply_config(self, config):
        """Apply configuration to NextDraw instance"""
        if not self.nextdraw:
            return

        # Apply general options
        for key, value in config.get('plotter_settings', {}).items():
            if hasattr(self.nextdraw.options, key):
                setattr(self.nextdraw.options, key, value)
                logger.debug(f"Set {key} = {value}")

    def _get_plotter_info(self):
        """Get plotter information and store in config"""
        try:
            if self.nextdraw and hasattr(self.nextdraw, 'fw_version_string'):
                info = {
                    "firmware_version": getattr(self.nextdraw, 'fw_version_string', 'Unknown'),
                    "software_version": getattr(self.nextdraw, 'version_string', 'Unknown'),
                    "nickname": getattr(self.nextdraw, 'nickname', ''),
                    "last_updated": datetime.now().isoformat()
                }
                self.config_manager.update_plotter_info(info)
        except Exception as e:
            logger.warning(f"Could not get plotter info: {str(e)}")

    def execute_job(self, job):
        """Execute a plot job"""
        try:
            with self.lock:
                if self.is_plotting:
                    return {"success": False, "error": "Plotter is already busy"}

                self.current_job = job
                self.is_plotting = True
                self.is_paused = False
                self.status = "PLOTTING"

            logger.info(f"Starting plot job: {job['name']}")
            start_time = time.time()

            # Initialize NextDraw for plotting
            self.nextdraw = NextDraw()

            # Apply base configuration
            config = self.config_manager.get_current_config()
            self._apply_config(config)

            # Apply job-specific config overrides
            job_config = job.get('config_overrides', {})
            for key, value in job_config.items():
                if hasattr(self.nextdraw.options, key):
                    setattr(self.nextdraw.options, key, value)
                    logger.debug(f"Job override: {key} = {value}")

            # Setup plot
            svg_content = job.get('svg_content')
            svg_file = job.get('svg_file')

            if svg_content:
                self.nextdraw.plot_setup(svg_content)
            elif svg_file and os.path.exists(svg_file):
                self.nextdraw.plot_setup(svg_file)
            else:
                return {"success": False, "error": "No valid SVG content or file provided"}

            # Handle start_mm parameter for resume plotting
            start_mm = job.get('start_mm')
            if start_mm is not None:
                try:
                    # First adjust the resume position
                    self.nextdraw.options.mode = "utility"
                    self.nextdraw.options.utility_cmd = "res_adj_mm"
                    self.nextdraw.options.dist = float(start_mm)

                    # Run the utility command to set resume position
                    output_svg = self.nextdraw.plot_run(True)

                    # Re-setup with the output SVG that now contains resume data
                    self.nextdraw.plot_setup(output_svg)

                    # Set mode to resume plot
                    self.nextdraw.options.mode = "res_plot"

                    logger.info(f"Set resume position to {start_mm} mm")

                except Exception as e:
                    logger.error(f"Failed to set start position: {str(e)}")
                    return {"success": False, "error": f"Failed to set start position: {str(e)}"}

            # Execute plot
            try:
                result = self.nextdraw.plot_run(True)  # Return output SVG

                # Check if job was cancelled or paused
                if not self.is_plotting:
                    return {"success": False, "error": "Job was cancelled"}

                plot_time = time.time() - start_time

                # Update statistics
                self.stats["total_jobs"] += 1
                self.stats["successful_jobs"] += 1
                self.stats["total_plot_time"] += plot_time
                self.stats["last_job_time"] = plot_time

                logger.info(f"Plot job completed in {plot_time:.2f} seconds")

                return {
                    "success": True,
                    "plot_time": plot_time,
                    "output_svg": result if isinstance(result, str) else None,
                    "stats": dict(self.stats)
                }

            except Exception as e:
                self.stats["failed_jobs"] += 1
                logger.error(f"Plot execution failed: {str(e)}")
                return {"success": False, "error": str(e)}

        except Exception as e:
            self.stats["failed_jobs"] += 1
            logger.error(f"Job execution failed: {str(e)}")
            return {"success": False, "error": str(e)}

        finally:
            with self.lock:
                self.current_job = None
                self.is_plotting = False
                self.is_paused = False
                self.status = "IDLE"

    def pause(self):
        """Pause current plotting job"""
        try:
            with self.lock:
                if not self.is_plotting or self.is_paused:
                    return False

                # NextDraw doesn't have direct pause - would need to implement
                # by stopping current job and saving state for resume
                self.is_paused = True
                self.status = "PAUSED"
                logger.info("Plot job paused")
                return True

        except Exception as e:
            logger.error(f"Failed to pause: {str(e)}")
            return False

    def resume(self):
        """Resume paused plotting job"""
        try:
            with self.lock:
                if not self.is_paused:
                    return False

                self.is_paused = False
                self.status = "PLOTTING"
                logger.info("Plot job resumed")
                return True

        except Exception as e:
            logger.error(f"Failed to resume: {str(e)}")
            return False

    def stop(self):
        """Stop current plotting job"""
        try:
            with self.lock:
                if not self.is_plotting:
                    return False

                self.is_plotting = False
                self.is_paused = False
                self.current_job = None
                self.status = "IDLE"

                # Disconnect from plotter
                if self.nextdraw:
                    try:
                        self.nextdraw.disconnect()
                    except:
                        pass

                logger.info("Plot job stopped")
                return True

        except Exception as e:
            logger.error(f"Failed to stop: {str(e)}")
            return False

    def execute_utility(self, command, params=None):
        """Execute utility commands"""
        try:
            if self.is_plotting:
                return {"error": "Cannot execute utility while plotting"}

            params = params or {}

            # Initialize for utility mode
            nd = NextDraw()
            config = self.config_manager.get_current_config()
            self._apply_config_to_instance(nd, config)

            nd.plot_setup()
            nd.options.mode = "utility"

            # Execute specific utility commands
            if command == "home":
                nd.options.model = 10
                nd.options.mode = "find_home"
                result = nd.plot_run()
                return {"success": True, "message": "Moved to home position"}

            elif command == "raise_pen":
                nd.options.utility_cmd = "raise_pen"
                result = nd.plot_run()
                return {"success": True, "message": "Pen raised"}

            elif command == "lower_pen":
                nd.options.utility_cmd = "lower_pen"
                result = nd.plot_run()
                return {"success": True, "message": "Pen lowered"}

            elif command == "toggle_pen":
                nd.options.utility_cmd = "toggle"
                result = nd.plot_run()
                return {"success": True, "message": "Pen toggled"}

            elif command == "move":
                direction = params.get('direction', 'x')
                distance = params.get('distance', 1.0)
                units = params.get('units', 'mm')

                if units == 'mm':
                    if direction.lower() == 'x':
                        nd.options.utility_cmd = "walk_mmx"
                    else:
                        nd.options.utility_cmd = "walk_mmy"
                else:  # inches
                    if direction.lower() == 'x':
                        nd.options.utility_cmd = "walk_x"
                    else:
                        nd.options.utility_cmd = "walk_y"

                nd.options.dist = distance
                result = nd.plot_run()
                return {"success": True, "message": f"Moved {distance} {units} in {direction}"}

            elif command == "get_info":
                nd.options.mode = "sysinfo"
                result = nd.plot_run()
                return {"success": True, "info": result}

            elif command == "go_to_limit":
                # Go to plotter limit
                nd.interactive()                # Enter interactive context
                nd.options.model = 5
                nd.options.homing = False
                nd.options.report_time = True
                nd.options.preview = False
                nd.options.penlift = 3
                nd.update()
                if not nd.connect():
                    return {"success": False, "message": "No connection"}
                nd.moveto(34, 22)
                nd.disconnect()
                return {"success": True, "message": "Moved to plotter limit (34, 22)"}

            else:
                return {"error": f"Unknown utility command: {command}"}

        except Exception as e:
            logger.error(f"Utility command failed: {str(e)}")
            return {"error": str(e)}

    def _apply_config_to_instance(self, nd_instance, config):
        """Apply configuration to a NextDraw instance"""
        for key, value in config.get('plotter_settings', {}).items():
            if hasattr(nd_instance.options, key):
                setattr(nd_instance.options, key, value)

    def get_status(self):
        """Get current plotter status"""
        return {
            "status": self.status,
            "is_plotting": self.is_plotting,
            "is_paused": self.is_paused,
            "current_job": self.current_job,
            "last_error": self.last_error,
            "stats": dict(self.stats),
            "connection_status": "connected" if self.status != "DISCONNECTED" else "disconnected"
        }

    def is_idle(self):
        """Check if plotter is idle and ready for new jobs"""
        return self.status == "IDLE" and not self.is_plotting and not self.is_paused

    def test_connection(self):
        """Test connection to plotter"""
        try:
            nd = NextDraw()
            nd.interactive()
            if nd.connect():
                nd.disconnect()
                return {"success": True, "message": "Connection test successful"}
            else:
                return {"success": False, "message": "Failed to connect"}
        except Exception as e:
            return {"success": False, "message": str(e)}
