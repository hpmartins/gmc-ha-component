"""Config flow for GMC Radiation Counter integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady

from .gmc_async import GMCDeviceAsync

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("port"): str,
        vol.Required("baudrate", default=57600): int,
        vol.Optional("scan_interval", default=30): int,
    }
)

class GMCConfigFlow(config_entries.ConfigFlow, domain="gmc"):
    """Handle a config flow for GMC Radiation Counter."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            _LOGGER.debug(
                "Attempting to connect to GMC device at %s (baudrate: %s)",
                user_input["port"],
                user_input["baudrate"]
            )
            
            try:
                gmc = GMCDeviceAsync(
                    port=user_input["port"],
                    baudrate=user_input["baudrate"]
                )
                await gmc.connect()
                _LOGGER.debug("Successfully connected to GMC device")
                
                try:
                    _LOGGER.debug("Requesting device serial number...")
                    serial_number = await gmc.get_serial_number()
                    if not serial_number:
                        _LOGGER.error("Failed to get device serial number - received empty response")
                        raise ConfigEntryNotReady("Could not get device serial number")
                    _LOGGER.debug("Got device serial number: %s", serial_number)
                        
                    _LOGGER.debug("Requesting device version...")
                    model_info = await gmc.get_model()
                    if not model_info:
                        _LOGGER.error("Failed to get device model/revision - received empty response")
                        raise ConfigEntryNotReady("Could not get device model/revision")
                    model, revision = model_info
                    _LOGGER.debug("Got device model: %s, revision: %s", model, revision)
                    
                    # Use the serial number as the unique ID
                    await self.async_set_unique_id(serial_number)
                    self._abort_if_unique_id_configured()

                    # Store additional device info in the config entry
                    user_input["serial_number"] = serial_number
                    user_input["model"] = model
                    user_input["revision"] = revision

                    _LOGGER.debug(
                        "Successfully configured GMC device: %s (S/N: %s, Rev: %s)",
                        model,
                        serial_number,
                        revision
                    )

                    return self.async_create_entry(
                        title=f"{model} ({serial_number})", 
                        data=user_input
                    )
                    
                finally:
                    _LOGGER.debug("Closing connection to GMC device")
                    await gmc.close()

            except Exception as err:
                _LOGGER.error("Failed to connect to GMC device: %s", str(err))
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return GMCOptionsFlowHandler(config_entry)

class GMCOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle GMC Radiation Counter options."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval",
                        default=self.options.get("scan_interval", 30),
                    ): int,
                }
            ),
        )
