"""Monitor Docker main component."""

import asyncio
import logging
from datetime import timedelta

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import (
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    ConfigEntryError,
    ConfigEntryAuthFailed,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.reload import async_setup_reload_service

from .config_flow import DockerConfigFlow
from .const import (
    API,
    CONF_CERTPATH,
    CONF_CONTAINERS,
    CONF_CONTAINERS_EXCLUDE,
    CONF_RETRY,
    CONFIG,
    CONTAINER_INFO_ALLINONE,
    DEFAULT_NAME,
    DEFAULT_RETRY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MONITORED_CONDITIONS_LIST,
)
from .helpers import DockerAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

DOCKER_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_URL, default=None): vol.Any(cv.string, None),
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): cv.positive_int,
        vol.Optional(CONF_MONITORED_CONDITIONS, default=[]): vol.All(
            cv.ensure_list,
            [vol.In(MONITORED_CONDITIONS_LIST)],
        ),
        vol.Optional(CONF_CONTAINERS, default=[]): cv.ensure_list,
        vol.Optional(CONF_CONTAINERS_EXCLUDE, default=[]): cv.ensure_list,
        vol.Optional(CONF_CERTPATH, default=""): cv.string,
        vol.Optional(CONF_RETRY, default=DEFAULT_RETRY): cv.positive_int,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [vol.Any(DOCKER_SCHEMA)])}, extra=vol.ALLOW_EXTRA
)


#################################################################
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    api = None

    try:
        api = DockerAPI(hass, entry.data)
        await api.init()

        # Pre-register docker instance, preventing warning in initial setup
        assert entry.unique_id
        device_registry = dr.async_get(hass)
        config_id = f"{entry.data[CONF_NAME]}_{entry.data[CONF_URL]}"
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, config_id)},
            manufacturer="Docker",
            name=entry.title,
            sw_version="1.00",
        )

        await api.run()

        hass.data[DOMAIN][entry.data[CONF_NAME]] = {}
        hass.data[DOMAIN][entry.data[CONF_NAME]][CONFIG] = entry.data
        hass.data[DOMAIN][entry.data[CONF_NAME]][API] = api

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    except ConfigEntryAuthFailed:
        # if api:
        #     await api.destroy()
        raise

    except Exception as err:
        _LOGGER.error(
            "[%s]: Failed to setup, error=%s", entry.data[CONF_NAME], str(err)
        )
        if api:
            await api.destroy()
        raise ConfigEntryNotReady(f"Failed to setup {err}") from err

    return True


#################################################################
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    _LOGGER.debug("async_unload_entry")

    await hass.data[DOMAIN][entry.data[CONF_NAME]][API].destroy()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

#################################################################
async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry."""

    if entry.data[CONF_NAME] in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.data[CONF_NAME])


#################################################################
async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Attempting migrating configuration from version %s.%s",
        entry.version,
        entry.minor_version,
    )

    class MigrateError(ConfigEntryError):
        """Error to indicate there is was an error in version migration."""

    installed_version = DockerConfigFlow.VERSION
    installed_minor_version = DockerConfigFlow.MINOR_VERSION

    new_data = {**entry.data}
    # new_options = {**entry.options}  # Note used

    if entry.version > installed_version:
        _LOGGER.warning(
            "Downgrading major version from %s to %s is not allowed",
            entry.version,
            installed_version,
        )
        return False

    if (
        entry.version == installed_version
        and entry.minor_version > installed_minor_version
    ):
        _LOGGER.warning(
            "Downgrading minor version from %s.%s to %s.%s is not allowed",
            entry.version,
            entry.minor_version,
            installed_version,
            installed_minor_version,
        )
        return False

    try:
        if entry.version == 1:
            pass
            # Verison 1.1 to 1.2
            # if entry.minor_version == 1:
            #     new_data = data_1_1_to_1_2(new_data)
            #     entry.minor_version = 2
            # Version 1.2 to 2.0
            # if entry.minor_version == 2:
            #     new_data = data_1_2_to_2_0(new_data)
            #     entry.version = 2
            #     entry.minor_version = 0
        # if entry.version == 2:
        #     ...
    except MigrateError as err:
        _LOGGER.error(
            "Error while upgrading from version %s.%s to %s.%s",
            entry.version,
            entry.minor_version,
            installed_version,
            installed_minor_version,
        )
        _LOGGER.error(str(err))
        return False

    hass.config_entries.async_update_entry(
        entry,
        data=new_data,
        # options=new_options,
        version=installed_version,
        minor_version=installed_minor_version,
    )
    _LOGGER.info(
        "Migration configuration from version %s.%s to %s.%s successful",
        entry.version,
        entry.minor_version,
        installed_version,
        installed_minor_version,
    )
    return True
