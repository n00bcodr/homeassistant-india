"""Support for Jellyfin media players."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, JELLYFIN_STATE_MAPPING, MEDIA_TYPE_MAPPING

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jellyfin media player based on a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]

    # Track existing entities to avoid duplicates
    existing_entities = set()

    def add_new_entities():
        """Add new media player entities for active sessions."""
        if not coordinator.data or "sessions" not in coordinator.data:
            return

        entities = []
        sessions = coordinator.data["sessions"]

        for session in sessions:
            # Only create entities for sessions with active playback
            if not session.get("NowPlayingItem"):
                continue

            session_id = session.get("Id")
            if session_id and session_id not in existing_entities:
                entities.append(JellyfinMediaPlayer(coordinator, api, session, config_entry))
                existing_entities.add(session_id)

        if entities:
            async_add_entities(entities)

    # Add initial entities
    add_new_entities()

    # Set up listener for new sessions
    coordinator.async_add_listener(add_new_entities)


class JellyfinMediaPlayer(CoordinatorEntity, MediaPlayerEntity):
    """Representation of a Jellyfin media player."""

    def __init__(self, coordinator, api, session: dict, config_entry: ConfigEntry) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)
        self._api = api
        self._session_id = session.get("Id")
        self._config_entry = config_entry
        self._session = None

        # Use device name instead of username
        device_name = session.get("DeviceName", "Unknown Device")
        client_name = session.get("Client", "")

        self._attr_name = f"Jellyfin {device_name}"
        if client_name and client_name != device_name:
            self._attr_name += f" ({client_name})"

        self._attr_unique_id = f"{config_entry.entry_id}_{self._session_id}"

        # Set entity category to None (default) so it appears in Media Players section
        self._attr_entity_category = None

        # Supported features
        self._attr_supported_features = (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.SEEK
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
        )

    def _update_session(self) -> None:
        """Update the current session data."""
        if not self.coordinator.data or "sessions" not in self.coordinator.data:
            self._session = None
            return

        sessions = self.coordinator.data["sessions"]
        for session in sessions:
            if session.get("Id") == self._session_id:
                self._session = session
                return

        self._session = None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        self._update_session()
        return self._session is not None

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the media player."""
        self._update_session()

        if not self._session or not self._session.get("NowPlayingItem"):
            return MediaPlayerState.IDLE

        play_state = self._session.get("PlayState", {})

        if play_state.get("IsPaused"):
            return MediaPlayerState.PAUSED
        elif self._session.get("NowPlayingItem"):
            return MediaPlayerState.PLAYING
        else:
            return MediaPlayerState.IDLE

    @property
    def media_content_type(self) -> str | None:
        """Return the content type of current playing media."""
        if not self._session or not self._session.get("NowPlayingItem"):
            return None

        item_type = self._session["NowPlayingItem"].get("Type")
        return MEDIA_TYPE_MAPPING.get(item_type, MediaType.VIDEO)

    @property
    def media_title(self) -> str | None:
        """Return the title of current playing media."""
        if not self._session or not self._session.get("NowPlayingItem"):
            return None

        return self._session["NowPlayingItem"].get("Name")

    @property
    def media_artist(self) -> str | None:
        """Return the artist of current playing media."""
        if not self._session or not self._session.get("NowPlayingItem"):
            return None

        item = self._session["NowPlayingItem"]

        # For music
        if item.get("Type") == "Audio":
            artists = item.get("ArtistItems", [])
            if artists:
                return ", ".join([artist["Name"] for artist in artists])
            return item.get("AlbumArtist")

        return None

    @property
    def media_series_title(self) -> str | None:
        """Return the series title of current playing media."""
        if not self._session or not self._session.get("NowPlayingItem"):
            return None

        item = self._session["NowPlayingItem"]

        # For TV shows
        if item.get("Type") == "Episode":
            return item.get("SeriesName")

        return None

    @property
    def media_album_name(self) -> str | None:
        """Return the album name of current playing media."""
        if not self._session or not self._session.get("NowPlayingItem"):
            return None

        item = self._session["NowPlayingItem"]
        if item.get("Type") == "Audio":
            return item.get("Album")

        return None

    @property
    def media_season(self) -> str | None:
        """Return the season of current playing media."""
        if not self._session or not self._session.get("NowPlayingItem"):
            return None

        item = self._session["NowPlayingItem"]
        if item.get("Type") == "Episode":
            return item.get("ParentIndexNumber")

        return None

    @property
    def media_episode(self) -> str | None:
        """Return the episode of current playing media."""
        if not self._session or not self._session.get("NowPlayingItem"):
            return None

        item = self._session["NowPlayingItem"]
        if item.get("Type") == "Episode":
            return item.get("IndexNumber")

        return None

    @property
    def media_duration(self) -> int | None:
        """Return the duration of current playing media in seconds."""
        if not self._session or not self._session.get("NowPlayingItem"):
            return None

        runtime_ticks = self._session["NowPlayingItem"].get("RunTimeTicks")
        if runtime_ticks:
            return int(runtime_ticks / 10000000)  # Convert from ticks to seconds

        return None

    @property
    def media_position(self) -> int | None:
        """Return the position of current playing media in seconds."""
        if not self._session:
            return None

        play_state = self._session.get("PlayState", {})
        position_ticks = play_state.get("PositionTicks")

        if position_ticks:
            return int(position_ticks / 10000000)  # Convert from ticks to seconds

        return None

    @property
    def media_image_url(self) -> str | None:
        """Return the image URL of current playing media."""
        if not self._session or not self._session.get("NowPlayingItem"):
            return None

        item = self._session["NowPlayingItem"]
        item_id = item.get("Id")

        if item_id:
            return self._api.get_image_url(item_id)

        return None

    @property
    def volume_level(self) -> float | None:
        """Return the volume level of the media player (0..1)."""
        if not self._session:
            return None

        play_state = self._session.get("PlayState", {})
        volume = play_state.get("VolumeLevel")

        if volume is not None:
            return volume / 100.0

        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Return boolean if volume is currently muted."""
        if not self._session:
            return None

        play_state = self._session.get("PlayState", {})
        return play_state.get("IsMuted", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self._session:
            return {}

        attributes = {}

        # Session info
        attributes["session_id"] = self._session.get("Id")
        attributes["client"] = self._session.get("Client")
        attributes["device_name"] = self._session.get("DeviceName")
        attributes["user_name"] = self._session.get("UserName")

        # Now playing item details
        if self._session.get("NowPlayingItem"):
            item = self._session["NowPlayingItem"]
            attributes["media_type"] = item.get("Type")
            attributes["production_year"] = item.get("ProductionYear")
            attributes["community_rating"] = item.get("CommunityRating")
            attributes["official_rating"] = item.get("OfficialRating")

            # For episodes
            if item.get("Type") == "Episode":
                attributes["series_name"] = item.get("SeriesName")
                attributes["season_number"] = item.get("ParentIndexNumber")
                attributes["episode_number"] = item.get("IndexNumber")

        return attributes

    async def _execute_command_with_retry(self, command_func, *args, **kwargs):
        """Execute a command with immediate refresh and retry logic."""
        try:
            # Execute the command
            await command_func(*args, **kwargs)

            # Small delay to allow Jellyfin to process the command
            await asyncio.sleep(0.1)

            # Force immediate refresh
            await self.coordinator.async_request_refresh()

            # Additional refresh after a short delay for better responsiveness
            await asyncio.sleep(0.5)
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Failed to execute command: %s", err)
            raise

    async def async_media_play(self) -> None:
        """Send play command."""
        if self._session:
            await self._execute_command_with_retry(self._api.play_pause, self._session["Id"])

    async def async_media_pause(self) -> None:
        """Send pause command."""
        if self._session:
            await self._execute_command_with_retry(self._api.play_pause, self._session["Id"])

    async def async_media_stop(self) -> None:
        """Send stop command."""
        if self._session:
            await self._execute_command_with_retry(self._api.stop, self._session["Id"])

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        if self._session:
            await self._execute_command_with_retry(self._api.next_track, self._session["Id"])

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        if self._session:
            await self._execute_command_with_retry(self._api.previous_track, self._session["Id"])

    async def async_media_seek(self, position: float) -> None:
        """Send seek command."""
        if self._session:
            position_ticks = int(position * 10000000)  # Convert seconds to ticks
            await self._execute_command_with_retry(self._api.seek, self._session["Id"], position_ticks)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        if self._session:
            volume_percent = int(volume * 100)
            await self._execute_command_with_retry(self._api.set_volume, self._session["Id"], volume_percent)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        if self._session:
            await self._execute_command_with_retry(self._api.mute, self._session["Id"], mute)

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