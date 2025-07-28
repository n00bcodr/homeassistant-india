"""Support for Jellyfin buttons."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .jellyfin_api import JellyfinAPI

_LOGGER = logging.getLogger(__name__)

BUTTON_TYPES = {
    "rescan_library": {"name": "Rescan Library", "icon": "mdi:magnify-scan"},
    "restart_server": {"name": "Restart Server", "icon": "mdi:restart"},
    "shutdown_server": {"name": "Shutdown Server", "icon": "mdi:power"},
    "cleanup_unavailable": {"name": "Cleanup Unavailable Media Players", "icon": "mdi:delete-sweep"},
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jellyfin buttons based on a config entry."""
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = [
        JellyfinServiceButton(coordinator, api, config_entry, button_type)
        for button_type in BUTTON_TYPES
    ]
    async_add_entities(entities)

class JellyfinServiceButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Jellyfin service button."""

    def __init__(self, coordinator, api: JellyfinAPI, config_entry: ConfigEntry, button_type: str) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._api = api
        self._config_entry = config_entry
        self._button_type = button_type

        button_config = BUTTON_TYPES[button_type]
        self._attr_name = f"Jellyfin {button_config['name']}"
        self._attr_icon = button_config["icon"]
        self._attr_unique_id = f"{config_entry.entry_id}_{button_type}"

        # Set entity category to CONFIG so it appears in Configuration section
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            if self._button_type == "rescan_library":
                await self._api.rescan_library()
                _LOGGER.info("Library rescan initiated")
            elif self._button_type == "restart_server":
                await self._api.restart_server()
                _LOGGER.info("Server restart initiated")
            elif self._button_type == "shutdown_server":
                await self._api.shutdown_server()
                _LOGGER.info("Server shutdown initiated")
            elif self._button_type == "cleanup_unavailable":
                await self._cleanup_unavailable_media_players()
                _LOGGER.info("Cleanup of unavailable media players completed")

        except Exception as err:
            _LOGGER.error("Failed to execute %s: %s", self._button_type, err)

    async def _cleanup_unavailable_media_players(self) -> None:
        """Remove unavailable media player entities."""
        entity_registry = er.async_get(self.hass)

        entities = er.async_entries_for_config_entry(entity_registry, self._config_entry.entry_id)

        media_player_entities = [
            entity for entity in entities
            if entity.domain == "media_player" and entity.platform == DOMAIN
        ]

        active_session_ids = set()
        if self.coordinator.data and "sessions" in self.coordinator.data:
            for session in self.coordinator.data["sessions"]:
                if session.get("NowPlayingItem"):
                    session_id = session.get("Id")
                    if session_id:
                        active_session_ids.add(f"{self._config_entry.entry_id}_{session_id}")

        removed_count = 0
        for entity in media_player_entities:
            if entity.unique_id not in active_session_ids:
                entity_registry.async_remove(entity.entity_id)
                removed_count += 1
                _LOGGER.debug("Removed unavailable media player: %s", entity.entity_id)

        _LOGGER.info("Removed %d unavailable media player entities", removed_count)

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        system_info = self.coordinator.data.get("system_info", {}) if self.coordinator.data else {}

        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": f"Jellyfin Server ({system_info.get('ServerName', 'Unknown')})",
            "manufacturer": "Jellyfin",
            "model": "Media Server",
            "sw_version": system_info.get("Version"),
        }