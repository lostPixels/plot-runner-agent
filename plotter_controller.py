import logging
import os
import threading
import time
import json
from datetime import datetime
from nextdraw import NextDraw

# Configure logging
logging.basicConfig(level=logging.INFO)
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
        self.progress_callback = None  # Progress update callback

        # Store pause/resume data
        self.pause_data = None  # Stores the output SVG with progress data

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
                test_nd = NextDraw()

                # Test connection in interactive mode
                test_nd.interactive()
                if test_nd.connect():
                    self.status = "IDLE"
                    logger.info("NextDraw plotter connected successfully")

                    # Get plotter info
                    self._get_plotter_info(test_nd)

                    test_nd.disconnect()
                else:
                    self.status = "CONNECTION_ERROR"
                    raise Exception("Failed to connect to NextDraw plotter")

        except Exception as e:
            self.status = "ERROR"
            self.last_error = str(e)
            logger.error(f"Failed to initialize plotter: {str(e)}")
            raise

    def _apply_config(self, nextdraw_instance, config):
        """Apply configuration to NextDraw instance"""
        if not nextdraw_instance or not isinstance(config, dict):
            return

        # Handle both new JSON format and old format
        if 'name' in config and 'plotter_settings' not in config:
            # New JSON format - direct parameters at root level
            for key, value in config.items():
                if key != 'name' and hasattr(nextdraw_instance.options, key):
                    setattr(nextdraw_instance.options, key, value)
                    logger.debug(f"Set {key} = {value}")
        else:
            # Old format with plotter_settings
            for key, value in config.get('plotter_settings', {}).items():
                if hasattr(nextdraw_instance.options, key):
                    setattr(nextdraw_instance.options, key, value)
                    logger.debug(f"Set {key} = {value}")

    def _get_plotter_info(self, nextdraw_instance=None):
        """Get plotter information"""
        try:
            nd = nextdraw_instance or self.nextdraw
            if nd and hasattr(nd, 'fw_version_string'):
                info = {
                    "firmware_version": getattr(nd, 'fw_version_string', 'Unknown'),
                    "software_version": getattr(nd, 'version_string', 'Unknown'),
                    "nickname": getattr(nd, 'nickname', ''),
                    "last_updated": datetime.now().isoformat()
                }
                return info
        except Exception as e:
            logger.warning(f"Could not get plotter info: {str(e)}")
        return None

    def draw_bullseye(self):
        """Draw a bullseye pattern on the plotter"""
        print("DRAW BULLSEYE")
        # self.nextdraw.plot_setup("bullseye-helper/bullseye.svg");
        # self.nextdraw.plot_run(True)


        with open("bullseye-helper/bullseyeconfig.json", "r") as file:
            config = json.load(file)
        opts = {
            "name": "Bullseye",
            "config_overrides": config,
            "svg_file": "bullseye-helper/bullseye.svg",

        }
        return self.execute_job(opts)

    def _cleanup_state(self):
        """Clean up all state for next plot"""
        self.current_job = None
        self.pause_data = None
        self.nextdraw = None
        self.plot_thread = None
        self.is_plotting = False
        self.is_paused = False
        logger.info("State cleaned up for next plot")

    def execute_job(self, job_data):
        """Execute a plot job"""
        try:
            with self.lock:
                if self.is_plotting:
                    return {"success": False, "error": "Plotter is already busy"}

                # Clean up any previous state
                self._cleanup_state()

                self.current_job = job_data
                self.is_plotting = True
                self.is_paused = False
                self.status = "PLOTTING"

            logger.info(f"Request to begin plot job: {job_data.get('name', 'Unnamed job')}")
            start_time = time.time()

            # Create fresh NextDraw instance for this job
            self.nextdraw = NextDraw()

            # Setup plot
            svg_content = job_data.get('svg_content')
            svg_file = job_data.get('svg_file')
            svg_origin = svg_content or svg_file

            if svg_origin is None:
                with self.lock:
                    self._cleanup_state()
                    self.status = "ERROR"
                return {"success": False, "error": "No valid SVG content or file provided"}

            progress_in_mm = job_data.get('progress_in_mm') or 0
            progress_in_mm /= 100

            print("job_data",job_data.get('progress_in_mm'), progress_in_mm)

            job_config = job_data.get('config_overrides', {})
            if isinstance(job_config, str):
                try:
                    job_config = json.loads(job_config)
                except:
                    job_config = {}

            has_progress_assigned = progress_in_mm is not None and progress_in_mm != 0

            # Handle layer selection
            layer = job_data.get('layer_name', 'all')

            if has_progress_assigned:
                try:
                    nd_plob_maker = NextDraw()
                    output_plob = None

                    if layer != "all":
                        print('Create PLOB with Layer Only.', layer)
                        nd_plob_maker.plot_setup(svg_origin)
                        if isinstance(job_config, dict):
                            for key, value in job_config.items():
                                if isinstance(value, dict):
                                    for sub_key, sub_value in value.items():
                                        if sub_key != 'name' and hasattr(nd_plob_maker.options, sub_key):
                                            setattr(nd_plob_maker.options, sub_key, sub_value)
                                elif hasattr(nd_plob_maker.options, key):
                                    setattr(nd_plob_maker.options, key, value)

                        nd_plob_maker.options.digest = 2
                        nd_plob_maker.options.mode = "layers"
                        nd_plob_maker.options.layer = int(layer)
                        nd_plob_maker.update()
                        output_plob = nd_plob_maker.plot_run(True)
                        nd_plob_maker.plot_setup(output_plob)
                    else:
                        nd_plob_maker.plot_setup(svg_origin)

                    nd_plob_maker.options.mode = "utility"
                    nd_plob_maker.options.utility_cmd = "res_adj_mm"
                    nd_plob_maker.options.dist = float(progress_in_mm)
                    nd_plob_maker.update();
                    svg_origin = nd_plob_maker.plot_run(True) #Update SVG origin with drawing that has layer and resume position set.

                    self.nextdraw.plot_setup(svg_origin)
                    self.nextdraw.options.mode = "res_plot"

                    print(f"Begin plotting with progress assignment. {progress_in_mm}")

                except Exception as e:
                    print(f"Error creating plot with progress assignment: {e}")
                    logger.error(f"Error creating plot with progress assignment: {e}")

            else:
                self.nextdraw.plot_setup(svg_origin)

                if layer != "all":
                    self.nextdraw.options.mode = "layers"
                    self.nextdraw.options.layer = int(layer)

            if isinstance(job_config, dict):
                for key, value in job_config.items():
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if sub_key != 'name' and hasattr(self.nextdraw.options, sub_key):
                                setattr(self.nextdraw.options, sub_key, sub_value)
                    elif hasattr(self.nextdraw.options, key):
                        setattr(self.nextdraw.options, key, value)

            self.nextdraw.update();

            # Execute plot and capture output
            try:
                print("!!!!!!!!!!EXECUTING PLOT with mode: ",self.nextdraw.options.mode)
                logger.info(f"Executing plot with mode: {self.nextdraw.options.mode}, Layer: {layer}")
                result = self.nextdraw.plot_run(True)  # Always return output SVG for pause/resume

                # Check if we were paused
                with self.lock:
                    if self.is_paused:
                        # Store pause data for resume
                        self.pause_data = result
                        logger.info("Job paused, pause data stored")
                        return {"success": False, "message": "Job was paused and can be resumed"}

                    if not self.is_plotting:
                        # Job was stopped
                        self._cleanup_state()
                        self.status = "IDLE"
                        return {"success": False, "error": "Job was cancelled"}

                # Job completed successfully
                plot_time = time.time() - start_time

                # Update statistics
                self.stats["total_jobs"] += 1
                self.stats["successful_jobs"] += 1
                self.stats["total_plot_time"] += plot_time
                self.stats["last_job_time"] = plot_time

                logger.info(f"Plot job completed in {plot_time:.2f} seconds")

                # Clean up state for next job
                with self.lock:
                    self._cleanup_state()
                    self.status = "IDLE"

                return {
                    "success": True,
                    "plot_time": plot_time,
                    "output_svg": result if isinstance(result, str) else None,
                    "stats": dict(self.stats)
                }

            except Exception as e:
                logger.error(f"Plot execution failed: {str(e)}")
                with self.lock:
                    self._cleanup_state()
                    self.status = "ERROR"
                    self.last_error = str(e)
                self.stats["failed_jobs"] += 1
                return {"success": False, "error": str(e)}

        except Exception as e:
            logger.error(f"Job execution failed: {str(e)}")
            with self.lock:
                self._cleanup_state()
                self.status = "ERROR"
                self.last_error = str(e)
            self.stats["failed_jobs"] += 1
            return {"success": False, "error": str(e)}

    def pause(self):
        """Pause current plotting job"""
        try:
            with self.lock:
                if not self.is_plotting or self.is_paused:
                    return False

                # Request pause
                if self.nextdraw:
                    self.nextdraw.transmit_pause_request()

                self.is_paused = True
                self.status = "PAUSED"
                logger.info("Plot job pause requested")
                return True

        except Exception as e:
            logger.error(f"Failed to pause: {str(e)}")
            return False

    def resume(self):
        """Resume paused plotting job"""
        try:
            with self.lock:
                if not self.is_paused or not self.pause_data:
                    logger.warning("No paused job to resume")
                    return False

                # Reset state for resume
                self.is_paused = False
                self.is_plotting = True
                self.status = "PLOTTING"

            logger.info("Resuming paused plot job")

            # Start resume in a separate thread
            def resume_thread():
                try:
                    # Create new NextDraw instance for resume
                    self.nextdraw = NextDraw()

                    # Setup with pause data
                    self.nextdraw.plot_setup(self.pause_data)
                    self.nextdraw.options.mode = "res_plot"

                    # Re-apply job configuration if available
                    if self.current_job:
                        job_config = self.current_job.get('config_overrides', {})
                        if isinstance(job_config, str):
                            try:
                                job_config = json.loads(job_config)
                            except:
                                pass

                        if isinstance(job_config, dict):
                            for key, value in job_config.items():
                                if isinstance(value, dict):
                                    for sub_key, sub_value in value.items():
                                        if sub_key != 'name' and hasattr(self.nextdraw.options, sub_key):
                                            setattr(self.nextdraw.options, sub_key, sub_value)
                                elif hasattr(self.nextdraw.options, key):
                                    setattr(self.nextdraw.options, key, value)

                    # Execute resumed plot
                    result = self.nextdraw.plot_run(True)

                    # Check final state
                    with self.lock:
                        if self.is_paused:
                            # Paused again during resume
                            self.pause_data = result
                            logger.info("Job paused again during resume")
                        else:
                            # Resume completed successfully
                            logger.info("Resume completed successfully")
                            self._cleanup_state()
                            self.status = "IDLE"

                except Exception as e:
                    logger.error(f"Error in resume thread: {str(e)}")
                    with self.lock:
                        self._cleanup_state()
                        self.status = "ERROR"
                        self.last_error = str(e)

            self.plot_thread = threading.Thread(target=resume_thread)
            self.plot_thread.daemon = True
            self.plot_thread.start()

            return True

        except Exception as e:
            logger.error(f"Failed to resume: {str(e)}")
            with self.lock:
                self.status = "ERROR"
                self.last_error = str(e)
            return False

    def stop(self):
        """Stop current plotting job"""
        try:
            with self.lock:
                if not self.is_plotting:
                    return False

                logger.info("Stopping plot job...")

                # Send pause request to stop gracefully
                if self.nextdraw:
                    try:
                        self.nextdraw.transmit_pause_request()
                    except:
                        pass

                # Clean up state
                self._cleanup_state()
                self.status = "IDLE"

                logger.info("Plot job stopped")
                return True

        except Exception as e:
            logger.error(f"Failed to stop: {str(e)}")
            return False

    def execute_utility(self, utility_cmd, options=None):

        if utility_cmd == "bullseye":
            return self.draw_bullseye()


        """Execute a utility command"""
        try:
            with self.lock:
                if self.is_plotting:
                    return {"success": False, "error": "Cannot execute utility while plotting"}

                self.status = "BUSY"

            logger.info(f"Executing utility command: {utility_cmd}")

            if utility_cmd == "home":
                nd = NextDraw()
                nd.plot_setup()
                nd.options.mode = "find_home"
                nd.plot_run()
            elif utility_cmd == "limit":
                print("TODO")
            elif utility_cmd =="disable_motors":
                nd = NextDraw()
                nd.plot_setup()
                nd.options.mode = "utility"
                nd.options.utility_cmd = "disable_xy"
                nd.plot_run()


            with self.lock:
                self.status = "IDLE"

            logger.info(f"Utility command '{utility_cmd}' completed")
            return {"success": True}

        except Exception as e:
            logger.error(f"Utility command failed: {str(e)}")
            with self.lock:
                self.status = "ERROR"
                self.last_error = str(e)
            return {"success": False, "error": str(e)}

    def _apply_config_to_instance(self, nd_instance, config):
        """Apply configuration to a NextDraw instance"""
        if not nd_instance or not config:
            return

        if isinstance(config, str):
            try:
                config = json.loads(config)
            except:
                logger.warning("Could not parse config as JSON")
                return

        if isinstance(config, dict):
            for key, value in config.items():
                if hasattr(nd_instance.options, key):
                    setattr(nd_instance.options, key, value)
                    logger.debug(f"Applied config: {key} = {value}")

    def get_status(self):
        """Get current plotter status"""
        with self.lock:
            return {
                "status": self.status,
                "is_plotting": self.is_plotting,
                "is_paused": self.is_paused,
                "current_job": self.current_job.get("name", "Unknown") if self.current_job else None,
                "last_error": self.last_error,
                "stats": dict(self.stats)
            }

    def is_idle(self):
        """Check if plotter is idle and ready for new job"""
        with self.lock:
            return self.status == "IDLE" and not self.is_plotting

    def test_connection(self):
        """Test connection to the plotter"""
        try:
            test_nd = NextDraw()
            test_nd.interactive()
            if test_nd.connect():
                test_nd.disconnect()
                return {"connected": True, "message": "Connection successful"}
            else:
                return {"connected": False, "message": "Failed to connect to plotter"}
        except Exception as e:
            return {"connected": False, "message": str(e)}

    def plot_file(self, svg_path, config_overrides=None, job_name=None, layer_name=None, progress_in_mm=0):
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
                'layer_name': layer_name,
                'progress_in_mm': progress_in_mm
            }

            # Execute the job
            result = self.execute_job(job_data)
            return result

        except Exception as e:
            logger.error(f"Error in plot_file: {str(e)}")
            return {"success": False, "error": str(e)}
