"""The Jellyfin integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .jellyfin_api import JellyfinAPI

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=2)  # Faster updates for better responsiveness


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Jellyfin from a config entry."""
    session = async_get_clientsession(hass)

    api = JellyfinAPI(
        session,
        entry.data["host"],
        entry.data["api_key"],
        entry.data.get("port", 8096),
        entry.data.get("use_ssl", False)
    )

    # Test the connection
    try:
        await api.get_system_info()
    except Exception as err:
        _LOGGER.error("Failed to connect to Jellyfin server: %s", err)
        raise ConfigEntryNotReady from err

    coordinator = JellyfinDataUpdateCoordinator(hass, api)

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await _async_register_services(hass, entry)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def _async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register Jellyfin services."""

    async def handle_broadcast_message(call: ServiceCall) -> None:
        """Handle send message to all active media players service call."""
        message = call.data.get("message", "")
        header = call.data.get("header", "Home Assistant")
        timeout = call.data.get("timeout", 5000)

        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        api = hass.data[DOMAIN][entry.entry_id]["api"]

        if not coordinator.data or "sessions" not in coordinator.data:
            _LOGGER.warning("No active sessions found")
            return

        sessions = coordinator.data["sessions"]
        sent_count = 0

        for session in sessions:
            if session.get("NowPlayingItem"):  # Only send to active sessions
                session_id = session.get("Id")
                if session_id:
                    try:
                        await api.send_message_to_session(session_id, message, header, timeout)
                        sent_count += 1
                    except Exception as err:
                        _LOGGER.error("Failed to send message to session %s: %s", session_id, err)

        _LOGGER.info("Message sent to %d active media players", sent_count)

    # Register services

    hass.services.async_register(
        DOMAIN, "broadcast_message", handle_broadcast_message
    )


async def _cleanup_unavailable_media_players(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove unavailable media player entities."""
    entity_registry = er.async_get(hass)

    # Get all entities for this integration
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)

    # Filter media player entities
    media_player_entities = [
        entity for entity in entities
        if entity.domain == "media_player" and entity.platform == DOMAIN
    ]

    # Get current active sessions
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    active_session_ids = set()

    if coordinator.data and "sessions" in coordinator.data:
        for session in coordinator.data["sessions"]:
            if session.get("NowPlayingItem"):
                session_id = session.get("Id")
                if session_id:
                    active_session_ids.add(f"{entry.entry_id}_{session_id}")

    # Remove entities that are no longer active
    removed_count = 0
    for entity in media_player_entities:
        if entity.unique_id not in active_session_ids:
            entity_registry.async_remove(entity.entity_id)
            removed_count += 1
            _LOGGER.debug("Removed unavailable media player: %s", entity.entity_id)

    _LOGGER.info("Removed %d unavailable media player entities", removed_count)


class JellyfinDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, api: JellyfinAPI) -> None:
        """Initialize."""
        self.api = api
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self):
        """Update data via library."""
        try:
            async with async_timeout.timeout(10):
                data = {}

                # Get system info
                data["system_info"] = await self.api.get_system_info()

                # Get active sessions (only those with active playback)
                all_sessions = await self.api.get_sessions()
                data["sessions"] = [
                    session for session in all_sessions
                    if session.get("NowPlayingItem")
                ]

                # Get library stats
                data["library_stats"] = await self.api.get_library_stats()

                # Get users for reference
                data["users"] = await self.api.get_users()

                # Get upcoming media for upcoming-media-card
                data["upcoming_media"] = await self.api.get_upcoming_media()

                # Get latest media items (last 30)
                data["latest_movies"] = await self.api.get_latest_media("Movie", 30)
                data["latest_episodes"] = await self.api.get_latest_media("Episode", 30)
                data["latest_music"] = await self.api.get_latest_media("Audio", 30)

                return data

        except Exception as exception:
            raise UpdateFailed(f"Error communicating with API: {exception}") from exception