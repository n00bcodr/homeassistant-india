# custom_components/mediabrowser/__init__.py
# --- CORRECTED VERSION (Added CONF_NAME import) ---
"""The Media Browser (Emby/Jellyfin) integration."""
from __future__ import annotations

import asyncio
import logging

import aiohttp
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryAuthFailed,
    ConfigEntryNotReady as HAConfigEntryNotReady, # Alias base class
)
# Ensure CONF_NAME is imported from homeassistant.const
from homeassistant.const import CONF_URL, Platform, CONF_API_KEY, CONF_NAME
from homeassistant.core import HomeAssistant
# Import helpers if used, ensure correct relative path
from .helpers import size_of, snake_cased_json

from .const import (
    # Import necessary constants, ensure they exist
    CONF_CACHE_SERVER_ID,
    CONF_CACHE_SERVER_NAME,
    CONF_CACHE_SERVER_PING,
    CONF_CACHE_SERVER_USER_ID,
    CONF_CACHE_SERVER_VERSION,
    # CONF_NAME should NOT be imported here
    DATA_HUB,
    DOMAIN,
)
# Import Hub and errors
from .hub import MediaBrowserHub, ClientMismatchError, ConnectError # Import Hub and relevant errors
# Import specific exceptions used in error handling
from .errors import RequestError

_LOGGER = logging.getLogger(__package__) # Use __package__

# Define platforms (ensure correct platform constants)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.MEDIA_PLAYER, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Media Browser (Emby/Jellyfin) from a config entry."""
    _LOGGER.debug("Setting up entry %s: %s", entry.entry_id, entry.title)

    try:
        hub = MediaBrowserHub(dict(entry.options))
    except ValueError as err:
        _LOGGER.error("Configuration error initializing Hub for %s: %s", entry.title, err)
        return False

    async def async_websocket_message(
        message_type: str, data: dict[str, Any] | None
    ) -> None:
        _LOGGER.debug(
            "%s firing event %s_%s (%d bytes)",
            hub.name, DOMAIN, message_type, size_of(data) if data else 0,
        )
        try:
            hass.bus.async_fire( f"{DOMAIN}_{message_type}", snake_cased_json(data))
        except (TypeError, ValueError) as json_err:
             _LOGGER.error("Failed to serialize data for event %s_%s: %s", DOMAIN, message_type, json_err)

    try:
        await hub.async_start(websocket=True)
        _LOGGER.debug("%s hub has started", hub.name)
    except ConfigEntryAuthFailed as err:
         _LOGGER.error("Authentication failed for %s: %s", hub.name, err); raise
    except ClientMismatchError as err:
         _LOGGER.error("Server ID mismatch during setup for %s: %s", hub.name, err)
         raise HAConfigEntryNotReady(f"Server ID mismatch: {err}") from err
    except (ConnectError, aiohttp.ClientConnectionError, asyncio.TimeoutError, TimeoutError) as err:
        _LOGGER.error("Connection error during setup for %s: %s", hub.name, err)
        raise HAConfigEntryNotReady(f"Connection error: {err}") from err
    except RequestError as err:
         _LOGGER.error("Request error during setup for %s: %s", hub.name, err)
         raise HAConfigEntryNotReady(f"Request error: {err}") from err
    except Exception as err:
         _LOGGER.exception("Unexpected error setting up %s: %s", hub.name, err)
         raise HAConfigEntryNotReady(f"Unexpected error: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_HUB: hub, "options": dict(entry.options)
    }

    # --- Update entry options with potentially refreshed server info ---
    updated_options = entry.options.copy()
    needs_update = False
    # Use CONF_NAME (imported from homeassistant.const) correctly here
    refreshed_data = {
         CONF_CACHE_SERVER_NAME: hub.server_name,
         CONF_CACHE_SERVER_ID: hub.server_id,
         CONF_CACHE_SERVER_PING: hub.server_ping,
         CONF_CACHE_SERVER_VERSION: hub.server_version,
         CONF_CACHE_SERVER_USER_ID: hub.user_id,
         # Update CONF_NAME only if it wasn't custom-set or differs from fetched
         CONF_NAME: hub.name if not entry.options.get(CONF_NAME) or entry.options.get(CONF_NAME) != hub.name else entry.options.get(CONF_NAME),
    }
    for key, value in refreshed_data.items():
         if value is not None and (key not in updated_options or updated_options[key] != value):
              updated_options[key] = value
              needs_update = True

    if needs_update:
         _LOGGER.debug("Updating entry options with refreshed server info.")
         hass.config_entries.async_update_entry(entry, options=updated_options)
    # --- End option update ---

    entry.async_on_unload(entry.add_update_listener(async_options_update_listener))
    unload_ws_listener = hub.on_websocket_message(async_websocket_message)
    entry.async_on_unload(unload_ws_listener)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Successfully set up Jellyfin integration for %s", hub.name)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s: %s", entry.entry_id, entry.title)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN)
        if domain_data and entry.entry_id in domain_data:
            entry_data = domain_data.pop(entry.entry_id)
            hub: MediaBrowserHub | None = entry_data.get(DATA_HUB)
            if hub: await hub.async_stop()
            if not hass.data[DOMAIN]: hass.data.pop(DOMAIN)
        else: _LOGGER.warning("Could not find hub data for entry %s during unload.", entry.entry_id)
    _LOGGER.debug("Unload status for %s: %s", entry.title, unload_ok)
    return unload_ok


async def async_options_update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Handle options update."""
    _LOGGER.debug("Options updated for %s, reloading entry.", config_entry.title)
    await hass.config_entries.async_reload(config_entry.entry_id)