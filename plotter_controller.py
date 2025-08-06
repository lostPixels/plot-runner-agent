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
import json

logger = logging.getLogger(__name__)

class PlotterController:
    """Controls NextDraw plotter operations"""

    def __init__(self):
        self.nextdraw = None
        self.status = "DISCONNECTED"
        self.current_job = None
        self.is_plotting = False
        self.is_paused = False
        self.last_error = None
        self.lock = threading.Lock()
        self.plot_thread = None
        self.progress_plob = None  # Placeholder for plot progress data
        self.output_svg = None     # Storage for the most recent output SVG
        self.progress_callback = None  # Progress update callback

        # Status tracking
        self.stats = {
            "total_jobs": 0,
            "successful_jobs": 0,
            "failed_jobs": 0,
            "total_plot_time": 0,
            "last_job_time": None
        }

    def set_progress_callback(self, callback):
        """Set callback function for progress updates"""
        self.progress_callback = callback

    def initialize(self):
        """Initialize connection to NextDraw plotter"""
        try:
            with self.lock:
                logger.info("Initializing NextDraw plotter...")
                self.nextdraw = NextDraw()

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

        # Ensure config is a dictionary
        if not isinstance(config, dict):
            logger.warning(f"Config is not a dictionary: {type(config)}")
            return

        # If config is in the new JSON format (has direct parameters at root level)
        if 'name' in config and 'plotter_settings' not in config:
            # Apply new JSON format directly
            for key, value in config.items():
                if key != 'name' and hasattr(self.nextdraw.options, key):
                    setattr(self.nextdraw.options, key, value)
                    logger.debug(f"Set {key} = {value}")
        else:
            # Apply old format (with plotter_settings)
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

        except Exception as e:
            logger.warning(f"Could not get plotter info: {str(e)}")

    def draw_bullseye(self):
        """Draw a bullseye pattern on the plotter"""
        with open("bullseye-helper/bullseyeconfig.json", "r") as file:
            config = json.load(file)
        opts = {
            "config_overrides": config,
            "svg_file": "bullseye-helper/bullseye.svg"
        }
        self.execute_job(opts)

    def execute_job(self, job_data):
        """Execute a plot job directly without using queue"""
        try:
            with self.lock:
                if self.is_plotting:
                    return {"success": False, "error": "Plotter is already busy"}

                self.current_job = job_data
                self.is_plotting = True
                self.is_paused = False
                self.status = "PLOTTING"

            logger.info(f"Starting plot job: {job_data.get('name', 'Unnamed job')}")
            start_time = time.time()

            # Initialize NextDraw for plotting
            self.nextdraw = NextDraw()


            # Apply job-specific config overrides
            job_config = job_data.get('config_overrides', {})


            # Setup plot
            svg_content = job_data.get('svg_content')
            svg_file = job_data.get('svg_file')

            if svg_content:
                self.nextdraw.plot_setup(svg_content)
            elif svg_file and os.path.exists(svg_file):
                self.nextdraw.plot_setup(svg_file)
            else:
                return {"success": False, "error": "No valid SVG content or file provided"}

            # Check if job_config is already a dict, if not, try to parse it from JSON
            if not isinstance(job_config, dict) and isinstance(job_config, str):
                job_config = json.loads(job_config)

            if isinstance(job_config, dict):
                # Iterate through the JSON configuration
                for key, value in job_config.items():
                    if isinstance(value, dict):
                        # If value is a nested dictionary, process its items
                        for sub_key, sub_value in value.items():
                            if sub_key != 'name':
                                #print(f"Setting option {sub_key} = {sub_value}")
                                setattr(self.nextdraw.options, sub_key, sub_value)
                    else:
                        # Handle direct key-value pairs
                        #print(f"Setting option {key} = {value}")
                        setattr(self.nextdraw.options, key, value)

            layer = job_data.get('layer_name', 'all')
            if layer != "all":
                    self.nextdraw.options.mode = "layers"
                    self.nextdraw.options.layer = int(layer)

            self.nextdraw.update()

            print("self.nextdraw.options",self.nextdraw.options)

            # Handle start_mm parameter for resume plotting
            start_mm = job_data.get('start_mm')
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

                # Store the output SVG for possible pause/resume operations
                if isinstance(result, str):
                    self.output_svg = result

                # Check if job was cancelled or paused
                if not self.is_plotting:
                    # If we're paused, the job data should already contain the output_svg
                    # from the pause method, so we return a different message
                    if self.is_paused:
                        return {"success": False, "message": "Job was paused and can be resumed"}
                    return {"success": False, "error": "Job was cancelled"}

                plot_time = time.time() - start_time

                # Update statistics
                self.stats["total_jobs"] += 1
                self.stats["successful_jobs"] += 1
                self.stats["total_plot_time"] += plot_time
                self.stats["last_job_time"] = plot_time

                # Update current_job with output SVG data
                if isinstance(result, str) and self.current_job:
                    self.current_job['output_svg'] = result

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
                # Only clear current_job if not paused - we need it for resume
                if not self.is_paused:
                    self.current_job = None
                    # Also clear output_svg when job completes normally
                    self.output_svg = None
                self.is_plotting = False
                # Don't change is_paused here - we need that state for resuming
                # Only set status to IDLE if not paused
                if not self.is_paused:
                    self.status = "IDLE"

    def pause(self):
        """Pause current plotting job"""
        try:
            with self.lock:
                if not self.is_plotting or self.is_paused:
                    return False

                # Call NextDraw pause function and capture the current SVG state
                self.is_paused = True
                self.status = "PAUSED"

                try:
                    # Request pause without expecting output
                    if self.nextdraw:
                        self.nextdraw.transmit_pause_request()

                    # Save the progress plot object if available
                    if self.nextdraw and hasattr(self.nextdraw, 'get_progress_plob'):
                        self.progress_plob = self.nextdraw.get_progress_plob()

                    # Store the previously saved output SVG in the current job for resume
                    if self.output_svg and self.current_job is not None:
                        self.current_job['output_svg'] = self.output_svg
                        logger.info("Stored SVG state for resume")
                except Exception as e:
                    logger.warning(f"Could not capture SVG state during pause: {str(e)}")

                logger.info("Plot job paused")
                return True

        except Exception as e:
            logger.error(f"Failed to pause: {str(e)}")
            return False

    def resume(self):
        """Resume paused plotting job"""
        try:
            with self.lock:
                if not self.is_paused or not self.current_job:
                    logger.warning("No paused job to resume")
                    return False

                logger.info("Resuming paused plot job")

                # Initialize NextDraw for resuming plot
                if not self.nextdraw:
                    self.nextdraw = NextDraw()

                # Prepare NextDraw for resuming
                if not self.nextdraw:
                    logger.error("No NextDraw instance available for resuming")
                    return False

                # First try to use the progress plot object
                if self.progress_plob:
                    logger.info("Resuming with progress plot object")
                    self.nextdraw.plot_setup(self.progress_plob)
                # Next try the saved output SVG in the current job
                elif self.current_job and 'output_svg' in self.current_job:
                    logger.info("Resuming with saved output SVG from job")
                    self.nextdraw.plot_setup(self.current_job.get('output_svg'))
                # Finally try the class-level stored output SVG
                elif self.output_svg:
                    logger.info("Resuming with stored output SVG")
                    self.nextdraw.plot_setup(self.output_svg)
                else:
                    logger.error("No resume data available")
                    return False

                self.nextdraw.options.report_time = True
                self.nextdraw.options.preview = False
                self.nextdraw.options.mode = "res_plot"

                # Apply any job-specific config overrides
                job_config = self.current_job.get('config_overrides', {})
                if isinstance(job_config, dict):
                    for key, value in job_config.items():
                        if hasattr(self.nextdraw.options, key):
                            setattr(self.nextdraw.options, key, value)

                # Update NextDraw with new configuration
                if hasattr(self.nextdraw, 'update'):
                    self.nextdraw.update()

                # Start plotting in a separate thread to not block the API
                def resume_thread():
                    try:
                        # Execute the resumed plot
                        output_svg = None
                        if self.nextdraw:
                            output_svg = self.nextdraw.plot_run(True)

                        # Update job data with new output SVG if available
                        if output_svg and self.current_job:
                            self.current_job['output_svg'] = output_svg
                            # Also update the class-level stored SVG
                            self.output_svg = output_svg

                        logger.info("Plot job completed successfully")

                        with self.lock:
                            self.is_plotting = False
                            self.is_paused = False
                            self.status = "IDLE"

                    except Exception as e:
                        logger.error(f"Error in resume thread: {str(e)}")
                        with self.lock:
                            self.is_plotting = False
                            self.is_paused = False
                            self.status = "ERROR"
                            self.last_error = str(e)

                # Start the resume thread
                self.plot_thread = threading.Thread(target=resume_thread)
                self.plot_thread.daemon = True
                self.plot_thread.start()

                # Update controller state
                self.is_paused = False
                self.is_plotting = True
                self.status = "PLOTTING"

                logger.info("Plot job resumed")
                return True

        except Exception as e:
            logger.error(f"Failed to resume: {str(e)}")
            self.status = "ERROR"
            self.last_error = str(e)
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

            nd.plot_setup()
            nd.options.mode = "utility"

            # Execute specific utility commands
            if command == "home":
                nd.options.model = 10
                nd.update()
                nd.options.mode = "find_home"
                result = nd.plot_run()
                return {"success": True, "message": "Moved to home position"}

            elif command == "bullseye":
                self.draw_bullseye()
                return {"success": True, "message": "Draw Bullseye"}

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
            elif command == "disable_motors":
                nd.options.mode = "disable_xy"
                result = nd.plot_run()
                return {"success": True, "message": "Motors disabled"}

            elif command == "go_to_limit":
                # Go to plotter limit
                nd.interactive()                # Enter interactive context
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
        # Ensure config is a dictionary
        if not isinstance(config, dict):
            logger.warning(f"Config is not a dictionary: {type(config)}")
            return

        # If config is in the new JSON format (has direct parameters at root level)
        if 'name' in config and 'plotter_settings' not in config:
            # Apply new JSON format directly
            for key, value in config.items():
                if key != 'name':
                    setattr(nd_instance.options, key, value)
        else:
            # Apply old format (with plotter_settings)
            for key, value in config.get('plotter_settings', {}).items():
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
        return self.status == "IDLE" or self.status == "DISCONNECTED" and not self.is_plotting

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

    def plot_file(self, svg_path, config_overrides=None, job_name=None, layer_name=None):
        """Plot an SVG file with optional layer filtering"""
        try:
            # Check if file exists
            if not os.path.exists(svg_path):
                return {"success": False, "error": f"SVG file not found: {svg_path}"}

            # Prepare job data
            job_data = {
                'svg_file': svg_path,
                'name': job_name or f'Plot_{int(time.time())}',
                'config_overrides': config_overrides or {},
                'layer_name': layer_name
            }

            # Execute the job
            result = self.execute_job(job_data)
            return result

        except Exception as e:
            logger.error(f"Error in plot_file: {str(e)}")
            return {"success": False, "error": str(e)}
