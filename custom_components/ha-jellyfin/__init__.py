"""The Media Browser (Emby/Jellyfin) integration."""
from __future__ import annotations

import asyncio
import logging

import aiohttp
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
)
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant

from .helpers import size_of, snake_cased_json

from .const import (
    CONF_CACHE_SERVER_API_KEY,
    CONF_CACHE_SERVER_ID,
    CONF_CACHE_SERVER_NAME,
    CONF_CACHE_SERVER_PING,
    CONF_CACHE_SERVER_USER_ID,
    CONF_CACHE_SERVER_VERSION,
    DATA_HUB,
    DOMAIN,
    SERVICE_PURGE_DEVICES,
)
from .hub import MediaBrowserHub

_LOGGER = logging.getLogger(__package__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.MEDIA_PLAYER, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Media Browser (Emby/Jellyfin) from a config entry."""

    hub = MediaBrowserHub(dict(entry.options))

    async def async_websocket_message(
        message_type: str, data: dict[str, None] | None
    ) -> None:
        _LOGGER.debug(
            "%s firing event %s_%s (%d bytes)",
            hub.server_name,
            DOMAIN,
            message_type,
            size_of(data),
        )
        hass.bus.async_fire(
            f"{DOMAIN}_{message_type}",
            snake_cased_json(data),
        )

    try:
        await hub.async_start(True)
    except aiohttp.ClientConnectionError as err:
        raise ConfigEntryNotReady from err
    except aiohttp.ClientResponseError as err:
        if err.status == 401:
            raise ConfigEntryAuthFailed from err
        raise ConfigEntryNotReady from err
    except (asyncio.TimeoutError, TimeoutError) as err:
        raise ConfigEntryNotReady from err

    _LOGGER.debug("%s hub has started", hub.server_name)

    new_options = {
        CONF_CACHE_SERVER_NAME: hub.server_name,
        CONF_CACHE_SERVER_ID: hub.server_id,
        CONF_CACHE_SERVER_PING: hub.server_ping,
        CONF_CACHE_SERVER_VERSION: hub.server_version,
        CONF_CACHE_SERVER_API_KEY: hub.api_key,
        CONF_CACHE_SERVER_USER_ID: hub.user_id,
    }

    hass.config_entries.async_update_entry(entry, options=entry.options | new_options)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = dict(entry.data)
    hass.data[DOMAIN][entry.entry_id][DATA_HUB] = hub

    # Register purge devices service
    async def async_purge_devices(call) -> None:
        """Service to purge orphaned devices."""
        import homeassistant.helpers.entity_registry as entreg
        import homeassistant.helpers.device_registry as devreg

        entity_registry = entreg.async_get(hass)
        device_registry = devreg.async_get(hass)

        # Get all devices for this integration
        devices = devreg.async_entries_for_config_entry(device_registry, entry.entry_id)

        # Get current active sessions
        sessions = await hub.async_get_last_sessions()
        active_session_ids = {session["Id"] for session in sessions}

        purged_count = 0
        for device in devices:
            # Skip the main server device
            if device.via_device is None:
                continue

            # Extract session ID from device identifiers
            for domain_id, session_id in device.identifiers:
                if domain_id == DOMAIN and session_id not in active_session_ids:
                    _LOGGER.info("Purging orphaned device %s (session: %s)", device.name, session_id)
                    device_registry.async_remove_device(device.id)
                    purged_count += 1
                    break

        _LOGGER.info("Purged %d orphaned devices", purged_count)

    hass.services.async_register(
        DOMAIN, SERVICE_PURGE_DEVICES, async_purge_devices
    )

    entry.async_on_unload(entry.add_update_listener(async_options_update_listener))
    entry.async_on_unload(hub.on_websocket_message(async_websocket_message))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        hub: MediaBrowserHub = data[DATA_HUB]
        await hub.async_stop()

        # Unregister services if this is the last config entry
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_PURGE_DEVICES)

    return unload_ok


async def async_options_update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)
