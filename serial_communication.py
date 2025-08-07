import serial
import serial.tools.list_ports
import pytz
import json
import logging
from datetime import datetime
from typing import Optional, List, Tuple
from time_utils import calculate_end_time


logger = logging.getLogger(__name__)


# TODO: Listen for DOUBLE_BUTTON_PRESS
class LilygoDisplay:
    """Handles communication with Lilygo AMOLED Display"""

    # Known ESP32 USB-to-UART bridge chips
    KNOWN_VID_PID_PAIRS: List[Tuple[str, str]] = [
        ('10C4', 'EA60'),  # Silicon Labs CP210x
        ('1A86', '7523'),  # CH340
        ('0403', '6001'),  # FTDI FT232R
        ('303A', '1001'),  # Espressif USB JTAG/serial debug unit - Lilygo
    ]

    def __init__(self):
        self.port = None
        self.connected = False
        self.device_path = None

    def find_port(self) -> Optional[str]:
        """
        Scan available serial ports for ESP32 devices, excluding EiBotBoard.
        Returns port name if found, None otherwise.
        """
        print("Scanning serial ports for Lilygo display")
        print(serial.tools.list_ports.comports())
        try:
            ports = list(serial.tools.list_ports.comports())
            #print(f"Found {len(ports)} serial ports")

            # Print detailed information about all ports
            for port in ports:
    #             print(f"""
    # Port Details:
    # - Device: {port.device}
    # - Name: {port.name}
    # - Description: {port.description}
    # - Hardware ID: {port.hwid}
    # - VID: {port.vid}
    # - PID: {port.pid}
    # - Serial Number: {port.serial_number}
    # - Manufacturer: {port.manufacturer}
    # """)

                # Skip if it's an EiBotBoard
                if "EiBotBoard" in port.description:
                    #print(f"Skipping EiBotBoard on {port.device}")
                    continue

                # Convert VID/PID to hex strings for comparison
                if port.vid is not None and port.pid is not None:
                    current_vid = f"{port.vid:04X}"
                    current_pid = f"{port.pid:04X}"

                    #print(f"Checking VID:PID pair: {current_vid}:{current_pid}")

                    # Check against known pairs
                    for vid, pid in self.KNOWN_VID_PID_PAIRS:
                        #print(f"Comparing against known pair: {vid}:{pid}")
                        if current_vid == vid and current_pid == pid:
                            #print(f"Found matching Lilygo display on port {port.device}")
                            return port.device

            print("No Lilygo display found")
            return None

        except Exception as e:
            print(f"Error scanning serial ports: {str(e)}")
            return None


    def connect(self, baud_rate: int = 115200, timeout: float = 1.0) -> bool:
        """Establish connection to Lilygo display"""
        if self.connected:
            return True

        self.device_path = self.find_port()
        if not self.device_path:
            print("No Lilygo display found")
            return False

        try:
            self.port = serial.Serial(
                port=self.device_path,
                baudrate=baud_rate,
                timeout=timeout
            )
            self.connected = True
            print(f"Connected to Lilygo display on {self.device_path}")
            return True

        except serial.SerialException as e:
            print(f"Failed to connect to Lilygo display: {str(e)}")
            self.port = None
            self.connected = False
            return False

    def disconnect(self):
        """Safely disconnect from device"""
        if self.port and self.port.is_open:
            try:
                self.port.close()
                print("Disconnected from Lilygo display")
            except Exception as e:
                print(f"Error disconnecting: {str(e)}")
            finally:
                self.port = None
                self.connected = False

    def test_connection(self) -> bool:
        """Test if the device is responsive"""
        if not self.connected and not self.connect():
            return False

        try:
            self.port.write(b'AT\r\n')
            response = self.port.readline().decode('utf-8').strip()
            return response == 'OK'
        except Exception as e:
            print(f"Connection test failed: {str(e)}")
            return False

    def send_plot_data(self, time_data, svg_name, layer_name) -> bool:
        """Send plot data to the display"""
        try:
            if not self.connected and not self.connect():
                return False

            # Parse job data
            #parsed_data = json.loads(job.layer_colors)
            #layer_info = parsed_data[int(layer)-1] if layer != "all" else None

            duration = time_data.get("project_duration", 0)
            # Prepare plot data
            plot_data = {
                "command": "PLOT_START",
                "start_time": time_data.get("project_start", None),
                "filename": svg_name,
                "layer": layer_name,
                "duration": duration,
                "color": "#ffffff" if layer_name == "all" else time_data.get('layer_color', '#ffffff'),
                "end_time": calculate_end_time(duration)
            }

            print(f"Sending plot data: {plot_data}")
            json_data = json.dumps(plot_data)

            self.port.write((json_data + '\n').encode())
            response = self.port.readline().decode().strip()
            print(f"Received response: {response}")

            return True

        except Exception as e:
            print(f"Error sending plot data: {str(e)}")
            return False

    def goto_bullseye_page(self) -> bool:
        """Send a test message to verify communication"""

        try:
            if not self.connected and not self.connect():
                print("Failed to connect")
                return False

            test_data = {
                "command": "GOTO_BULLSEYE"
            }

            json_data = json.dumps(test_data)
            self.port.write((json_data + '\n').encode())
            response = self.port.readline().decode().strip()
            print(f"Test message sent. Response: {response}")





            return True

        except Exception as e:
            print(f"Error sending test message: {str(e)}")
            return False
    def send_test_message(self) -> bool:
        """Send a test message to verify communication"""

        try:
            if not self.connected and not self.connect():
                print("Failed to connect")
                return False

            test_data = {
                "command": "PLOT_START",
                "start_time": "2025-1-1T12:00:00",
                "filename": "test123.svg",
                "layer": "1",
                "duration": 3600,
                "color": "#FF0F00",
                "end_time": "2025-1-1T13:00:00"
            }

            json_data = json.dumps(test_data)
            self.port.write((json_data + '\n').encode())
            response = self.port.readline().decode().strip()
            print(f"Test message sent. Response: {response}")

            return True

        except Exception as e:
            print(f"Error sending test message: {str(e)}")
            return False

# Example usage functions
def checkSerialConnection():
    display = LilygoDisplay()
    return display.test_connection()

def sendPlotStartToSerial(time_data, svg_name, layer_name):
    print("Sending plot data to serial")
    display = LilygoDisplay()
    return display.send_plot_data(time_data, svg_name, layer_name)

def gotoBullseyePage():
    display = LilygoDisplay()
    if display.connect():
        print("Successfully connected to Lilygo display")
    else:
        print("Failed to connect to Lilygo display")

    res = display.goto_bullseye_page()
    if(res):
        return "Message sent"
    else:
        return "Failed to send message"

def sendTestPlotMessage():
    display = LilygoDisplay()
    if display.connect():
        print("Successfully connected to Lilygo display")
    else:
        print("Failed to connect to Lilygo display")

    res = display.send_test_message()
    if(res):
        return "Message sent"
    else:
        return "Failed to send message"

# # # Initialize connection on module import
# display = LilygoDisplay()
# if display.connect():
#     print("Successfully connected to Lilygo display")
# else:
#     print("Failed to connect to Lilygo display")
