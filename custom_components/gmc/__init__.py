"""The GMC Radiation Counter integration."""
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.sensor import (
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)

from .gmc_async import GMCDeviceAsync

_LOGGER = logging.getLogger(__name__)

DOMAIN = "gmc"
PLATFORMS = ["sensor"]

# Default values
DEFAULT_CALIBRATION_FACTOR = 0.0065  # Default for GMC-300E Plus
DEFAULT_SCAN_INTERVAL = 30
MAX_CPM_VALUE = 1000000  # Maximum reasonable CPM value

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="cpm",
        name="CPM",
        icon="mdi:radioactive",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="CPM",
    ),
    SensorEntityDescription(
        key="usv_per_hour",
        name="Radiation Dose Rate",
        icon="mdi:radioactive",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="µSv/h",
        suggested_display_precision=3,
    ),
    SensorEntityDescription(
        key="voltage",
        name="Battery Voltage",
        icon="mdi:battery",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement="V",
    ),
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GMC Radiation Counter from a config entry."""
    port = entry.data["port"]
    baudrate = entry.data["baudrate"]
    scan_interval = entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)

    try:
        # Create device instance
        gmc = GMCDeviceAsync(port=port, baudrate=baudrate)
        await gmc.connect()
        
        # Test the connection and get initial readings
        # We'll retry a few times if we get invalid initial readings
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Get initial CPM reading
                cpm = await gmc.get_cpm()
                if cpm is None or cpm > MAX_CPM_VALUE:
                    if attempt < max_retries - 1:
                        _LOGGER.warning(
                            "Invalid initial CPM reading (attempt %d/%d): %s. Retrying...",
                            attempt + 1,
                            max_retries,
                            cpm
                        )
                        await gmc.close()
                        gmc = GMCDeviceAsync(port=port, baudrate=baudrate)
                        await gmc.connect()
                        continue
                    else:
                        raise ConfigEntryNotReady(
                            f"Invalid initial CPM reading after {max_retries} attempts: {cpm}"
                        )
                break
            except Exception as err:
                if attempt < max_retries - 1:
                    _LOGGER.warning(
                        "Error getting initial reading (attempt %d/%d): %s. Retrying...",
                        attempt + 1,
                        max_retries,
                        str(err)
                    )
                    await gmc.close()
                    continue
                raise
        
        # Get the calibration factor
        calibration_factor = await gmc.get_unit_conversion_factor()
        if calibration_factor is None:
            _LOGGER.warning(
                "Could not get calibration factor from device, using default value of %f",
                DEFAULT_CALIBRATION_FACTOR
            )
            calibration_factor = DEFAULT_CALIBRATION_FACTOR
        
    except Exception as err:
        try:
            await gmc.close()
        except:
            pass
        _LOGGER.exception("Error connecting to GMC device")
        raise ConfigEntryNotReady(
            f"Error connecting to GMC device at {port}: {str(err)}"
        ) from err

    async def async_update_data() -> Dict[str, Any]:
        """Fetch data from GMC device."""
        try:
            # Get all relevant data from the device
            cpm = await gmc.get_cpm()
            voltage = await gmc.get_voltage()

            if cpm is None:
                raise UpdateFailed("Failed to get CPM reading")
            if voltage is None:
                raise UpdateFailed("Failed to get voltage reading")

            # Calculate µSv/h from CPM
            try:
                usv_per_hour = round(float(cpm) * calibration_factor, 3)
            except (ValueError, TypeError, OverflowError) as e:
                _LOGGER.error("Failed to convert CPM to µSv/h: %s. Raw CPM value: %s", e, cpm)
                raise UpdateFailed(f"Invalid CPM value: {cpm}")
            
            return {
                "cpm": cpm,
                "voltage": voltage,
                "usv_per_hour": usv_per_hour
            }
            
        except Exception as err:
            raise UpdateFailed(f"Error communicating with GMC device: {err}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"GMC {entry.data['serial_number']}",
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store both the device and coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "device": gmc,
        "calibration_factor": calibration_factor,
    }

    # Set up the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Get the device instance
        device_data = hass.data[DOMAIN].pop(entry.entry_id)
        # Close the serial connection
        if "device" in device_data:
            await device_data["device"].close()
    
    return unload_ok

