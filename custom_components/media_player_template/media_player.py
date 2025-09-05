"""Template for media-player
https://github.com/Sennevds/media_player.template
"""

import logging

import voluptuous as vol

from homeassistant.components.media_player import (
    DEVICE_CLASSES_SCHEMA,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA as MEDIA_PLAYER_PLATFORM_SCHEMA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components.template import DOMAIN
from homeassistant.components.template.helpers import async_setup_template_platform
from homeassistant.components.template.schemas import (
    TEMPLATE_ENTITY_AVAILABILITY_SCHEMA_LEGACY,
)
from homeassistant.components.template.template_entity import TemplateEntity
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_PICTURE_TEMPLATE,
    CONF_ICON_TEMPLATE,
    CONF_STATE,
    CONF_UNIQUE_ID,
    CONF_VALUE_TEMPLATE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import TemplateError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

LEGACY_FIELDS = {
    CONF_VALUE_TEMPLATE: CONF_STATE,
}

CONF_ALBUM_ART_TEMPLATE = "album_art_template"
CONF_ALBUM_TEMPLATE = "album_template"
CONF_ARTIST_TEMPLATE = "artist_template"
CONF_CURRENT_IS_MUTED_TEMPLATE = "current_is_muted_template"
CONF_CURRENT_POSITION_TEMPLATE = "current_position_template"
CONF_CURRENT_SOUND_MODE_TEMPLATE = "current_sound_mode_template"
CONF_CURRENT_SOURCE_TEMPLATE = "current_source_template"
CONF_CURRENT_VOLUME_TEMPLATE = "current_volume_template"
CONF_INPUTS = "inputs"
CONF_MEDIA_ALBUM_ARTIST_TEMPLATE = "media_album_artist_template"
CONF_MEDIA_CONTENT_TYPE_TEMPLATE = "media_content_type_template"
CONF_MEDIA_DURATION_TEMPLATE = "media_duration_template"
CONF_MEDIA_EPISODE_TEMPLATE = "media_episode_template"
CONF_MEDIA_IMAGE_URL_REMOTELY_ACCESSIBLE = "media_image_url_remotely_accessible"
CONF_MEDIA_IMAGE_URL_TEMPLATE = "media_image_url_template"
CONF_MEDIA_SEASON_TEMPLATE = "media_season_template"
CONF_MEDIA_SERIES_TITLE_TEMPLATE = "media_series_title_template"
CONF_MEDIAPLAYER = "media_players"
CONF_MUTE_ACTION = "mute"
CONF_NEXT_ACTION = "next"
CONF_OFF_ACTION = "turn_off"
CONF_ON_ACTION = "turn_on"
CONF_PAUSE_ACTION = "pause"
CONF_PLAY_ACTION = "play"
CONF_PLAY_MEDIA_ACTION = "play_media"
CONF_PREVIOUS_ACTION = "previous"
CONF_SEEK_ACTION = "seek"
CONF_SET_VOLUME_ACTION = "set_volume"
CONF_SOUND_MODES = "sound_modes"
CONF_STOP_ACTION = "stop"
CONF_TITLE_TEMPLATE = "title_template"
CONF_VOLUME_DOWN_ACTION = "volume_down"
CONF_VOLUME_UP_ACTION = "volume_up"


MEDIA_PLAYER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional(ATTR_FRIENDLY_NAME): cv.template,
        vol.Optional(CONF_ALBUM_ART_TEMPLATE): cv.template,
        vol.Optional(CONF_ALBUM_TEMPLATE): cv.template,
        vol.Optional(CONF_ARTIST_TEMPLATE): cv.template,
        vol.Optional(CONF_CURRENT_IS_MUTED_TEMPLATE): cv.template,
        vol.Optional(CONF_CURRENT_POSITION_TEMPLATE): cv.template,
        vol.Optional(CONF_CURRENT_SOUND_MODE_TEMPLATE): cv.template,
        vol.Optional(CONF_CURRENT_SOURCE_TEMPLATE): cv.template,
        vol.Optional(CONF_CURRENT_VOLUME_TEMPLATE): cv.template,
        vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
        vol.Optional(CONF_ENTITY_PICTURE_TEMPLATE): cv.template,
        vol.Optional(CONF_ICON_TEMPLATE): cv.template,
        vol.Optional(CONF_INPUTS, default={}): {cv.string: cv.SCRIPT_SCHEMA},
        vol.Optional(CONF_MEDIA_ALBUM_ARTIST_TEMPLATE): cv.template,
        vol.Optional(CONF_MEDIA_CONTENT_TYPE_TEMPLATE): cv.template,
        vol.Optional(CONF_MEDIA_DURATION_TEMPLATE): cv.template,
        vol.Optional(CONF_MEDIA_EPISODE_TEMPLATE): cv.template,
        vol.Optional(CONF_MEDIA_IMAGE_URL_REMOTELY_ACCESSIBLE): cv.boolean,
        vol.Optional(CONF_MEDIA_IMAGE_URL_TEMPLATE): cv.template,
        vol.Optional(CONF_MEDIA_SEASON_TEMPLATE): cv.template,
        vol.Optional(CONF_MEDIA_SERIES_TITLE_TEMPLATE): cv.template,
        vol.Optional(CONF_MUTE_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_NEXT_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_OFF_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_ON_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_PAUSE_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_PLAY_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_PLAY_MEDIA_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_PREVIOUS_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_SEEK_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_SET_VOLUME_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_SOUND_MODES, default={}): {cv.string: cv.SCRIPT_SCHEMA},
        vol.Optional(CONF_STOP_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_TITLE_TEMPLATE): cv.template,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Required(CONF_VALUE_TEMPLATE): cv.template,
        vol.Optional(CONF_VOLUME_DOWN_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_VOLUME_UP_ACTION): cv.SCRIPT_SCHEMA,
    }
).extend(TEMPLATE_ENTITY_AVAILABILITY_SCHEMA_LEGACY.schema)

PLATFORM_SCHEMA = MEDIA_PLAYER_PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_MEDIAPLAYER): cv.schema_with_slug_keys(MEDIA_PLAYER_SCHEMA)}
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the template media player."""
    await async_setup_template_platform(
        hass,
        MEDIA_PLAYER_DOMAIN,
        config,
        MediaPlayerTemplate,
        None,
        async_add_entities,
        discovery_info,
        LEGACY_FIELDS,
        CONF_MEDIAPLAYER,
    )


class MediaPlayerTemplate(TemplateEntity, MediaPlayerEntity):
    """Representation of a Template Media player."""

    _attr_should_poll = False
    _entity_id_format = ENTITY_ID_FORMAT

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        unique_id: str,
    ) -> None:
        """Initialize the Template Media player."""
        super().__init__(hass, config, unique_id)

        self._attr_device_class = config.get(CONF_DEVICE_CLASS)
        self._template = config[CONF_STATE]

        self._attr_supported_features = MediaPlayerEntityFeature(0)
        for action_id, supported_feature in (
            (CONF_ON_ACTION, MediaPlayerEntityFeature.TURN_ON),
            (CONF_OFF_ACTION, MediaPlayerEntityFeature.TURN_OFF),
            (CONF_PLAY_ACTION, MediaPlayerEntityFeature.PLAY),
            (CONF_STOP_ACTION, MediaPlayerEntityFeature.STOP),
            (CONF_PAUSE_ACTION, MediaPlayerEntityFeature.PAUSE),
            (CONF_NEXT_ACTION, MediaPlayerEntityFeature.NEXT_TRACK),
            (CONF_PREVIOUS_ACTION, MediaPlayerEntityFeature.PREVIOUS_TRACK),
            (CONF_VOLUME_UP_ACTION, MediaPlayerEntityFeature.VOLUME_STEP),
            (CONF_VOLUME_DOWN_ACTION, MediaPlayerEntityFeature.VOLUME_STEP),
            (CONF_MUTE_ACTION, MediaPlayerEntityFeature.VOLUME_MUTE),
            (CONF_SET_VOLUME_ACTION, MediaPlayerEntityFeature.VOLUME_SET),
            (CONF_PLAY_MEDIA_ACTION, MediaPlayerEntityFeature.PLAY_MEDIA),
            (CONF_SEEK_ACTION, MediaPlayerEntityFeature.SEEK),
        ):
            if (action_config := config.get(action_id)) is not None:
                self.add_script(action_id, action_config, self._attr_name, DOMAIN)
                if supported_feature is not None:
                    self._attr_supported_features |= supported_feature

        # Source and Source List
        for source, source_config in config.get(CONF_INPUTS, {}).items():
            self._add_source(source, source_config)

        # Sound Mode and Sound Mode List
        for sound_mode, sound_mode_config in config.get(CONF_SOUND_MODES, {}).items():
            self._add_sound_mode(sound_mode, sound_mode_config)

        self._current_source_template = config.get(CONF_CURRENT_SOURCE_TEMPLATE)
        self._title_template = config.get(CONF_TITLE_TEMPLATE)
        self._artist_template = config.get(CONF_ARTIST_TEMPLATE)
        self._album_template = config.get(CONF_ALBUM_TEMPLATE)
        self._current_volume_template = config.get(CONF_CURRENT_VOLUME_TEMPLATE)
        self._current_is_muted_template = config.get(CONF_CURRENT_IS_MUTED_TEMPLATE)
        self._current_sound_mode_template = config.get(CONF_CURRENT_SOUND_MODE_TEMPLATE)
        self._album_art_template = config.get(CONF_ALBUM_ART_TEMPLATE)
        self._media_content_type_template = config.get(CONF_MEDIA_CONTENT_TYPE_TEMPLATE)
        self._media_image_url_template = config.get(CONF_MEDIA_IMAGE_URL_TEMPLATE)
        self._media_episode_template = config.get(CONF_MEDIA_EPISODE_TEMPLATE)
        self._media_season_template = config.get(CONF_MEDIA_SEASON_TEMPLATE)
        self._media_series_title_template = config.get(CONF_MEDIA_SERIES_TITLE_TEMPLATE)
        self._media_album_artist_template = config.get(CONF_MEDIA_ALBUM_ARTIST_TEMPLATE)
        self._media_content_type_template = config.get(CONF_MEDIA_CONTENT_TYPE_TEMPLATE)
        self._current_position_template = config.get(CONF_CURRENT_POSITION_TEMPLATE)
        self._media_duration_template = config.get(CONF_MEDIA_DURATION_TEMPLATE)

        self._attr_media_image_remotely_accessible = config.get(
            CONF_MEDIA_IMAGE_URL_REMOTELY_ACCESSIBLE, False
        )

    def _async_setup_templates(self):
        """Set up templates."""
        self.add_template_attribute(
            "_attr_state",
            self._template,
            None,
            self._update_state,
            none_on_template_error=True,
        )

        if self._current_source_template is not None:
            self.add_template_attribute(
                "_attr_source",
                self._current_source_template,
                None,
                self._update_source,
                none_on_template_error=True,
            )

        if self._title_template is not None:
            self.add_template_attribute(
                "_attr_media_title",
                self._title_template,
                None,
                self._update_title,
                none_on_template_error=True,
            )

        if self._artist_template is not None:
            self.add_template_attribute(
                "_attr_media_artist",
                self._artist_template,
                None,
                self._update_media_artist,
                none_on_template_error=True,
            )

        if self._album_template is not None:
            self.add_template_attribute(
                "_attr_media_album_name",
                self._album_template,
                None,
                self._update_media_album_name,
                none_on_template_error=True,
            )

        if self._current_volume_template is not None:
            self.add_template_attribute(
                "_attr_volume_level",
                self._current_volume_template,
                None,
                self._update_volume_level,
                none_on_template_error=True,
            )

        if self._current_is_muted_template is not None:
            self.add_template_attribute(
                "_attr_is_volume_muted",
                self._current_is_muted_template,
                None,
                self._update_is_volume_muted,
                none_on_template_error=True,
            )

        if self._media_content_type_template is not None:
            self.add_template_attribute(
                "_attr_media_content_type",
                self._media_content_type_template,
                None,
                self._update_media_content_type,
                none_on_template_error=True,
            )
        if self._media_image_url_template is not None:
            self.add_template_attribute(
                "_attr_media_image_url",
                self._media_image_url_template,
                None,
                self._update_media_image_url,
                none_on_template_error=True,
            )
        if self._media_episode_template is not None:
            self.add_template_attribute(
                "_attr_media_episode",
                self._media_episode_template,
                None,
                self._update_media_episode,
                none_on_template_error=True,
            )
        if self._media_season_template is not None:
            self.add_template_attribute(
                "_attr_media_season",
                self._media_season_template,
                None,
                self._update_media_season,
                none_on_template_error=True,
            )
        if self._media_series_title_template is not None:
            self.add_template_attribute(
                "_attr_media_series_title",
                self._media_series_title_template,
                None,
                self._update_media_series_title,
                none_on_template_error=True,
            )
        if self._media_album_artist_template is not None:
            self.add_template_attribute(
                "_attr_media_album_artist",
                self._media_album_artist_template,
                None,
                self._update_media_album_artist,
                none_on_template_error=True,
            )
        if self._current_position_template is not None:
            self.add_template_attribute(
                "_attr_media_position",
                self._current_position_template,
                None,
                self._update_media_position,
                none_on_template_error=True,
            )
        if self._media_duration_template is not None:
            self.add_template_attribute(
                "_attr_media_duration",
                self._media_duration_template,
                None,
                self._update_media_duration,
                none_on_template_error=True,
            )
        if self._current_sound_mode_template is not None:
            self.add_template_attribute(
                "_attr_sound_mode",
                self._current_sound_mode_template,
                None,
                self._update_sound_mode,
                none_on_template_error=True,
            )
        super()._async_setup_templates()

    def _add_source(self, source: str, config: ConfigType | None = None) -> None:
        if config is not None and config:
            self.add_script(f"input_{source}", config, self._attr_name, DOMAIN)

        if not MediaPlayerEntityFeature.SELECT_SOURCE & self._attr_supported_features:
            self._attr_supported_features |= MediaPlayerEntityFeature.SELECT_SOURCE

        if self._attr_source_list is None:
            self._attr_source_list = []

        self._attr_source_list.append(source)

    def _add_sound_mode(
        self, sound_mode: str, config: ConfigType | None = None
    ) -> None:
        if config is not None and config:
            self.add_script(f"sound_mode_{sound_mode}", config, self._attr_name, DOMAIN)

        if (
            not MediaPlayerEntityFeature.SELECT_SOUND_MODE
            & self._attr_supported_features
        ):
            self._attr_supported_features |= MediaPlayerEntityFeature.SELECT_SOUND_MODE

        if self._attr_sound_mode_list is None:
            self._attr_sound_mode_list = []

        self._attr_sound_mode_list.append(sound_mode)

    @callback
    def _update_state(self, result):
        super()._update_state(result)
        if isinstance(result, TemplateError) or result is None:
            self._attr_state = None
            return

        result = vol.Coerce(str)(result).lower()
        try:
            if result == "true":
                self._attr_state = MediaPlayerState.ON
            elif result == "false":
                self._attr_state = MediaPlayerState.OFF
            else:
                self._attr_state = MediaPlayerState(result)
        except ValueError:
            _LOGGER.error(
                "Template entity %s received an invalid state %s, expected: true, false, %s",
                self.entity_id,
                result,
                ", ".join(MediaPlayerState),
            )
            self._attr_state = None

    @callback
    def _update_source(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_source = None
            return

        if self._attr_source_list and result not in self._attr_source_list:
            _LOGGER.debug(
                "Received new source: %s for entity %s", result, self.entity_id
            )
            self._add_source(result)

        self._attr_source = result

    @callback
    def _update_title(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_title = None
            return

        self._attr_media_title = vol.Coerce(str)(result)

    @callback
    def _update_media_artist(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_artist = None
            return

        self._attr_media_artist = vol.Coerce(str)(result)

    @callback
    def _update_media_album_name(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_album_name = None
            return

        self._attr_media_album_name = vol.Coerce(str)(result)

    @callback
    def _update_volume_level(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_volume_level = None
            return

        try:
            level = vol.All(vol.Coerce(float), vol.Range(min=0))(result)
            self._attr_volume_level = level
        except vol.Invalid:
            _LOGGER.error(
                "Received invalid volume level: %s for entity %s, expected value above 0",
                result,
                self.entity_id,
            )
            self._attr_volume_level = None

    @callback
    def _update_is_volume_muted(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_is_volume_muted = None
            return

        try:
            self._attr_is_volume_muted = cv.boolean(result)
        except vol.Invalid:
            _LOGGER.error(
                "Received invalid mute: %s for entity %s, expected: true or false",
                result,
                self.entity_id,
            )
            self._attr_is_volume_muted = None

    @callback
    def _update_media_content_type(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_content_type = None
            return

        result = vol.Coerce(str)(result).lower()
        try:
            self._attr_media_content_type = MediaType(result)
        except ValueError:
            _LOGGER.error(
                "Template entity %s received an invalid media content type %s, expected: %s",
                self.entity_id,
                result,
                ", ".join(MediaType),
            )
            self._attr_media_content_type = None

    @callback
    def _update_media_image_url(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_image_url = None
            return

        self._attr_media_image_url = vol.Coerce(str)(result)

    @callback
    def _update_media_episode(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_episode = None
            return

        self._attr_media_episode = vol.Coerce(str)(result)

    @callback
    def _update_media_season(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_season = None
            return

        self._attr_media_season = vol.Coerce(str)(result)

    @callback
    def _update_media_series_title(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_series_title = None
            return

        self._attr_media_series_title = vol.Coerce(str)(result)

    @callback
    def _update_media_album_artist(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_album_artist = None
            return

        self._attr_media_album_artist = vol.Coerce(str)(result)

    @callback
    def _update_media_position(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_media_position_updated_at = None
            self._attr_media_position = None
            return

        try:
            if self._attr_state in (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED):
                self._attr_media_position_updated_at = dt_util.utcnow()
                self._attr_media_position = cv.positive_int(result)
            else:
                self._attr_media_position_updated_at = None
                self._attr_media_position = None
        except vol.Invalid:
            _LOGGER.error(
                "Template entity %s received an invalid media position %s",
                self.entity_id,
                result,
            )
            self._attr_media_position_updated_at = None
            self._attr_media_position = None

    @callback
    def _update_media_duration(self, result):
        if isinstance(result, TemplateError):
            self._attr_media_duration = None
            return

        try:
            if self._attr_state in (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED):
                self._attr_media_duration = cv.positive_int(result)
            else:
                self._attr_media_duration = None

        except vol.Invalid:
            _LOGGER.error(
                "Template entity %s received an invalid media duration %s",
                self.entity_id,
                result,
            )
            self._attr_media_duration = None

    @callback
    def _update_sound_mode(self, result):
        if isinstance(result, TemplateError) or result is None:
            self._attr_sound_mode = None
            return

        if self._attr_sound_mode_list and result not in self._attr_sound_mode_list:
            _LOGGER.debug(
                "Received new sound mode: %s for entity %s",
                result,
                self.entity_id,
            )
            self._add_sound_mode(result)

        self._attr_sound_mode = result

    async def async_turn_on(self):
        """Fire the on action."""
        if script := self._action_scripts.get(CONF_ON_ACTION):
            await self.async_run_script(script, context=self._context)

    async def async_turn_off(self):
        """Fire the off action."""
        if script := self._action_scripts.get(CONF_OFF_ACTION):
            await self.async_run_script(script, context=self._context)

    async def async_volume_up(self):
        """Fire the volume up action."""
        if script := self._action_scripts.get(CONF_VOLUME_UP_ACTION):
            await self.async_run_script(script, context=self._context)

    async def async_volume_down(self):
        """Fire the volume down action."""
        if script := self._action_scripts.get(CONF_VOLUME_DOWN_ACTION):
            await self.async_run_script(script, context=self._context)

    async def async_mute_volume(self, mute):
        """Set the is_muted state."""
        if self._current_is_muted_template is None:
            self._attr_is_volume_muted = mute
            self.async_write_ha_state()
        if script := self._action_scripts.get(CONF_MUTE_ACTION):
            await self.async_run_script(
                script,
                run_variables={"is_muted": mute},
                context=self._context,
            )

    async def async_media_play(self):
        """Fire the play action."""
        if script := self._action_scripts.get(CONF_PLAY_ACTION):
            await self.async_run_script(script, context=self._context)

    async def async_media_stop(self):
        """Fire the stop action."""
        if script := self._action_scripts.get(CONF_STOP_ACTION):
            await self.async_run_script(script, context=self._context)

    async def async_media_pause(self):
        """Fire the pause action."""
        if script := self._action_scripts.get(CONF_PAUSE_ACTION):
            await self.async_run_script(script, context=self._context)

    async def async_media_next_track(self):
        """Fire the media next action."""
        if script := self._action_scripts.get(CONF_NEXT_ACTION):
            await self.async_run_script(script, context=self._context)

    async def async_media_previous_track(self):
        """Fire the media previous action."""
        if script := self._action_scripts.get(CONF_PREVIOUS_ACTION):
            await self.async_run_script(script, context=self._context)

    async def async_set_volume_level(self, volume):
        """Set the volume."""
        if self._current_volume_template is None:
            self._attr_volume_level = volume
            self.async_write_ha_state()
        if script := self._action_scripts.get(CONF_SET_VOLUME_ACTION):
            await self.async_run_script(
                script,
                run_variables={"volume": volume},
                context=self._context,
            )

    async def async_play_media(self, media_type, media_id, **kwargs):
        """Play media."""
        if script := self._action_scripts.get(CONF_PLAY_MEDIA_ACTION):
            await self.async_run_script(
                script,
                run_variables={"media_type": media_type, "media_id": media_id},
                context=self._context,
            )

    async def async_media_seek(self, position):
        """Send seek command."""
        if script := self._action_scripts.get(CONF_SEEK_ACTION):
            await self.async_run_script(
                script,
                run_variables={"position": position},
                context=self._context,
            )

    async def async_select_source(self, source):
        """Set the input source."""
        if script := self._action_scripts.get(f"input_{source}"):
            if self._current_source_template is None:
                self._attr_source = source
                self.async_write_ha_state()
            await self.async_run_script(script, context=self._context)

    async def async_select_sound_mode(self, sound_mode):
        """Select sound mode."""
        if script := self._action_scripts.get(f"sound_mode_{sound_mode}"):
            if self._current_sound_mode_template is None:
                self._attr_sound_mode = sound_mode
                self.async_write_ha_state()
            await self.async_run_script(script, context=self._context)
