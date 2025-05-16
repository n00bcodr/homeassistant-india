"""Media Player for the Media Browser (Emby/Jellyfin) integration."""

import json
import logging
from datetime import datetime
from typing import Any, Callable

import homeassistant.helpers.entity_registry as entreg
import homeassistant.util.dt as utildt
import voluptuous as vol

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.components.media_player.browse_media import BrowseMedia
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    async_get_current_platform,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import HomeAssistant
from .hub import MediaBrowserHub

from .browse_media import async_browse_media_id
from .const import (
    CONF_PURGE_PLAYERS,
    DATA_HUB,
    DOMAIN,
    MANUFACTURER_MAP,
    MEDIA_TYPE_MAP,
    SERVICE_SEND_COMMAND,
    SERVICE_SEND_MESSAGE,
    TICKS_PER_SECOND,
    EntityType,
    ImageType,
    Item,
    Manufacturer,
    PlayState,
    Response,
    Session,
)

from .entity import MediaBrowserEntity
from .errors import NotFoundError # Assuming errors.py exists
from .helpers import (
    camel_cased_json,
    extract_player_key,
    get_image_url,
    as_float,
    as_int,
)

VOLUME_RATIO = 100
_LOGGER = logging.getLogger(__package__)


COMMAND_MB_TO_HA: dict[str, int] = {
    "Mute": MediaPlayerEntityFeature.VOLUME_MUTE,
    "Unmute": MediaPlayerEntityFeature.VOLUME_MUTE,
    "ToggleMute": MediaPlayerEntityFeature.VOLUME_MUTE,
    "SetVolume": MediaPlayerEntityFeature.VOLUME_SET,
    "VolumeSet": MediaPlayerEntityFeature.VOLUME_SET, # Added for consistency if server sends this
    "VolumeUp": MediaPlayerEntityFeature.VOLUME_STEP,
    "VolumeDown": MediaPlayerEntityFeature.VOLUME_STEP,
    "SetRepeatMode": MediaPlayerEntityFeature.REPEAT_SET,
    # Add other commands mapped to features if needed
    "Play": MediaPlayerEntityFeature.PLAY,
    "Pause": MediaPlayerEntityFeature.PAUSE,
    "Unpause": MediaPlayerEntityFeature.PLAY, # Unpause maps to PLAY feature
    "PlayPause": MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE,
    "Stop": MediaPlayerEntityFeature.STOP,
    "NextTrack": MediaPlayerEntityFeature.NEXT_TRACK,
    "PreviousTrack": MediaPlayerEntityFeature.PREVIOUS_TRACK,
    "Seek": MediaPlayerEntityFeature.SEEK,
}

REPEAT_HA_TO_MB = {
    RepeatMode.OFF: "RepeatNone",
    RepeatMode.ONE: "RepeatOne",
    RepeatMode.ALL: "RepeatAll",
}


REPEAT_MB_TO_HA = {v: k for k, v in REPEAT_HA_TO_MB.items()}

spawned_players: set[str] = set()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sets up media players from a config entry."""

    hub: MediaBrowserHub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]

    platform = async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SEND_MESSAGE,
        {
            vol.Required("text"): cv.string,
            vol.Required("header"): cv.string,
            vol.Optional("timeout"): cv.Number,
        },  # type: ignore
        "async_send_message",
    )

    platform.async_register_entity_service(
        SERVICE_SEND_COMMAND,
        {
            vol.Required("command"): cv.string,
            vol.Optional("arguments"): cv.Any,
        },  # type: ignore
        "async_send_command",
    )

    async def session_changed(
        old_session: dict[str, Any] | None, new_session: dict[str, Any] | None
    ):
        """Handle session additions and removals."""
        # Add new player
        if old_session is None and new_session is not None:
            session_id = new_session.get(Session.ID)
            if session_id and session_id not in spawned_players:
                _LOGGER.debug("Adding new media player for session %s", session_id)
                async_add_entities([MediaBrowserPlayer(hub, new_session)])
                spawned_players.add(session_id)

        # Remove player if configured
        if (
            new_session is None
            and old_session is not None
            and entry.options.get(CONF_PURGE_PLAYERS, False) # Check option correctly
        ):
            session_id_to_remove = old_session.get(Session.ID)
            if not session_id_to_remove:
                return

            entity_registry = entreg.async_get(hass)
            # Construct the expected unique_id suffix
            unique_id_suffix = f"-{session_id_to_remove}-{EntityType.PLAYER}"

            player_entity = next(
                (
                    entity
                    for entity in entreg.async_entries_for_config_entry(
                        entity_registry, entry.entry_id
                    )
                    # Ensure unique_id exists and check suffix correctly
                    if entity.unique_id and entity.unique_id.endswith(unique_id_suffix)
                ),
                None,
            )

            if player_entity:
                _LOGGER.debug("Purging media player %s for session %s", player_entity.entity_id, session_id_to_remove)
                spawned_players.discard(session_id_to_remove)
                entity_registry.async_remove(player_entity.entity_id)
            else:
                 _LOGGER.debug("Could not find entity to purge for session %s", session_id_to_remove)


    # Initial setup: Add players for existing sessions
    try:
        sessions = await hub.async_get_last_sessions()
        new_entities = []
        for session in sessions:
             session_id = session.get(Session.ID)
             if session_id and session_id not in spawned_players:
                 new_entities.append(MediaBrowserPlayer(hub, session))
                 spawned_players.add(session_id)
        if new_entities:
            async_add_entities(new_entities)
    except Exception as e:
         _LOGGER.error("Error fetching initial sessions: %s", e)


    # Register listener for future changes
    entry.async_on_unload(hub.on_session_changed(session_changed))


class MediaBrowserPlayer(MediaBrowserEntity, MediaPlayerEntity):
    """Represents a media player entity."""

    def __init__(self, hub: MediaBrowserHub, session: dict[str, Any]) -> None:
        """Initialize the media player."""
        super().__init__(hub)
        self._session_key: str = session[Session.ID] # Assume ID is always present from setup logic
        self._device_name: str | None = session.get(Session.DEVICE_NAME)
        self._device_version = session.get(Session.APPLICATION_VERSION)
        self._device_model: str | None = session.get(Session.CLIENT)

        self._session: dict[str, Any] | None = session # Store initial session data
        self._last_update: datetime | None = utildt.utcnow() # Set initial update time

        self._availability_unlistener: Callable[[], None] | None = None
        self._session_changed_unlistener: Callable[[], None] | None = None

        # Set initial attributes based on the first session data
        self._attr_name = f"{self.hub.name} {self._session.get(Session.DEVICE_NAME, 'Unknown Device')}"
        self._attr_unique_id = (
            f"{self.hub.server_id}-{self._session_key}-{EntityType.PLAYER}"
        )
        self._attr_media_image_remotely_accessible = True # Assume images are accessible via HA proxy/server URL
        self._attr_available = hub.is_available
        self._update_from_data() # Populate attributes from initial session

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self._availability_unlistener = self.hub.on_availability_changed(
            self._async_availability_changed
        )
        self._session_changed_unlistener = self.hub.on_session_changed(
            self._async_session_changed
        )
        _LOGGER.debug("%s: Added to HASS", self.entity_id)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._availability_unlistener is not None:
            self._availability_unlistener()
        if self._session_changed_unlistener is not None:
            self._session_changed_unlistener()

        self._availability_unlistener = None
        self._session_changed_unlistener = None
        _LOGGER.debug("%s: Removed from HASS", self.entity_id)


    async def _async_availability_changed(self, availability: bool) -> None:
        """Handle hub availability changes."""
        _LOGGER.debug("%s: Availability changed to %s", self.entity_id, availability)
        self._attr_available = availability
        # If becoming unavailable, maybe clear session data?
        # if not availability:
        #     self._session = None
        #     self._update_from_data() # Update state to OFF/UNAVAILABLE
        self.async_write_ha_state()

    async def _async_session_changed(
        self, old_session: dict[str, Any] | None, new_session: dict[str, Any] | None
    ) -> None:
        """Handle individual session updates from the hub."""
        # Check if the change is relevant to this entity's session key
        relevant_session_key = None
        if new_session and new_session.get(Session.ID) == self._session_key:
            relevant_session_key = self._session_key
            self._session = new_session # Update with new data
            self._last_update = utildt.utcnow()
            # Update device info potentially
            self._device_name = new_session.get(Session.DEVICE_NAME)
            self._device_version = new_session.get(Session.APPLICATION_VERSION)
            self._device_model = new_session.get(Session.CLIENT)
            _LOGGER.debug("%s: Session updated", self.entity_id)

        elif old_session and old_session.get(Session.ID) == self._session_key and new_session is None:
            # Session was removed (and not purged immediately by setup_entry)
            relevant_session_key = self._session_key
            self._session = None # Clear session data
            _LOGGER.debug("%s: Session removed", self.entity_id)

        # If the change was relevant, update state
        if relevant_session_key:
            self._update_from_data()
            self.async_write_ha_state()


    def _update_init(self) -> None:
        """Initialize all media player attributes to default/None."""
        self._attr_extra_state_attributes = {}
        self._attr_media_album_artist = None
        self._attr_media_album_name = None
        self._attr_media_artist = None
        self._attr_media_channel = None
        self._attr_media_content_id = None
        self._attr_media_content_type = None
        self._attr_media_duration = None
        self._attr_media_episode = None
        self._attr_media_position = None
        self._attr_media_season = None
        self._attr_media_series_title = None
        self._attr_media_title = None
        self._attr_media_image_url = None
        self._attr_media_position_updated_at = None
        self._attr_app_id = None
        self._attr_app_name = None
        self._attr_repeat = RepeatMode.OFF # Default repeat mode
        self._attr_is_volume_muted = None
        self._attr_volume_level = None
        self._attr_supported_features = MediaPlayerEntityFeature(0) # Start with no features
        self._attr_state = MediaPlayerState.OFF # Default state

    def _update_from_state(self, play_state: dict[str, Any]) -> None:
        """Update attributes based on the PlayState dictionary."""
        self._attr_repeat = REPEAT_MB_TO_HA.get(
            play_state.get(PlayState.REPEAT_MODE, ""), RepeatMode.OFF # Default if key missing/invalid
        )
        self._attr_is_volume_muted = play_state.get(PlayState.IS_MUTED)

        if (ticks := as_int(play_state, PlayState.POSITION_TICKS)) is not None: # Check for None explicitly
            self._attr_media_position = ticks // TICKS_PER_SECOND
            # Use the last update time from the session change
            self._attr_media_position_updated_at = self._last_update
        else:
             self._attr_media_position = None
             self._attr_media_position_updated_at = None


        if (level := as_float(play_state, PlayState.VOLUME_LEVEL)) is not None: # Check for None
            self._attr_volume_level = max(0.0, min(1.0, level / VOLUME_RATIO)) # Clamp between 0 and 1
        else:
             self._attr_volume_level = None # Explicitly set to None if not present


    def _update_from_item(self, item: dict[str, Any]) -> None:
        """Update attributes based on the NowPlayingItem dictionary."""
        self._attr_media_album_artist = item.get(Item.ALBUM_ARTIST)
        self._attr_media_album_name = item.get(Item.ALBUM)
        if artists := item.get(Item.ARTISTS):
            self._attr_media_artist = ", ".join(artists) # Join multiple artists
        else:
             self._attr_media_artist = None

        self._attr_media_channel = item.get(Item.CHANNEL_NAME)
        self._attr_media_content_id = item.get(Item.ID)
        if content_type := item.get(Item.TYPE):
            # Default to MUSIC if not specifically mapped
            self._attr_media_content_type = MEDIA_TYPE_MAP.get(
                content_type, MediaType.MUSIC
            )
        else:
             self._attr_media_content_type = None

        if (ticks := as_int(item, Item.RUNTIME_TICKS)) is not None:
            self._attr_media_duration = ticks // TICKS_PER_SECOND
        else:
             self._attr_media_duration = None

        # Combine series/season/episode info for title if it's an episode
        item_type = item.get(Item.TYPE)
        if item_type == "Episode":
            series_title = item.get(Item.SERIES_NAME, '')
            season_number = item.get(Item.PARENT_INDEX_NUMBER) # Season number
            episode_number = item.get(Item.INDEX_NUMBER) # Episode number
            episode_title = item.get(Item.NAME, 'Unknown Title')

            title_parts = []
            if series_title: title_parts.append(series_title)
            if season_number is not None and episode_number is not None:
                 title_parts.append(f"S{season_number:02}E{episode_number:02}")
            title_parts.append(episode_title)
            self._attr_media_title = " - ".join(filter(None, title_parts)) # Join parts with " - "

            # Set specific episode attributes
            self._attr_media_series_title = series_title
            self._attr_media_season = str(season_number) if season_number is not None else None
            self._attr_media_episode = str(episode_number) if episode_number is not None else None

        else:
            # For other types, use the item name as the title
            self._attr_media_title = item.get(Item.NAME, "Unknown Title")
            self._attr_media_series_title = item.get(Item.SERIES_NAME) # Might still exist for movies in collections
            self._attr_media_season = item.get(Item.SEASON_NAME) # Might exist for music albums etc.
            self._attr_media_episode = None # Not an episode

        # Get image URL (prefer primary, fallback to backdrop)
        self._attr_media_image_url = get_image_url(
            item, self.hub.server_url, ImageType.PRIMARY # Prefer Primary image
        ) or get_image_url(
            item, self.hub.server_url, ImageType.BACKDROP # Fallback to Backdrop
        )


    def _update_from_session(self, session: dict[str, Any]) -> None:
        """Update attributes based on the main Session dictionary."""
        self._attr_state = MediaPlayerState.IDLE # Default to IDLE if session exists
        remote_control: bool = session.get(Session.SUPPORTS_REMOTE_CONTROL, False)

        self._attr_app_id = session.get(Session.ID) # Should always be the same as _session_key
        self._attr_app_name = session.get(Session.CLIENT)

        # --- Base Features ---
        if remote_control:
            self._attr_supported_features |= (
                MediaPlayerEntityFeature.BROWSE_MEDIA
                | MediaPlayerEntityFeature.PLAY_MEDIA
                | MediaPlayerEntityFeature.PAUSE # Assume possible if remote controlled
                | MediaPlayerEntityFeature.STOP # Assume possible if remote controlled
                | MediaPlayerEntityFeature.PLAY # Assume possible if remote controlled
            )

        # --- Features based on SupportedCommands ---
        if commands := session.get(Session.SUPPORTED_COMMANDS):
            for command in commands:
                # Map command to HA features
                self._attr_supported_features |= COMMAND_MB_TO_HA.get(command, 0)

        # --- Features based on Playlist ---
        play_index = session.get(Session.PLAYLIST_INDEX)
        play_length = session.get(Session.PLAYLIST_LENGTH)
        if play_index is not None and play_length is not None:
            if play_index > 0:
                self._attr_supported_features |= MediaPlayerEntityFeature.PREVIOUS_TRACK
            if play_index < play_length - 1:
                self._attr_supported_features |= MediaPlayerEntityFeature.NEXT_TRACK

        # --- Update based on NowPlayingItem ---
        if item := session.get(Session.NOW_PLAYING_ITEM):
            self._update_from_item(item)
            self._attr_state = MediaPlayerState.PLAYING # If something is playing, state is PLAYING
        else:
            # Clear media info if nothing is playing
             self._attr_media_title = None
             self._attr_media_artist = None
             # ... clear other media attributes ...
             self._attr_media_content_id = None
             self._attr_media_content_type = None
             self._attr_media_duration = None
             self._attr_media_image_url = None
             self._attr_media_position = None
             self._attr_media_position_updated_at = None
             # State remains IDLE or becomes OFF later if session disappears

        # --- Update based on PlayState (overrides state if paused/seeking etc.) ---
        if play_state := session.get(Session.PLAY_STATE):
            self._update_from_state(play_state) # Updates volume, mute, position, repeat
            # Add SEEK feature if CanSeek is true
            if play_state.get(PlayState.CAN_SEEK):
                self._attr_supported_features |= MediaPlayerEntityFeature.SEEK
            # If paused, override state to PAUSED
            if play_state.get(PlayState.IS_PAUSED) and self._attr_state == MediaPlayerState.PLAYING:
                self._attr_state = MediaPlayerState.PAUSED
        else:
             # If no PlayState, clear related attributes
             self._attr_media_position = None
             self._attr_media_position_updated_at = None
             self._attr_is_volume_muted = None # Or False? Depends on desired default
             self._attr_volume_level = None # Or 0? Depends on desired default
             self._attr_repeat = RepeatMode.OFF


        # Final state check: If session exists but nothing playing/paused, it's IDLE (unless remote_control is false?)
        if self._attr_state not in (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED):
             self._attr_state = MediaPlayerState.IDLE if remote_control else MediaPlayerState.OFF


    def _update_from_data(self) -> None:
        """Update all attributes based on the current self._session data."""
        self._update_init() # Reset all attributes
        if self._session is not None:
            self._update_from_session(self._session)
            # Add raw session data to extra attributes for debugging/advanced use
            self._attr_extra_state_attributes["raw_session_data"] = self._session
        else:
            # If session is None, ensure state is OFF and available is False?
            self._attr_state = MediaPlayerState.OFF
            # self._attr_available = False # Let availability be handled by _async_availability_changed


    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information for the media player."""
        # Ensure hub.server_id is available
        if not self.hub.server_id:
             return None

        return DeviceInfo(
            identifiers={(DOMAIN, self._session_key)}, # Use session key as primary identifier
            manufacturer=MANUFACTURER_MAP.get(
                self.hub.server_type, Manufacturer.UNKNOWN
            ),
            name=self._device_name or f"Media Player {self._session_key[:6]}", # Fallback name
            sw_version=self._device_version,
            model=self._device_model or "Generic Player", # Fallback model
            via_device=(DOMAIN, self.hub.server_id), # Link to the main hub device
        )

    # --- Service Calls ---
    async def async_send_message(self, text: str, header: str, timeout: int | None = None) -> None:
        """Send a message command to the player."""
        _LOGGER.debug("%s: Sending message: Header='%s', Text='%s', Timeout=%s", self.entity_id, header, text, timeout)
        command_data = {"Text": text, "Header": header}
        if timeout is not None:
            command_data["TimeoutMs"] = timeout * 1000 # Assuming timeout service parameter is in seconds
        try:
            await self.hub.async_command(self._session_key, "DisplayMessage", data=command_data)
            # No session refresh needed for display message typically
        except Exception as e:
            _LOGGER.error("Failed to send message to %s: %s", self.entity_id, e)

    async def async_send_command(self, command: str, arguments: Any = None) -> None:
        """Send a general command to the player."""
        _LOGGER.debug("%s: Sending command: Command='%s', Arguments=%s", self.entity_id, command, arguments)
        try:
            # Use async_command for general commands
            await self.hub.async_command(self._session_key, command, data=arguments)
            # Optionally refresh session after general commands if they might affect state
            # await self._hub.async_refresh_session(self._session_id)
        except Exception as e:
            _LOGGER.error("Failed to send command '%s' to %s: %s", command, self.entity_id, e)


    # --- Standard Media Player Methods ---
    async def async_media_seek(self, position: float) -> None:
        """Send seek command."""
        _LOGGER.debug("%s: Seeking to %s", self.entity_id, position)
        try:
            await self.hub.async_play_command(
                self._session_key,
                "Seek",
                {"SeekPositionTicks": int(position * TICKS_PER_SECOND)},
            )
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to seek on %s: %s", self.entity_id, e)


    async def async_media_next_track(self) -> None:
        """Send next track command."""
        _LOGGER.debug("%s: Next track", self.entity_id)
        try:
            await self.hub.async_play_command(self._session_key, "NextTrack")
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to skip to next track on %s: %s", self.entity_id, e)


    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        _LOGGER.debug("%s: Previous track", self.entity_id)
        try:
            await self.hub.async_play_command(self._session_key, "PreviousTrack")
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to skip to previous track on %s: %s", self.entity_id, e)


    async def async_media_pause(self) -> None:
        """Send pause command."""
        _LOGGER.debug("%s: Pausing", self.entity_id)
        try:
            await self.hub.async_play_command(self._session_key, "Pause")
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to pause %s: %s", self.entity_id, e)


    async def async_media_play_pause(self) -> None:
        """Send play/pause command."""
        _LOGGER.debug("%s: Toggling play/pause", self.entity_id)
        try:
            await self.hub.async_play_command(self._session_key, "PlayPause")
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to toggle play/pause on %s: %s", self.entity_id, e)


    async def async_media_stop(self) -> None:
        """Send stop command."""
        _LOGGER.debug("%s: Stopping", self.entity_id)
        try:
            await self.hub.async_play_command(self._session_key, "Stop")
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to stop %s: %s", self.entity_id, e)


    async def async_media_play(self) -> None:
        """Send play/unpause command."""
        _LOGGER.debug("%s: Playing/Unpausing", self.entity_id)
        try:
            # Use "Unpause" if currently paused, otherwise "Play" might be needed
            # Check current state to decide? Or just send "Unpause" / "PlayPause"
            # Sending "Unpause" is generally safe if playing or paused.
            await self.hub.async_play_command(self._session_key, "Unpause")
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to play/unpause %s: %s", self.entity_id, e)


    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute/unmute command."""
        command = "Mute" if mute else "Unmute"
        _LOGGER.debug("%s: Setting mute to %s", self.entity_id, mute)
        try:
            # Mute/Unmute are general commands, not play commands
            await self.hub.async_command(self._session_key, command)
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to %s %s: %s", command.lower(), self.entity_id, e)


    async def async_volume_up(self) -> None:
        """Send volume up command."""
        _LOGGER.debug("%s: Volume up", self.entity_id)
        try:
            await self.hub.async_command(self._session_key, "VolumeUp")
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to increase volume on %s: %s", self.entity_id, e)


    async def async_volume_down(self) -> None:
        """Send volume down command."""
        _LOGGER.debug("%s: Volume down", self.entity_id)
        try:
            await self.hub.async_command(self._session_key, "VolumeDown")
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to decrease volume on %s: %s", self.entity_id, e)


    async def async_set_volume_level(self, volume: float) -> None:
        """Send set volume level command."""
        volume_percent = int(volume * VOLUME_RATIO)
        _LOGGER.debug("%s: Setting volume to %s (%s%%)", self.entity_id, volume, volume_percent)
        try:
            await self.hub.async_command(
                self._session_key,
                "SetVolume",
                data={"Volume": volume_percent}, # API likely expects integer 0-100
            )
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to set volume on %s: %s", self.entity_id, e)


    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Send set repeat mode command."""
        mb_repeat_mode = REPEAT_HA_TO_MB.get(repeat)
        if mb_repeat_mode is None:
            _LOGGER.warning("%s: Received invalid repeat mode: %s", self.entity_id, repeat)
            return
        _LOGGER.debug("%s: Setting repeat mode to %s (%s)", self.entity_id, repeat, mb_repeat_mode)
        try:
            await self.hub.async_command(
                self._session_key,
                "SetRepeatMode",
                # API likely expects the argument key to be "Mode" or similar, check API docs
                data={"Mode": mb_repeat_mode}, # Adjust "Mode" if API expects different key like "RepeatMode"
            )
            # --- ADD THIS LINE ---
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to set repeat mode on %s: %s", self.entity_id, e)


    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia | None:
        """Implement the websocket media browsing."""
        _LOGGER.debug("%s: Browsing media: type=%s, id=%s", self.entity_id, media_content_type, media_content_id)
        if self._session is not None:
            try:
                return await async_browse_media_id(
                    self.hub,
                    media_content_id,
                    self._session.get(Session.PLAYABLE_MEDIA_TYPES),
                    True, # Assume can_play is true for players?
                )
            except Exception as e:
                _LOGGER.error("Failed to browse media on %s: %s", self.entity_id, e)
                return None
        else:
            _LOGGER.warning("%s: Cannot browse media, session not available.", self.entity_id)
            return None

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Send the play media command to the media player."""
        _LOGGER.debug("%s: Playing media: type=%s, id=%s, kwargs=%s", self.entity_id, media_type, media_id, kwargs)
        if self._session is None:
            _LOGGER.error("%s: Cannot play media, session not available.", self.entity_id)
            return

        actual_media_id = media_id # Start with the provided ID

        # Handle HA media source URI
        if media_id.startswith(f"media_source://{DOMAIN}"):
            actual_media_id = media_id.split("/")[-1]
            _LOGGER.debug("%s: Resolved media_source ID to %s", self.entity_id, actual_media_id)
        # Handle JSON payload for advanced playback
        elif media_id.startswith("{") and media_id.endswith("}"):
            try:
                actual_media_id = await self._async_play_media_json(media_id)
                _LOGGER.debug("%s: Resolved JSON media ID to %s", self.entity_id, actual_media_id)
            except NotFoundError as e:
                _LOGGER.error("%s: Failed to resolve JSON media ID: %s", self.entity_id, e)
                return # Stop playback attempt if ID resolution fails
            except json.JSONDecodeError as e:
                _LOGGER.error("%s: Invalid JSON provided for media_id: %s", self.entity_id, e)
                return
            except Exception as e:
                _LOGGER.error("%s: Error processing JSON media_id: %s", self.entity_id, e)
                return

        if not actual_media_id:
            _LOGGER.error("%s: Could not determine a valid media ID to play.", self.entity_id)
            return

        # Prepare parameters for the Play API call
        params = {
            "PlayCommand": "PlayNow", # Or PlayNext, PlayLast depending on kwargs?
            "ItemIds": actual_media_id # API likely expects comma-separated string if multiple
        }
        # Add enqueue behavior from kwargs if needed
        enqueue_mode = kwargs.get("enqueue")
        if enqueue_mode:
            # Map HA enqueue modes to MB PlayCommands if necessary
            # e.g., if enqueue_mode == MediaPlayerEnqueue.NEXT: params["PlayCommand"] = "PlayNext"
            # Defaulting to PlayNow, which usually replaces the queue
            _LOGGER.warning("%s: Enqueue modes not fully implemented, using PlayNow.", self.entity_id)


        try:
            await self.hub.async_play(self._session_key, params)
            # --- ADD THIS LINE ---
            # Refresh after starting playback
            await self.hub.async_refresh_session(self._session_key)
            # --- End Added Line ---
        except Exception as e:
            _LOGGER.error("Failed to play media on %s: %s", self.entity_id, e)


    async def _async_play_media_json(self, media_id_json: str) -> str:
        """Resolve a media ID from a JSON payload by searching items."""
        try:
            payload = json.loads(media_id_json)
            # Convert keys to CamelCase if needed by the hub's get_items
            params = camel_cased_json(payload) or {}
        except json.JSONDecodeError as err:
             _LOGGER.error("Invalid JSON in media_id: %s", media_id_json)
             raise err # Re-raise to be caught by async_play_media

        params["Limit"] = 1 # We only need one item to play

        try:
            # Assuming hub.async_get_items returns a dict like {'Items': [...], 'TotalRecordCount': x}
            response = await self.hub.async_get_items(params)
            items = response.get(Response.ITEMS, [])
            if not items:
                 raise NotFoundError(f"Cannot find any item matching JSON parameters: {params}")
            # Return the ID of the first found item
            first_item_id = items[0].get(Item.ID)
            if not first_item_id:
                 raise NotFoundError(f"Found item matching JSON parameters has no ID: {items[0]}")
            return first_item_id
        except (KeyError, IndexError, TypeError) as err:
            # Catch errors related to accessing the response structure
            _LOGGER.error("Error parsing response from async_get_items for JSON play: %s", err)
            raise NotFoundError(f"Could not extract item ID from server response for JSON parameters: {params}") from err
        # Let other exceptions (like connection errors from async_get_items) propagate

