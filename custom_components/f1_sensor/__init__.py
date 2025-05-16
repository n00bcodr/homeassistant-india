import logging
from datetime import timedelta
import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    PLATFORMS,
    API_URL,
    DRIVER_STANDINGS_URL,
    CONSTRUCTOR_STANDINGS_URL
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration via config flow."""

    # Coordinator for "Current Season"
    race_coordinator = F1DataCoordinator(
        hass,
        API_URL,
        "F1 Race Data Coordinator"
    )

    # Coordinator for "Driver Standings"
    driver_coordinator = F1DataCoordinator(
        hass,
        DRIVER_STANDINGS_URL,
        "F1 Driver Standings Coordinator"
    )

    # Coordinator for "Constructor Standings" – required for the constructor sensor
    constructor_coordinator = F1DataCoordinator(
        hass,
        CONSTRUCTOR_STANDINGS_URL,
        "F1 Constructor Standings Coordinator"
    )

    # Initial call
    await race_coordinator.async_config_entry_first_refresh()
    await driver_coordinator.async_config_entry_first_refresh()
    await constructor_coordinator.async_config_entry_first_refresh()

    # Save in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "race_coordinator": race_coordinator,
        "driver_coordinator": driver_coordinator,
        "constructor_coordinator": constructor_coordinator,  # Important
    }

    # Load sensor.py (and possibly other platforms)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Clean up when the integration is removed."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class F1DataCoordinator(DataUpdateCoordinator):
    """Handles updates from a given F1 endpoint."""

    def __init__(self, hass: HomeAssistant, url: str, name: str):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1)
        )
        self._session = aiohttp.ClientSession()
        self._url = url

    async def _async_update_data(self):
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(self._url) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"Error fetching data: {response.status}")
                    return await response.json()
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err