import serial
from datetime import datetime
from typing import Optional
import struct
import logging

_LOGGER = logging.getLogger(__name__)

class GMCDevice:
    """
    A class to interact with GQ GMC Geiger Counter devices.
    Implements the GQ-RFC1201 protocol specification.
    """

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 57600):
        """
        Initialize the GMC device connection.

        Args:
            port: Serial port path (default: /dev/ttyUSB0)
            baudrate: Baud rate for serial communication (default: 57600 for GMC-300 V3.xx)
        """
        self.port = port
        self.baudrate = baudrate
        _LOGGER.debug("Initializing GMC device on port %s with baudrate %d", port, baudrate)
        try:
            self.serial = serial.Serial(self.port, baudrate, timeout=1)
            _LOGGER.debug("Successfully opened serial connection")
        except serial.SerialException as e:
            _LOGGER.error("Failed to connect to %s: %s", self.port, str(e))
            raise Exception(f"Failed to connect to {self.port}: {str(e)}")

    def _send_command(self, cmd: str, is_bytes: bool = False, retries: int = 3) -> bytes:
        """
        Send a command to the device and read the response.

        Args:
            cmd: Command string to send
            is_bytes: Whether cmd is already bytes
            retries: Number of retries on invalid response
        Returns:
            bytes: Raw response from the device
        """
        _LOGGER.debug("Sending command: %r", cmd)
        
        for attempt in range(retries):
            try:
                # Clear any pending data
                self.serial.reset_input_buffer()
                self.serial.reset_output_buffer()
                
                # Send command
                if is_bytes:
                    self.serial.write(cmd)
                else:
                    self.serial.write(cmd.encode())
                
                # Read response
                response = self.serial.readline()
                _LOGGER.debug(
                    "Attempt %d/%d - Received response: %r (length: %d bytes)", 
                    attempt + 1, retries, response, len(response)
                )
                
                # Check for obviously invalid responses
                # if len(response) == 1 and response[0] in [b'*'[0], b'\n'[0], b'\r'[0]]:
                #     if attempt < retries - 1:
                #         _LOGGER.debug("Got invalid single-byte response, retrying...")
                #         continue
                
                return response
                
            except Exception as e:
                _LOGGER.error("Error in _send_command (attempt %d/%d): %s", 
                            attempt + 1, retries, str(e))
                if attempt == retries - 1:
                    raise

    def get_unit_conversion_factor(self) -> Optional[float]:
        """
        Get the unit conversion factor from the device configuration.
        """
        data = self._send_command("<GETCFG>>")
        if not data or len(data) < 26:
            print(
                f"""Received insufficient configuration data. Expected
                at least 26 bytes for calibration parameters, but received
                {len(data)} bytes."""
            )
            return None

        try:
            cpm = [struct.unpack_from(">H", data, x)[0] for x in [8, 14, 20]]
            usv = [struct.unpack_from("<f", data, x)[0] for x in [10, 16, 22]]
            return sum([x / y for x, y in zip(usv, cpm)]) / len(cpm)
        except Exception as e:
            print(
                f"An unexpected error occurred during final calibration parameter mapping: {e}"
            )
            return None

    def get_version(self) -> tuple[str, str]:
        """Get hardware model and firmware version."""
        _LOGGER.debug("Getting version info...")
        try:
            response = self._send_command("<GETVER>>")
            version_str = response.decode().strip()
            _LOGGER.debug("Version string: %r", version_str)
            return version_str
        except Exception as e:
            _LOGGER.error("Error getting version: %s", str(e))
            raise

    def get_cpm(self) -> int:
        """Get current CPM (Counts Per Minute) value."""
        _LOGGER.debug("Getting CPM reading...")
        try:
            response = self._send_command("<GETCPM>>")
            _LOGGER.debug("Raw CPM response: %r", response)
            
            # GMC devices typically return 2 bytes for CPM
            # Only use the first 2 bytes and validate the value
            cpm = int.from_bytes(response[:2], "big")
            _LOGGER.debug("Parsed CPM value: %d", cpm)
            
            # Add reasonable bounds checking
            if cpm < 0 or cpm > 1000000:  # 1M CPM is already extremely high
                _LOGGER.error("CPM value out of bounds: %d", cpm)
                raise ValueError(f"CPM value out of reasonable bounds: {cpm}")
            
            return cpm
        except Exception as e:
            _LOGGER.error("Error getting CPM: %s", str(e))
            raise

    def get_serial_number(self) -> str:
        """Get device serial number."""
        _LOGGER.debug("Getting serial number...")
        try:
            response = self._send_command("<GETSERIAL>>")
            _LOGGER.debug("Raw serial number response: %r", response)
            serial = "".join([hex(x)[2:] for x in response]).upper()
            _LOGGER.debug("Parsed serial number: %s", serial)
            return serial
        except Exception as e:
            _LOGGER.error("Error getting serial number: %s", str(e))
            raise

    def get_voltage(self) -> float:
        """Get battery voltage status."""
        _LOGGER.debug("Getting voltage reading...")
        try:
            response = self._send_command("<GETVOLT>>")
            _LOGGER.debug("Raw voltage response: %r", response)

            # GMC devices typically return 2 bytes for voltage
            # Only use the first 2 bytes and validate the value
            raw_voltage = int.from_bytes(response[:2], "big")
            voltage = raw_voltage / 10.0  # Convert to actual voltage
            _LOGGER.debug("Parsed voltage value: %.2fV (raw: %d)", voltage, raw_voltage)
            
            # Add reasonable bounds checking
            if voltage < 0.0 or voltage > 10.0:  # Most GMC devices use 3-4.2V batteries
                _LOGGER.error("Voltage value out of bounds: %.2fV", voltage)
                raise ValueError(f"Voltage value out of reasonable bounds: {voltage}V")
            
            return voltage
        except Exception as e:
            _LOGGER.error("Error getting voltage: %s", str(e))
            raise

    def get_temperature(self) -> Optional[float]:
        """
        Get temperature in Celsius.
        Only supported by GMC-320 Re.3.01 or later.
        """
        response = self._send_command("<GETTEMP>>")
        if len(response) != 4:
            return None

        integer_part = response[0]
        decimal_part = response[1]
        is_negative = response[2] != 0

        temp = integer_part + (decimal_part / 100)
        return -temp if is_negative else temp

    def get_datetime(self) -> Optional[datetime]:
        """
        Get device's current date and time.
        Supported by GMC-280, GMC-300 Re.3.00 or later.
        """
        response = self._send_command("<GETDATETIME>>")
        if len(response) != 7 or response[-1] != 0xAA:
            return None

        year, month, day, hour, minute, second, _ = response
        return datetime(2000 + year, month, day, hour, minute, second)

    def set_datetime(self, dt: datetime | None = None) -> bool:
        """
        Set device's date and time.
        If no datetime is provided, current system time will be used.
        """
        if dt is None:
            dt = datetime.now()

        dt_cmd = struct.pack(
            ">BBBBBB",
            dt.year - 2000,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second,
        )
        response = self._send_command(b"<SETDATETIME" + dt_cmd + b">>", True)
        return len(response) == 1 and response[0] == 0xAA

    def enable_heartbeat(self) -> None:
        """Enable heartbeat mode (CPS data every second)."""
        self.serial.reset_input_buffer()  # Clear any existing data
        self.serial.write("<HEARTBEAT1>>".encode())

    def disable_heartbeat(self) -> None:
        """Disable heartbeat mode."""
        self.serial.write("<HEARTBEAT0>>".encode())
        self.serial.reset_input_buffer()

    def read_heartbeat(self) -> Optional[int]:
        """
        Read a single heartbeat value when heartbeat mode is enabled.

        Returns:
            CPS value or None if no data available
        """
        try:
            data = self.serial.read(2)  # Read exactly 2 bytes
            if len(data) != 2:
                return None
            value = struct.unpack(">H", data)[0] & 0x3FFF  # Mask with 14 bits
            return value
        except (struct.error, serial.SerialException):
            return None

    def power_off(self) -> None:
        """Power off the device."""
        print("Powering off...")
        self._send_command("<POWEROFF>>")

    def power_on(self) -> None:
        """Power on the device."""
        print("Powering on...")
        self._send_command("<POWERON>>")

    def factory_reset(self) -> bool:
        """Reset unit to factory default."""
        response = self._send_command("<FACTORYRESET>>")
        return len(response) == 1 and response[0] == 0xAA

    def reboot(self) -> None:
        """Reboot the device."""
        self._send_command("<REBOOT>>")

    def get_gyroscope(self) -> Optional[tuple[int, int, int]]:
        """
        Get gyroscope data (X, Y, Z positions).
        Only supported by GMC-320 Re.3.01 or later.

        Returns:
            Tuple of (X, Y, Z) positions or None if not supported
        """
        response = self._send_command("<GETGYRO>>")
        if len(response) != 7 or response[-1] != 0xAA:
            return None

        x = int.from_bytes(response[0:2], "big")
        y = int.from_bytes(response[2:4], "big")
        z = int.from_bytes(response[4:6], "big")
        return (x, y, z)

    def close(self) -> None:
        """Close the serial connection."""
        if hasattr(self, "serial") and self.serial.is_open:
            self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

if __name__ == "__main__":
    with GMCDevice() as device:
        print("version: ", device.get_version())
        print("cpm: ", device.get_cpm())
        print("serial number: ", device.get_serial_number())
        print("voltage: ", device.get_voltage())
        print("temperature: ", device.get_temperature())
        print("datetime: ", device.get_datetime())
        print("gyroscope: ", device.get_gyroscope())
        print("conversion factor: ", device.get_unit_conversion_factor())

        # print("Heartbeat Mode Test:")
        # test_heartbeat(device)
