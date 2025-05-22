import serial_asyncio_fast
from datetime import datetime
from typing import Optional
import struct
import logging
import asyncio

_LOGGER = logging.getLogger(__name__)

class GMCDeviceAsync:
    """
    An async class to interact with GQ GMC Geiger Counter devices.
    Implements the GQ-RFC1201 protocol specification.
    """

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 57600):
        """Initialize GMC device connection parameters."""
        self.port = port
        self.baudrate = baudrate
        self.reader = None
        self.writer = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Establish connection to the device."""
        try:
            self.reader, self.writer = await serial_asyncio_fast.open_serial_connection(
                url=self.port,
                baudrate=self.baudrate,
            )
            _LOGGER.debug("Connected to GMC device")
        except Exception as e:
            _LOGGER.error("Failed to connect: %s", str(e))
            raise

    async def _send_command(self, cmd: str, read_size: int = 0) -> Optional[bytes]:
        """Send a command and read the response."""
        async with self._lock:
            try:
                # Clear buffers and send command
                self.reader._buffer.clear()
                self.writer.write(cmd.encode())
                await self.writer.drain()
                await asyncio.sleep(0.1)  # Small delay for device processing

                # Read response if expected
                if read_size > 0:
                    response = await asyncio.wait_for(
                        self.reader.read(read_size),
                        timeout=1.0
                    )
                    if len(response) != read_size:
                        _LOGGER.debug("Invalid response length: got %d, expected %d", len(response), read_size)
                        return None
                    return response
                return b''
            except Exception as e:
                _LOGGER.error("Command failed: %s", str(e))
                return None

    def _check_terminator(self, response: bytes) -> bool:
        """Check if response has valid 0xAA terminator."""
        if not response or response[-1] != 0xAA:
            _LOGGER.debug("Invalid response: missing 0xAA terminator")
            return False
        return True

    async def get_model(self) -> Optional[tuple[str, str]]:
        """
        Get hardware model and firmware version (15 bytes ASCII).
        Returns: Tuple of (model, revision) where model is first 8 chars and revision is the rest
        """
        response = await self._send_command("<GETVER>>", 15)
        if not response:
            return None
        version_str = response.decode().strip()
        model = version_str[:8].strip()
        revision = version_str[8:].strip()
        return model, revision

    async def get_cpm(self) -> Optional[int]:
        """Get current CPM value (2 bytes unsigned int)."""
        response = await self._send_command("<GETCPM>>", 2)
        if not response:
            return None
        return int.from_bytes(response, "big")

    async def get_voltage(self) -> Optional[float]:
        """Get battery voltage (1 byte, value * 10V)."""
        response = await self._send_command("<GETVOLT>>", 1)
        if not response:
            return None
        return response[0] / 10.0

    async def get_serial_number(self) -> Optional[str]:
        """Get serial number (7 bytes)."""
        response = await self._send_command("<GETSERIAL>>", 7)
        if not response:
            return None
        return "".join([hex(x)[2:].upper() for x in response])

    async def get_temperature(self) -> Optional[float]:
        """
        Get temperature in Celsius (4 bytes).
        Only supported by GMC-320 Re.3.01 or later.
        Returns: integer_part + decimal_part/100, negative if sign_byte != 0
        """
        response = await self._send_command("<GETTEMP>>", 4)
        if not response or not self._check_terminator(response):
            return None
        integer_part = response[0]
        decimal_part = response[1]
        is_negative = response[2] != 0
        temp = integer_part + (decimal_part / 100)
        return -temp if is_negative else temp

    async def get_datetime(self) -> Optional[datetime]:
        """
        Get device's date and time (7 bytes: YY MM DD HH MM SS 0xAA).
        Supported by GMC-280, GMC-300 Re.3.00 or later.
        """
        response = await self._send_command("<GETDATETIME>>", 7)
        if not response or not self._check_terminator(response):
            return None
        year, month, day, hour, minute, second, _ = response
        return datetime(2000 + year, month, day, hour, minute, second)

    async def get_gyroscope(self) -> Optional[tuple[int, int, int]]:
        """
        Get gyroscope data (7 bytes: XX XX YY YY ZZ ZZ 0xAA).
        Only supported by GMC-320 Re.3.01 or later.
        Returns: Tuple of (X, Y, Z) positions
        """
        try:
            response = await self._send_command("<GETGYRO>>", 7)
            if not response or not self._check_terminator(response):
                return None

            # Read values in big-endian format as specified in the protocol
            x = int.from_bytes(response[0:2], "big")  # Using signed integers
            y = int.from_bytes(response[2:4], "big")
            z = int.from_bytes(response[4:6], "big")
            
            _LOGGER.debug("Gyroscope raw data: %r, values: X=%d, Y=%d, Z=%d", response, x, y, z)
            return (x, y, z)
        except Exception as e:
            _LOGGER.error("Failed to read gyroscope: %s", str(e))
            return None

    async def get_unit_conversion_factor(self) -> Optional[float]:
        """Get the unit conversion factor from the device configuration."""
        data = await self._send_command("<GETCFG>>", 256)  # Read first 256 bytes which contain calibration
        if not data:
            return None
        try:
            cpm = [struct.unpack_from(">H", data, x)[0] for x in [8, 14, 20]]
            usv = [struct.unpack_from("<f", data, x)[0] for x in [10, 16, 22]]
            return sum([x / y for x, y in zip(usv, cpm)]) / len(cpm)
        except Exception as e:
            _LOGGER.error("Failed to calculate conversion factor: %s", str(e))
            return None

    async def power_off(self) -> None:
        """Power off the device."""
        await self._send_command("<POWEROFF>>")

    async def power_on(self) -> None:
        """Power on the device."""
        await self._send_command("<POWERON>>")

    async def reboot(self) -> None:
        """Reboot the device."""
        await self._send_command("<REBOOT>>")

    async def factory_reset(self) -> bool:
        """Reset unit to factory default."""
        response = await self._send_command("<FACTORYRESET>>", 1)
        return len(response) == 1 and response[0] == 0xAA

    async def close(self) -> None:
        """Close the serial connection."""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

async def main():
    async with GMCDeviceAsync() as device:
        results = await asyncio.gather(
            device.get_model(),
            device.get_cpm(),
            device.get_serial_number(),
            device.get_voltage(),
            device.get_temperature(),
            device.get_datetime(),
            device.get_unit_conversion_factor(),
        )

        print({
            "model": results[0][0],
            "revision": results[0][1],
            "cpm": results[1],
            "serial": results[2],
            "voltage": results[3],
            "temperature": results[4],
            "datetime": results[5],
            "conversion": results[6],
        })


if __name__ == "__main__":
    asyncio.run(main()) 