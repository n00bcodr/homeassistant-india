from homeassistant import config_entries
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

class F1FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            # Create the configuration entry
            return self.async_create_entry(
                title=user_input["sensor_name"],  # Title shown in HA
                data=user_input                   # Store the entire user_input in entry.data
            )

        # Show form to enter sensor name and enabled sensors
        data_schema = vol.Schema({
            vol.Required("sensor_name", default="F1"): cv.string,
            vol.Required(
                "enabled_sensors",
                default=["next_race"]
            ): cv.multi_select({
                "next_race": "Next race",
                "current_season": "Current season",
                "driver_standings": "Driver standings",
                "constructor_standings": "Constructor standings",
                "weather": "Weather"
            }),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )

    async def async_step_reconfigure(self, user_input=None):
        """Allow reconfiguration of the integration."""
        errors = {}
        # If user submitted the form, update the entry and reload
        if user_input is not None:
            entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(
                entry,
                data_updates=user_input,
            )
        # Show the form pre-filled with existing settings
        entry = self._get_reconfigure_entry()
        current = entry.data
        data_schema = vol.Schema({
            vol.Required("sensor_name", default=current.get("sensor_name", "F1")): cv.string,
            vol.Required("enabled_sensors", default=current.get("enabled_sensors", [
                "next_race",
                "current_season",
                "driver_standings",
                "constructor_standings"
            ])): cv.multi_select({
                "next_race": "Next race",
                "current_season": "Current season",
                "driver_standings": "Driver standings",
                "constructor_standings": "Constructor standings",
                "weather": "Weather"
            }),
        })
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )