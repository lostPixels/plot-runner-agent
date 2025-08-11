import serial
import serial.tools.list_ports
import pytz
import json
import logging
import time
import threading
from datetime import datetime
from typing import Optional, List, Tuple
from time_utils import calculate_end_time


logger = logging.getLogger(__name__)


class LilygoDisplay:
    """Singleton class for reliable communication with Lilygo AMOLED Display"""

    _instance = None
    _lock = threading.Lock()

    # Known ESP32 USB-to-UART bridge chips
    KNOWN_VID_PID_PAIRS: List[Tuple[str, str]] = [
        ('10C4', 'EA60'),  # Silicon Labs CP210x
        ('1A86', '7523'),  # CH340
        ('0403', '6001'),  # FTDI FT232R
        ('303A', '1001'),  # Espressif USB JTAG/serial debug unit - Lilygo
    ]

    # Connection parameters
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # seconds
    READ_TIMEOUT = 2.0  # seconds
    WRITE_TIMEOUT = 1.0  # seconds
    CONNECTION_CHECK_INTERVAL = 5.0  # seconds

    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the display connection (only once for singleton)"""
        if self._initialized:
            return

        self.port = None
        self.connected = False
        self.device_path = None
        self._last_connection_check = 0
        self._connection_lock = threading.Lock()
        self._initialized = True

        # Auto-connect on initialization
        self._ensure_connection()

    def find_port(self) -> Optional[str]:
        """
        Scan available serial ports for ESP32 devices, excluding EiBotBoard.
        Returns port name if found, None otherwise.
        """
        try:
            ports = list(serial.tools.list_ports.comports())
            logger.debug(f"Found {len(ports)} serial ports")

            for port in ports:
                # Skip EiBotBoard (NextDraw plotter)
                if "EiBotBoard" in port.description:
                    logger.debug(f"Skipping EiBotBoard on {port.device}")
                    continue

                # Check VID/PID pairs
                if port.vid is not None and port.pid is not None:
                    current_vid = f"{port.vid:04X}"
                    current_pid = f"{port.pid:04X}"

                    for vid, pid in self.KNOWN_VID_PID_PAIRS:
                        if current_vid == vid and current_pid == pid:
                            logger.info(f"Found Lilygo display on port {port.device}")
                            return port.device

            logger.debug("No Lilygo display found in port scan")
            return None

        except Exception as e:
            logger.error(f"Error scanning serial ports: {str(e)}")
            return None

    def _connect_internal(self, baud_rate: int = 115200) -> bool:
        """Internal connection method without lock (call with lock held)"""
        try:
            # Close existing connection if any
            if self.port and self.port.is_open:
                try:
                    self.port.close()
                except:
                    pass
                self.port = None

            # Find the device
            self.device_path = self.find_port()
            if not self.device_path:
                logger.warning("No Lilygo display found")
                return False

            # Open serial connection with proper timeouts
            self.port = serial.Serial(
                port=self.device_path,
                baudrate=baud_rate,
                timeout=self.READ_TIMEOUT,
                write_timeout=self.WRITE_TIMEOUT,
                # Additional settings for reliability
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )

            # Clear buffers
            self.port.reset_input_buffer()
            self.port.reset_output_buffer()

            # Small delay to let connection stabilize
            time.sleep(0.1)

            # Test connection
            if self._test_connection_internal():
                self.connected = True
                self._last_connection_check = time.time()
                logger.info(f"Connected to Lilygo display on {self.device_path}")
                return True
            else:
                logger.warning("Connection test failed")
                if self.port:
                    self.port.close()
                self.port = None
                return False

        except serial.SerialException as e:
            logger.error(f"Failed to connect to Lilygo display: {str(e)}")
            self.port = None
            self.connected = False
            return False

    def connect(self, baud_rate: int = 115200) -> bool:
        """Establish connection to Lilygo display with retry logic"""
        with self._connection_lock:
            if self.connected and self._is_connection_healthy_internal():
                return True

            for attempt in range(self.MAX_RETRIES):
                if attempt > 0:
                    logger.info(f"Connection attempt {attempt + 1}/{self.MAX_RETRIES}")
                    time.sleep(self.RETRY_DELAY * attempt)  # Exponential backoff

                if self._connect_internal(baud_rate):
                    return True

            logger.error(f"Failed to connect after {self.MAX_RETRIES} attempts")
            return False

    def disconnect(self):
        """Safely disconnect from device"""
        with self._connection_lock:
            if self.port and self.port.is_open:
                try:
                    # Flush buffers before closing
                    self.port.flush()
                    time.sleep(0.1)
                    self.port.close()
                    logger.info("Disconnected from Lilygo display")
                except Exception as e:
                    logger.error(f"Error disconnecting: {str(e)}")
                finally:
                    self.port = None
                    self.connected = False

    def _test_connection_internal(self) -> bool:
        """Test if the device is responsive (call with lock held)"""
        if not self.port or not self.port.is_open:
            return False

        try:
            # Clear any pending data
            self.port.reset_input_buffer()

            # Send AT command
            self.port.write(b'AT\r\n')
            self.port.flush()

            # Wait for response
            response = self.port.readline().decode('utf-8', errors='ignore').strip()
            return response == 'OK'

        except Exception as e:
            logger.debug(f"Connection test failed: {str(e)}")
            return False

    def _is_connection_healthy_internal(self) -> bool:
        """Check if connection is still healthy (call with lock held)"""
        if not self.connected or not self.port or not self.port.is_open:
            return False

        # Periodic health check
        current_time = time.time()
        if current_time - self._last_connection_check > self.CONNECTION_CHECK_INTERVAL:
            self._last_connection_check = current_time
            return self._test_connection_internal()

        return True

    def _ensure_connection(self) -> bool:
        """Ensure we have a valid connection, reconnect if necessary"""
        with self._connection_lock:
            if self._is_connection_healthy_internal():
                return True

            logger.info("Connection not healthy, attempting to reconnect...")
            self.connected = False

            for attempt in range(self.MAX_RETRIES):
                if attempt > 0:
                    time.sleep(self.RETRY_DELAY * attempt)

                if self._connect_internal():
                    return True

            return False

    def _send_json_command(self, data: dict) -> bool:
        """Send JSON command with proper error handling and retry logic"""
        for attempt in range(self.MAX_RETRIES):
            if not self._ensure_connection():
                logger.error("Failed to establish connection")
                return False

            try:
                with self._connection_lock:
                    if not self.port or not self.port.is_open:
                        continue

                    # Clear input buffer before sending
                    self.port.reset_input_buffer()

                    # Send JSON data
                    json_data = json.dumps(data)
                    message = (json_data + '\n').encode('utf-8')

                    self.port.write(message)
                    self.port.flush()

                    # Wait for acknowledgment
                    start_time = time.time()
                    response = ""

                    while time.time() - start_time < self.READ_TIMEOUT:
                        if self.port.in_waiting > 0:
                            response = self.port.readline().decode('utf-8', errors='ignore').strip()
                            break
                        time.sleep(0.01)

                    if response:
                        logger.debug(f"Received response: {response}")
                        return True
                    else:
                        logger.warning(f"No response received (attempt {attempt + 1}/{self.MAX_RETRIES})")

            except serial.SerialTimeoutException:
                logger.warning(f"Write timeout (attempt {attempt + 1}/{self.MAX_RETRIES})")
                self.connected = False

            except Exception as e:
                logger.error(f"Error sending command: {str(e)} (attempt {attempt + 1}/{self.MAX_RETRIES})")
                self.connected = False

            if attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_DELAY * (attempt + 1))

        return False

    def test_connection(self) -> bool:
        """Public method to test if the device is responsive"""
        return self._ensure_connection()

    def send_plot_data(self, time_data, svg_name, layer_name) -> bool:
        """Send plot data to the display"""
        try:
            duration = time_data.get("project_duration", 0)

            plot_data = {
                "command": "PLOT_START",
                "start_time": time_data.get("project_start", None),
                "filename": svg_name,
                "layer": layer_name,
                "duration": duration,
                "color": "#ffffff" if layer_name == "all" else time_data.get('layer_color', '#ffffff'),
                "end_time": calculate_end_time(duration)
            }

            logger.info(f"Sending plot data for {svg_name} layer {layer_name}")
            return self._send_json_command(plot_data)

        except Exception as e:
            logger.error(f"Error preparing plot data: {str(e)}")
            return False

    def goto_bullseye_page(self) -> bool:
        """Send command to go to bullseye page"""
        logger.info("Sending GOTO_BULLSEYE command")
        return self._send_json_command({"command": "GOTO_BULLSEYE"})

    def send_test_message(self) -> bool:
        """Send a test message to verify communication"""
        test_data = {
            "command": "PLOT_START",
            "start_time": "2025-1-1T12:00:00",
            "filename": "test123.svg",
            "layer": "1",
            "duration": 3600,
            "color": "#FF0F00",
            "end_time": "2025-1-1T13:00:00"
        }

        logger.info("Sending test message")
        return self._send_json_command(test_data)


# Global singleton instance
_display_instance = None
_display_lock = threading.Lock()


def get_display() -> LilygoDisplay:
    """Get or create the singleton display instance"""
    global _display_instance
    if _display_instance is None:
        with _display_lock:
            if _display_instance is None:
                _display_instance = LilygoDisplay()
    return _display_instance


# Public API functions using singleton
def checkSerialConnection() -> bool:
    """Check if serial connection is working"""
    display = get_display()
    return display.test_connection()


def sendPlotStartToSerial(time_data, svg_name, layer_name) -> bool:
    """Send plot start data to serial display"""
    logger.info(f"Sending plot data to serial: {svg_name} layer {layer_name}")
    display = get_display()
    return display.send_plot_data(time_data, svg_name, layer_name)


def gotoBullseyePage() -> str:
    """Navigate to bullseye page on display"""
    display = get_display()
    if display.goto_bullseye_page():
        return "Message sent"
    else:
        return "Failed to send message"


def sendTestPlotMessage() -> str:
    """Send test plot message to display"""
    display = get_display()
    if display.send_test_message():
        return "Message sent"
    else:
        return "Failed to send message"


# Initialize connection on module import
logger.info("Initializing Lilygo display connection...")
try:
    display = get_display()
    if display.test_connection():
        logger.info("Successfully connected to Lilygo display on startup")
    else:
        logger.warning("Could not connect to Lilygo display on startup (will retry on demand)")
except Exception as e:
    logger.error(f"Error during startup connection: {str(e)}")
