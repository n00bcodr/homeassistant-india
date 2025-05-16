# custom_components/mediabrowser/config_flow.py
# --- FINAL VERSION WITH CORRECTED IMPORTS AND REAL VALIDATION ---
"""Config and Options flows for Media Browser (Emby/Jellyfin) integration."""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from typing import Any
import uuid # Make sure uuid is imported

import aiohttp
import voluptuous as vol
# Import ConfigEntryAuthFailed
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow, ConfigEntryAuthFailed
# Import CONF_NAME from homeassistant.const
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get,
)

# Import only component-specific constants from .const
from .const import (
    CONF_API_KEY,
    CONF_CACHE_SERVER_ID,
    CONF_CACHE_SERVER_NAME,
    CONF_CACHE_SERVER_PING,
    CONF_CACHE_SERVER_USER_ID,
    CONF_CACHE_SERVER_VERSION,
    CONF_CLIENT_NAME,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_VERSION,
    CONF_EVENTS_ACTIVITY_LOG,
    CONF_EVENTS_OTHER,
    CONF_EVENTS_SESSIONS,
    CONF_EVENTS_TASKS,
    CONF_IGNORE_APP_PLAYERS,
    CONF_IGNORE_DLNA_PLAYERS,
    CONF_IGNORE_MOBILE_PLAYERS,
    CONF_IGNORE_WEB_PLAYERS,
    CONF_PURGE_PLAYERS,
    CONF_SENSOR_ITEM_TYPE,
    CONF_SENSOR_LIBRARY,
    CONF_SENSOR_REMOVE,
    CONF_SENSOR_USER,
    CONF_SENSORS,
    CONF_SERVER,
    CONF_TIMEOUT,
    CONF_UPCOMING_MEDIA,
    DATA_HUB,
    DEFAULT_CLIENT_NAME,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DEVICE_VERSION,
    DEFAULT_EVENTS_ACTIVITY_LOG,
    DEFAULT_EVENTS_OTHER,
    DEFAULT_EVENTS_SESSIONS,
    DEFAULT_EVENTS_TASKS,
    DEFAULT_IGNORE_APP_PLAYERS,
    DEFAULT_IGNORE_DLNA_PLAYERS,
    DEFAULT_IGNORE_MOBILE_PLAYERS,
    DEFAULT_IGNORE_WEB_PLAYERS,
    DEFAULT_PORT,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_PURGE_PLAYERS,
    DEFAULT_SENSORS,
    DEFAULT_SERVER_NAME,
    DEFAULT_SSL_PORT,
    DEFAULT_UPCOMING_MEDIA,
    DOMAIN, # Import DOMAIN
    KEY_ALL,
    SENSOR_ITEM_TYPES,
    Discovery,
    EntityType,
    Item,
    Server,
    # ApiUrl, # Not strictly needed if only used in hub.py
)
from .discovery import discover_mb
from .helpers import build_sensor_key_from_config, extract_sensor_key
# Import Hub and errors needed for REAL validation
from .hub import ClientMismatchError, MediaBrowserHub, ConnectError, RequestError

_LOGGER = logging.getLogger(__name__)


# --- REAL VALIDATION LOGIC ---
async def _validate_config(
    config_data: dict[str, Any],
    errors: dict[str, str],
) -> tuple[bool, dict[str, Any]]:
    """Validate the provided configuration (URL and API Key)."""
    errors.clear()
    hub = None # Initialize hub to None for finally block
    if not config_data.get(CONF_URL) or not config_data.get(CONF_API_KEY):
        errors["base"] = "missing_url_or_key"
        return False, {}

    try:
        # Hub is imported above now
        hub = MediaBrowserHub(config_data)

        # Perform validation steps
        await hub._async_needs_server_verification()
        await hub.async_test_api_key() # Use the API key test method

    except ConfigEntryAuthFailed as err:
         # Map specific auth errors
         if "Invalid API Key" in str(err): errors["base"] = "invalid_auth"
         elif "permissions" in str(err).lower(): errors["base"] = "forbidden"
         else: errors["base"] = "invalid_auth" # Default auth error
    except (ConnectError, aiohttp.ClientConnectionError) as err:
        errors["base"] = "cannot_connect"
    except aiohttp.ClientResponseError as err:
        _LOGGER.warning("API validation HTTP error: %s (%s)", err.status, err.message)
        if err.status == 401: errors["base"] = "invalid_auth" # Should be caught by ConfigEntryAuthFailed
        elif err.status == 403: errors["base"] = "forbidden" # Should be caught by ConfigEntryAuthFailed
        else: errors["base"] = "bad_request" # Or map other statuses if needed
    except (TimeoutError, asyncio.TimeoutError):
        _LOGGER.error("Timeout validating connection to %s", config_data.get(CONF_URL))
        errors["base"] = "timeout"
    except ClientMismatchError as err:
         _LOGGER.warning("Server ID mismatch during validation: %s", err)
         errors["base"] = "mismatch"
    except RequestError as err: # Catch generic request errors from Hub
         _LOGGER.warning("Hub validation request error: %s", err)
         errors["base"] = "unknown" # Or map specific RequestError subtypes if defined
    except ValueError as err: # Catch Hub init errors (e.g., bad URL)
         _LOGGER.warning("Configuration error during validation: %s", err)
         errors["base"] = "invalid_url"
    except Exception as err: # Catch-all for unexpected validation issues
        _LOGGER.exception("Unexpected validation error: %s (%s)", type(err), err)
        errors["base"] = "unknown"
    else:
        # Validation successful, return validated data including fetched info
        validated_data = config_data.copy()
        validated_data.update({
            CONF_URL: hub.server_url,
            CONF_API_KEY: hub.api_key,
            CONF_CLIENT_NAME: hub.client_name,
            CONF_DEVICE_NAME: hub.device_name,
            CONF_DEVICE_ID: hub.device_id,
            CONF_DEVICE_VERSION: hub.device_version,
            CONF_TIMEOUT: hub.timeout,
            CONF_NAME: config_data.get(CONF_NAME, hub.server_name),
            # Include ignore/event flags using validated hub values as defaults
            CONF_IGNORE_WEB_PLAYERS: config_data.get(CONF_IGNORE_WEB_PLAYERS, hub.ignore_web_players),
            CONF_IGNORE_DLNA_PLAYERS: config_data.get(CONF_IGNORE_DLNA_PLAYERS, hub.ignore_dlna_players),
            CONF_IGNORE_MOBILE_PLAYERS: config_data.get(CONF_IGNORE_MOBILE_PLAYERS, hub.ignore_mobile_players),
            CONF_IGNORE_APP_PLAYERS: config_data.get(CONF_IGNORE_APP_PLAYERS, hub.ignore_app_players),
            CONF_EVENTS_SESSIONS: config_data.get(CONF_EVENTS_SESSIONS, hub.send_session_events),
            CONF_EVENTS_ACTIVITY_LOG: config_data.get(CONF_EVENTS_ACTIVITY_LOG, hub.send_activity_events),
            CONF_EVENTS_TASKS: config_data.get(CONF_EVENTS_TASKS, hub.send_task_events),
            CONF_EVENTS_OTHER: config_data.get(CONF_EVENTS_OTHER, hub.send_other_events),
            # Include cache keys from validated hub
            CONF_CACHE_SERVER_ID: hub.server_id,
            CONF_CACHE_SERVER_NAME: hub.server_name,
            CONF_CACHE_SERVER_PING: hub.server_ping,
            CONF_CACHE_SERVER_VERSION: hub.server_version,
            CONF_CACHE_SERVER_USER_ID: hub.user_id,
        })
        await hub.async_stop() # Stop temporary hub ONLY on success
        return True, validated_data
    finally:
        # Ensure hub is stopped if validation failed partway through
        if hub and errors:
            await hub.async_stop()
    return False, {}
# --- END OF REAL VALIDATION LOGIC ---


class MediaBrowserConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Media Browser (Emby/Jellyfin)."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self.available_servers: dict[str, Any] | None = None
        self.discovered_server_id: str | None = None
        # Remove other unused instance variables like host/port/ssl/name if not needed

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial discovery step."""
        try:
            discovered = await self.hass.async_add_executor_job(discover_mb)
            self.available_servers = {server[Discovery.ID]: server for server in discovered if Discovery.ID in server}
        except Exception as e:
            _LOGGER.warning("Discovery failed: %s", e); self.available_servers = {}
        current_ids = {entry.unique_id for entry in self._async_current_entries(include_ignore=True) if entry.unique_id}
        if self.available_servers:
            self.available_servers = {sid: sinfo for sid, sinfo in self.available_servers.items() if sid not in current_ids}
        if not self.available_servers: return await self.async_step_manual()
        if len(self.available_servers) == 1:
            self.discovered_server_id = next(iter(self.available_servers)); return await self.async_step_manual()
        return await self.async_step_select()

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle multiple servers discovered step."""
        if user_input is not None:
            self.discovered_server_id = user_input[CONF_SERVER]; return await self.async_step_manual()
        if not self.available_servers: return await self.async_step_manual()
        server_list = {sid: f'{sinfo.get(Discovery.NAME,"?")} ({sinfo.get(Discovery.ADDRESS)})' for sid, sinfo in self.available_servers.items()}
        if not server_list: return await self.async_step_manual()
        return self.async_show_form(step_id="select", data_schema=vol.Schema({vol.Required(CONF_SERVER): vol.In(server_list)}))

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the manual configuration step (URL and API Key)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Call the REAL validation function
            valid, validation_data = await _validate_config(user_input, errors)

            if valid and validation_data.get(CONF_CACHE_SERVER_ID):
                unique_id = validation_data[CONF_CACHE_SERVER_ID]
                await self.async_set_unique_id(unique_id, raise_on_progress=False)
                self._abort_if_unique_id_configured(updates=validation_data)

                # Prepare options using the validated data
                options_to_save = {
                    CONF_URL: validation_data[CONF_URL],
                    CONF_API_KEY: validation_data[CONF_API_KEY],
                    CONF_NAME: validation_data[CONF_NAME], # Use name from validation
                    CONF_CLIENT_NAME: validation_data[CONF_CLIENT_NAME],
                    CONF_DEVICE_NAME: validation_data[CONF_DEVICE_NAME],
                    CONF_DEVICE_ID: validation_data[CONF_DEVICE_ID],
                    CONF_DEVICE_VERSION: validation_data[CONF_DEVICE_VERSION],
                    CONF_TIMEOUT: validation_data[CONF_TIMEOUT],
                    # Use defaults for options not set during initial config
                    CONF_PURGE_PLAYERS: DEFAULT_PURGE_PLAYERS,
                    CONF_UPCOMING_MEDIA: DEFAULT_UPCOMING_MEDIA,
                    CONF_SENSORS: DEFAULT_SENSORS,
                    # Use validated values from hub as defaults
                    CONF_IGNORE_WEB_PLAYERS: validation_data[CONF_IGNORE_WEB_PLAYERS],
                    CONF_IGNORE_DLNA_PLAYERS: validation_data[CONF_IGNORE_DLNA_PLAYERS],
                    CONF_IGNORE_MOBILE_PLAYERS: validation_data[CONF_IGNORE_MOBILE_PLAYERS],
                    CONF_IGNORE_APP_PLAYERS: validation_data[CONF_IGNORE_APP_PLAYERS],
                    CONF_EVENTS_SESSIONS: validation_data[CONF_EVENTS_SESSIONS],
                    CONF_EVENTS_ACTIVITY_LOG: validation_data[CONF_EVENTS_ACTIVITY_LOG],
                    CONF_EVENTS_TASKS: validation_data[CONF_EVENTS_TASKS],
                    CONF_EVENTS_OTHER: validation_data[CONF_EVENTS_OTHER],
                    # Include cache keys
                    CONF_CACHE_SERVER_ID: validation_data[CONF_CACHE_SERVER_ID],
                    CONF_CACHE_SERVER_NAME: validation_data[CONF_CACHE_SERVER_NAME],
                    CONF_CACHE_SERVER_PING: validation_data.get(CONF_CACHE_SERVER_PING),
                    CONF_CACHE_SERVER_VERSION: validation_data[CONF_CACHE_SERVER_VERSION],
                    CONF_CACHE_SERVER_USER_ID: validation_data.get(CONF_CACHE_SERVER_USER_ID),
                }
                entry_title = options_to_save[CONF_NAME]
                _LOGGER.info("Creating entry '%s' with validated config.", entry_title)
                return self.async_create_entry(title=entry_title, data={}, options=options_to_save)
            elif not errors: errors["base"] = "unknown" # Fallback error

        # --- Schema definition ---
        previous_input = user_input or {}
        default_url = ""; default_name = DEFAULT_SERVER_NAME
        if self.discovered_server_id and self.available_servers:
            server = self.available_servers.get(self.discovered_server_id)
            if server: default_url = server.get(Discovery.ADDRESS, ""); default_name = server.get(Discovery.NAME) or default_name
        data_schema = vol.Schema({
            vol.Required(CONF_URL, description={"suggested_value": previous_input.get(CONF_URL, default_url)}): str,
            vol.Required(CONF_API_KEY, description={"suggested_value": previous_input.get(CONF_API_KEY)}): str,
            vol.Optional(CONF_NAME, description={"suggested_value": previous_input.get(CONF_NAME, default_name)}): str,
        })
        return self.async_show_form(step_id="manual", data_schema=data_schema, errors=errors)

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the reauthorization step (API Key only)."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        if user_input is not None:
            options_for_validation = deepcopy(dict(entry.options))
            options_for_validation[CONF_API_KEY] = user_input[CONF_API_KEY]
            if CONF_URL not in options_for_validation: return self.async_abort(reason="missing_configuration")

            # Use the REAL validation logic
            valid, validation_data = await _validate_config(options_for_validation, errors)

            if valid:
                self.hass.config_entries.async_update_entry(entry, options=validation_data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            elif not errors: errors["base"] = "unknown"

        data_schema = vol.Schema({vol.Required(CONF_API_KEY, description={"suggested_value": ""}): str})
        self.context["title_placeholders"] = {"name": entry.title}
        return self.async_show_form(
            step_id="reauth", data_schema=data_schema, errors=errors,
            description_placeholders={"url": entry.options.get(CONF_URL)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return MediaBrowserOptionsFlow(config_entry)


class MediaBrowserOptionsFlow(OptionsFlow):
    """Handle an option flow for Media Browser (Emby/Jellyfin)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = deepcopy(dict(config_entry.options))

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["auth", "players", "libraries", "events", "add_sensor", "remove_sensor", "advanced"])

    async def async_step_auth(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input:
            options_for_validation = self.options.copy()
            options_for_validation[CONF_API_KEY] = user_input[CONF_API_KEY]
            if CONF_URL not in options_for_validation: errors["base"] = "missing_configuration"
            else:
                 # Use REAL validation
                 valid, validation_data = await _validate_config(options_for_validation, errors)
                 if valid: return self.async_create_entry(title="", data=validation_data)
                 elif not errors: errors["base"] = "unknown"

        return self.async_show_form(
             step_id="auth",
             data_schema=vol.Schema({vol.Required(CONF_API_KEY, description={"suggested_value": ""}): str}),
             errors=errors,
             description_placeholders={"url": self.options.get(CONF_URL)},
         )

    # --- Other Option Steps (Implementations from previous response) ---
    async def async_step_libraries(self, user_input=None):
        if user_input is not None: self.options.update(user_input); return self.async_create_entry(title="", data=self.options)
        return self.async_show_form(step_id="libraries", data_schema=vol.Schema({vol.Required(CONF_UPCOMING_MEDIA, default=self.options.get(CONF_UPCOMING_MEDIA, DEFAULT_UPCOMING_MEDIA)): bool}))

    async def async_step_events(self, user_input=None):
         if user_input is not None: self.options.update(user_input); return self.async_create_entry(title="", data=self.options)
         return self.async_show_form(step_id="events", data_schema=vol.Schema({
             vol.Optional(CONF_EVENTS_SESSIONS, default=self.options.get(CONF_EVENTS_SESSIONS, DEFAULT_EVENTS_SESSIONS)): bool,
             vol.Optional(CONF_EVENTS_ACTIVITY_LOG, default=self.options.get(CONF_EVENTS_ACTIVITY_LOG, DEFAULT_EVENTS_ACTIVITY_LOG)): bool,
             vol.Optional(CONF_EVENTS_TASKS, default=self.options.get(CONF_EVENTS_TASKS, DEFAULT_EVENTS_TASKS)): bool,
             vol.Optional(CONF_EVENTS_OTHER, default=self.options.get(CONF_EVENTS_OTHER, DEFAULT_EVENTS_OTHER)): bool,}))

    async def async_step_players(self, user_input=None):
         if user_input is not None: self.options.update(user_input); return self.async_create_entry(title="", data=self.options)
         return self.async_show_form(step_id="players", data_schema=vol.Schema({
             vol.Required(CONF_IGNORE_WEB_PLAYERS, default=self.options.get(CONF_IGNORE_WEB_PLAYERS, DEFAULT_IGNORE_WEB_PLAYERS)): bool,
             vol.Required(CONF_IGNORE_DLNA_PLAYERS, default=self.options.get(CONF_IGNORE_DLNA_PLAYERS, DEFAULT_IGNORE_DLNA_PLAYERS)): bool,
             vol.Required(CONF_IGNORE_MOBILE_PLAYERS, default=self.options.get(CONF_IGNORE_MOBILE_PLAYERS, DEFAULT_IGNORE_MOBILE_PLAYERS)): bool,
             vol.Required(CONF_IGNORE_APP_PLAYERS, default=self.options.get(CONF_IGNORE_APP_PLAYERS, DEFAULT_IGNORE_APP_PLAYERS)): bool,
             vol.Required(CONF_PURGE_PLAYERS, default=self.options.get(CONF_PURGE_PLAYERS, DEFAULT_PURGE_PLAYERS)): bool,}))

    async def async_step_remove_sensor(self, user_input=None):
        sensors = self.options.get(CONF_SENSORS, []); entity_registry = async_get(self.hass)
        entries = { extract_sensor_key(entry.unique_id): entry for entry in async_entries_for_config_entry(entity_registry, self.config_entry.entry_id) if entry.unique_id and entry.unique_id.endswith(f"-{EntityType.LIBRARY}") }
        if not sensors and not entries: return self.async_abort(reason="no_sensors")
        if user_input is not None:
            target = user_input[CONF_SENSOR_REMOVE]; entry = entries.get(target)
            if entry is not None: entity_registry.async_remove(entry.entity_id)
            sensors = [s for s in sensors if build_sensor_key_from_config(s) != target]; self.options[CONF_SENSORS] = sensors
            return self.async_create_entry(title="", data=self.options)
        entry_list = { key: value.name or value.original_name or f"Sensor ({key})" for key, value in sorted(entries.items(), key=lambda item: item[1].name or item[1].original_name or "") }
        if not entry_list: return self.async_abort(reason="no_sensors_in_registry")
        return self.async_show_form(step_id="remove_sensor", data_schema=vol.Schema({vol.Required(CONF_SENSOR_REMOVE, default=next(iter(entry_list), None)): vol.In(entry_list)}))

    async def async_step_add_sensor(self, user_input=None):
        hub: MediaBrowserHub | None = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {}).get(DATA_HUB)
        if not hub or not hub.is_available: return self.async_abort(reason="hub_not_ready")
        if user_input is not None:
            sensor_config = {CONF_SENSOR_ITEM_TYPE: user_input[CONF_SENSOR_ITEM_TYPE], CONF_SENSOR_LIBRARY: user_input[CONF_SENSOR_LIBRARY], CONF_SENSOR_USER: user_input[CONF_SENSOR_USER]}
            sensor_key = build_sensor_key_from_config(sensor_config); sensors = self.options.get(CONF_SENSORS, [])
            configs = {build_sensor_key_from_config(config) for config in sensors}; entity_registry = async_get(self.hass)
            entries = { extract_sensor_key(entry.unique_id) for entry in async_entries_for_config_entry(entity_registry, self.config_entry.entry_id) if entry.unique_id and entry.unique_id.endswith(f"-{EntityType.LIBRARY}") }
            if sensor_key in configs or sensor_key in entries: return self.async_abort(reason="sensor_already_configured")
            sensors.append(sensor_config); self.options[CONF_SENSORS] = sensors; return self.async_create_entry(title="", data=self.options)
        try: users = await hub.async_get_users(); libraries = await hub.async_get_libraries()
        except Exception as e: _LOGGER.error("Failed fetch users/libs: %s", e); return self.async_abort(reason="fetch_failed")
        user_list = {KEY_ALL: "(All users)"}; [user_list.update({u["Id"]: u["Name"]}) for u in sorted(users, key=lambda x: x.get("Name", "")) if "Id" in u and "Name" in u]
        library_list = {KEY_ALL: "(All libraries)"}; [library_list.update({l[Item.ID]: l[Item.NAME]}) for l in sorted(libraries, key=lambda x: x.get(Item.NAME, "")) if Item.ID in l and Item.NAME in l]
        type_list = {k: v["title"] for k, v in sorted(SENSOR_ITEM_TYPES.items(), key=lambda x: x[1]["title"])}; default_item_type = ItemType.MOVIE if ItemType.MOVIE in type_list else next(iter(type_list), KEY_ALL)
        return self.async_show_form(step_id="add_sensor", data_schema=vol.Schema({
            vol.Required(CONF_SENSOR_ITEM_TYPE, default=default_item_type): vol.In(type_list),
            vol.Required(CONF_SENSOR_LIBRARY, default=KEY_ALL): vol.In(library_list),
            vol.Required(CONF_SENSOR_USER, default=KEY_ALL): vol.In(user_list),}))

    async def async_step_advanced(self, user_input=None):
        if user_input is not None:
            if CONF_TIMEOUT in user_input:
                 try: user_input[CONF_TIMEOUT] = int(user_input[CONF_TIMEOUT])
                 except (ValueError, TypeError): pass # Schema handles validation
            self.options.update(user_input); return self.async_create_entry(title="", data=self.options)
        schema_dict = {
            # Make Name optional in schema
            vol.Optional(CONF_NAME, description={"suggested_value": self.options.get(CONF_NAME)}): str,
            vol.Required(CONF_CLIENT_NAME, default=self.options.get(CONF_CLIENT_NAME, DEFAULT_CLIENT_NAME)): str,
            vol.Required(CONF_DEVICE_NAME, default=self.options.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)): str,
            vol.Required(CONF_DEVICE_ID, default=self.options.get(CONF_DEVICE_ID, "")): str,
            vol.Required(CONF_DEVICE_VERSION, default=self.options.get(CONF_DEVICE_VERSION, DEFAULT_DEVICE_VERSION)): str,
            vol.Required(CONF_TIMEOUT, default=self.options.get(CONF_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
        }
        return self.async_show_form(step_id="advanced", data_schema=vol.Schema(schema_dict))