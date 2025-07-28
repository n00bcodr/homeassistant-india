"""Support for Jellyfin sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jellyfin sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = []
    for sensor_type in SENSOR_TYPES:
        entities.append(JellyfinSensor(coordinator, sensor_type, config_entry))

    # Add upcoming media sensor for upcoming-media-card
    entities.append(JellyfinUpcomingSensor(coordinator, config_entry))

    async_add_entities(entities)


class JellyfinSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Jellyfin sensor."""

    def __init__(self, coordinator, sensor_type: str, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._config_entry = config_entry

        sensor_config = SENSOR_TYPES[sensor_type]
        self._attr_name = f"Jellyfin {sensor_config['name']}"
        self._attr_icon = sensor_config["icon"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_device_class = sensor_config["device_class"]

        # Set entity category to None (default) so it appears in Sensors section
        self._attr_entity_category = None

        # Unique ID
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        data = self.coordinator.data

        if self._sensor_type == "server_status":
            system_info = data.get("system_info", {})
            return "Online" if system_info else "Offline"

        elif self._sensor_type == "active_sessions":
            sessions = data.get("sessions", [])
            return len(sessions)

        elif self._sensor_type in ["movies", "shows", "episodes", "music"]:
            library_stats = data.get("library_stats", {})
            return library_stats.get(self._sensor_type, 0)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        data = self.coordinator.data
        attributes = {}

        if self._sensor_type == "server_status":
            system_info = data.get("system_info", {})
            attributes.update({
                "server_name": system_info.get("ServerName"),
                "server_id": system_info.get("Id"),
                "version": system_info.get("Version"),
                "operating_system": system_info.get("OperatingSystem"),
            })

        elif self._sensor_type == "active_sessions":
            sessions = data.get("sessions", [])
            system_info = data.get("system_info", {})

            attributes.update({
                "server_name": system_info.get("ServerName"),
                "server_id": system_info.get("Id"),
                "total_sessions": len(sessions),
            })

            session_list = []
            for session in sessions:
                session_info = {
                    "user_name": session.get("UserName", "Unknown"),
                    "client": session.get("Client", "Unknown"),
                    "device_name": session.get("DeviceName", "Unknown"),
                    "device_id": session.get("DeviceId", ""),
                    "application_version": session.get("ApplicationVersion", ""),
                    "remote_end_point": session.get("RemoteEndPoint", ""),
                    "supports_remote_control": session.get("SupportsRemoteControl", False),
                    "last_activity_date": session.get("LastActivityDate", ""),
                }

                if session.get("NowPlayingItem"):
                    now_playing = session["NowPlayingItem"]
                    session_info.update({
                        "media_type": now_playing.get("Type"),
                        "media_title": now_playing.get("Name"),
                        "media_series": now_playing.get("SeriesName"),
                    })

                session_list.append(session_info)

            attributes["sessions"] = session_list

        # Add latest items as an attribute to the corresponding sensor
        elif self._sensor_type == "movies":
            attributes["latest"] = data.get("latest_movies", [])
        elif self._sensor_type == "episodes":
            attributes["latest"] = data.get("latest_episodes", [])
        elif self._sensor_type == "music":
            attributes["latest"] = data.get("latest_music", [])

        return attributes

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


class JellyfinUpcomingSensor(CoordinatorEntity, SensorEntity):
    """Sensor for upcoming media data for upcoming-media-card."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the upcoming media sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry

        self._attr_name = "Jellyfin Upcoming Media"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_unique_id = f"{config_entry.entry_id}_upcoming_media"
        self._attr_entity_category = None

    @property
    def native_value(self) -> int:
        """Return the number of upcoming items."""
        if not self.coordinator.data or "upcoming_media" not in self.coordinator.data:
            return 0
        return len(self.coordinator.data["upcoming_media"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return upcoming media data for upcoming-media-card."""
        if not self.coordinator.data or "upcoming_media" not in self.coordinator.data:
            return {"data": []}

        # Return the formatted data directly from the API
        return {"data": self.coordinator.data["upcoming_media"]}

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