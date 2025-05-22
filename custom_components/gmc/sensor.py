"""Platform for GMC Radiation Counter sensors."""
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from . import DOMAIN, SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GMC Radiation Counter sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    # Get device info from the config entry
    device_name = config_entry.title
    serial_number = config_entry.data["serial_number"]
    model = config_entry.data["model"]
    revision = config_entry.data["revision"]

    entities = []
    for description in SENSOR_TYPES:
        entities.append(
            GMCSensor(
                coordinator=coordinator,
                device_name=device_name,
                serial_number=serial_number,
                model=model,
                revision=revision,
                description=description,
            )
        )

    async_add_entities(entities)

class GMCSensor(CoordinatorEntity, SensorEntity):
    """Representation of a GMC Radiation Counter sensor."""

    def __init__(
        self,
        coordinator,
        device_name: str,
        serial_number: str,
        model: str,
        revision: str,
        description,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{serial_number}_{description.key}"
        self._attr_has_entity_name = True

        # Device info for grouping entities
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial_number)},
            name=device_name,
            manufacturer="GQ Electronics LLC",
            model=f"{model} (Rev. {revision})",
            sw_version=revision,
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
            
        try:
            return self.coordinator.data.get(self.entity_description.key)
        except Exception as e:
            _LOGGER.error(
                "Error getting value for %s: %s",
                self.entity_description.key,
                str(e)
            )
            return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.entity_description.key in self.coordinator.data
        )

