"""Constants for the Jellyfin integration."""
from homeassistant.components.media_player import MediaType
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform

DOMAIN = "jellyfin"

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.BUTTON,
]

# State mappings
JELLYFIN_STATE_MAPPING = {
    "Playing": "playing",
    "Paused": "paused",
    "Stopped": "idle",
}

MEDIA_TYPE_MAPPING = {
    "Movie": MediaType.MOVIE,
    "Episode": MediaType.TVSHOW,
    "Audio": MediaType.MUSIC,
    "Video": MediaType.VIDEO,
}

# Sensor configurations
SENSOR_TYPES = {
    "server_status": {
        "name": "Server Status",
        "icon": "mdi:server",
        "unit": None,
        "device_class": None,
    },
    "active_sessions": {
        "name": "Active Sessions",
        "icon": "mdi:play-circle-outline",
        "unit": "sessions",
        "device_class": None,
    },
    "movies": {
        "name": "Movies",
        "icon": "mdi:movie-roll",
        "unit": "items",
        "device_class": None,
    },
    "shows": {
        "name": "TV Shows",
        "icon": "mdi:television-classic",
        "unit": "items",
        "device_class": None,
    },
    "episodes": {
        "name": "Episodes",
        "icon": "mdi:television",
        "unit": "items",
        "device_class": None,
    },
    "music": {
        "name": "Music",
        "icon": "mdi:music-note",
        "unit": "items",
        "device_class": None,
    },
}