# custom_components/mediabrowser/hub.py
# --- FINAL CLEAN VERSION (Indentation, Logic, WS Logging) ---
"""Hub for the Media Browser (Emby/Jellyfin) integration."""

from copy import deepcopy
import urllib.parse
import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Awaitable
import uuid # Ensure imported

import aiohttp
import async_timeout
# Import necessary exceptions and constants
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.const import CONF_URL, CONF_NAME
from homeassistant.exceptions import HomeAssistantError # Import base HA error
from homeassistant.util import uuid as uuid_util

# Ensure all helpers needed are imported
from .helpers import (
    get_library_changed_event_data,
    get_user_data_changed_event_data,
    get_session_event_data,
    snake_case,
    size_of, # Import size_of if used elsewhere or remove
)

from .const import (
    APP_PLAYERS, CONF_API_KEY, CONF_CACHE_SERVER_ID, CONF_CACHE_SERVER_NAME,
    CONF_CACHE_SERVER_PING, CONF_CACHE_SERVER_USER_ID, CONF_CACHE_SERVER_VERSION,
    CONF_CLIENT_NAME, CONF_DEVICE_ID, CONF_DEVICE_NAME, CONF_DEVICE_VERSION,
    CONF_EVENTS_ACTIVITY_LOG, CONF_EVENTS_OTHER, CONF_EVENTS_SESSIONS,
    CONF_EVENTS_TASKS, CONF_IGNORE_APP_PLAYERS, CONF_IGNORE_DLNA_PLAYERS,
    CONF_IGNORE_MOBILE_PLAYERS, CONF_IGNORE_WEB_PLAYERS, CONF_TIMEOUT,
    DEFAULT_CLIENT_NAME, DEFAULT_DEVICE_NAME, DEFAULT_DEVICE_VERSION,
    DEFAULT_EVENTS_ACTIVITY_LOG, DEFAULT_EVENTS_OTHER, DEFAULT_EVENTS_SESSIONS,
    DEFAULT_EVENTS_TASKS, DEFAULT_IGNORE_APP_PLAYERS, DEFAULT_IGNORE_DLNA_PLAYERS,
    DEFAULT_IGNORE_MOBILE_PLAYERS, DEFAULT_IGNORE_WEB_PLAYERS, DEFAULT_PORT,
    DEFAULT_REQUEST_TIMEOUT, DEFAULT_SSL_PORT, DEVICE_PROFILE_BASIC, DLNA_PLAYERS,
    KEEP_ALIVE_TIMEOUT, KEY_ALL, LATEST_QUERY_PARAMS, MOBILE_PLAYERS, WEB_PLAYERS,
    ApiUrl, Item, Query, Response, ServerType, Session, Value, WebsocketMessage,
)
# Import specific errors used FROM errors.py (ClientMismatchError is defined below)
from .errors import ConnectError, RequestError, BrowseMediaError, ForbiddenError, UnauthorizedError, NotFoundError # Import necessary errors defined in errors.py

_LOGGER = logging.getLogger(__package__)


class MediaBrowserHub:
    """Represents an Emby/Jellyfin connection."""

    def __init__(self, options: dict[str, Any]) -> None:
        """Initialize."""
        # Parse URL
        url_str = options.get(CONF_URL)
        if not url_str: raise ValueError("URL is required in configuration")
        parsed_url = urllib.parse.urlparse(url_str)
        if not parsed_url.scheme or not parsed_url.netloc: raise ValueError(f"Invalid URL format: {url_str}")
        self._host: str = parsed_url.hostname or ""
        if not self._host: raise ValueError(f"Could not parse hostname from URL: {url_str}")
        self._use_ssl: bool = parsed_url.scheme == "https"
        # --- CORRECTED Port Logic ---
        if parsed_url.port is not None:
            # Use the port specified in the URL
            self._port: int = parsed_url.port
        else:
            # Default to standard ports if none specified
            self._port: int = DEFAULT_SSL_PORT if self._use_ssl else DEFAULT_PORT # Use constants
        # --- End Corrected Port Logic ---
        # Store API Key
        self.api_key: str | None = options.get(CONF_API_KEY)
        _LOGGER.debug("Hub initialized %s API Key.", "with" if self.api_key else "without")
        self.user_id: str | None = options.get(CONF_CACHE_SERVER_USER_ID)
        # Other options
        self.timeout: float = options.get(CONF_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)
        self.client_name: str = options.get(CONF_CLIENT_NAME, DEFAULT_CLIENT_NAME)
        self.device_name: str = options.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)
        self.device_id: str = options.get(CONF_DEVICE_ID) or uuid_util.random_uuid_hex() # Use HA util
        self.device_version: str = (options.get(CONF_DEVICE_VERSION, DEFAULT_DEVICE_VERSION))
        self._custom_name: str | None = options.get(CONF_NAME)
        # Player ignore options
        self.ignore_web_players: bool = options.get(CONF_IGNORE_WEB_PLAYERS, DEFAULT_IGNORE_WEB_PLAYERS)
        self.ignore_dlna_players: bool = options.get(CONF_IGNORE_DLNA_PLAYERS, DEFAULT_IGNORE_DLNA_PLAYERS)
        self.ignore_mobile_players: bool = options.get(CONF_IGNORE_MOBILE_PLAYERS, DEFAULT_IGNORE_MOBILE_PLAYERS)
        self.ignore_app_players: bool = options.get(CONF_IGNORE_APP_PLAYERS, DEFAULT_IGNORE_APP_PLAYERS)
        # Event options
        self.send_session_events: bool = options.get(CONF_EVENTS_SESSIONS, DEFAULT_EVENTS_SESSIONS)
        self.send_activity_events: bool = options.get(CONF_EVENTS_ACTIVITY_LOG, DEFAULT_EVENTS_ACTIVITY_LOG)
        self.send_task_events: bool = options.get(CONF_EVENTS_TASKS, DEFAULT_EVENTS_TASKS)
        self.send_other_events: bool = options.get(CONF_EVENTS_OTHER, DEFAULT_EVENTS_OTHER)
        # Cached server info
        self.server_id: str | None = options.get(CONF_CACHE_SERVER_ID)
        self.server_name: str | None = options.get(CONF_CACHE_SERVER_NAME)
        self.server_ping: str | None = options.get(CONF_CACHE_SERVER_PING)
        self.server_version: str | None = options.get(CONF_CACHE_SERVER_VERSION)
        self.server_type: ServerType = ServerType.UNKNOWN
        # Internal state
        self._last_keep_alive: datetime = datetime.utcnow()
        self._keep_alive_timeout: float | None = None
        self._is_api_key_validated: bool = False
        # Setup URLs and Headers
        schema_rest = "https" if self._use_ssl else "http"
        self._rest_url: str = f"{schema_rest}://{self._host}:{self._port}"
        base_path = parsed_url.path.rstrip('/')
        self._rest_url += base_path
        self.server_url: str = self._rest_url
        self._default_params: dict[str, Any] = {}
        self._default_headers: dict[str, Any] = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*"}
        self._ws_url: str = ""
        self._auth_update() # Call after setting defaults
        self._rest = aiohttp.ClientSession()
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ws_loop: asyncio.Task[None] | None = None
        self._abort: bool = False # Start assuming we want to run
        self._availability_listeners: set[Callable[[bool], Awaitable[None]]] = set()
        self._availability_task: asyncio.Task[None] | None = None
        self.is_available: bool = False
        self._sessions: dict[str, dict[str, Any]] = {}
        self._raw_sessions: dict[str, dict[str, Any]] = {}
        self._library_infos: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._sessions_listeners: set[Callable[[list[dict[str, Any]]], Awaitable[None]]] = set()
        self._session_changed_listeners: set[Callable[[dict[str, Any] | None, dict[str, Any] | None], Awaitable[None]]] = set()
        self._library_listeners: dict[tuple[str, str, str], set[Callable[[dict[str, Any]], Awaitable[None]]]] = {}
        self._websocket_listeners: set[Callable[[str, dict[str, Any] | None], Awaitable[None]]] = set()
        self._last_activity_log_entry: str | None = None

    @property
    def name(self) -> str:
        """Return the name of the server."""
        # Assuming DEFAULT_SERVER_NAME is defined somewhere, otherwise provide a fallback
        return self._custom_name or self.server_name or "Media Browser Server"

    # --- Listener Registration Methods ---
    def on_availability_changed(self, callback: Callable[[bool], Awaitable[None]]) -> Callable[[], None]:
        """Registers a callback for availability updates."""
        def remove_availability_listener() -> None:
            self._availability_listeners.discard(callback)
        self._availability_listeners.add(callback)
        return remove_availability_listener

    def on_sessions_changed(self, callback: Callable[[list[dict[str, Any]]], Awaitable[None]]) -> Callable[[], None]:
        """Registers a callback for session updates."""
        def remove_sessions_listener() -> None:
            self._sessions_listeners.discard(callback)
        self._sessions_listeners.add(callback)
        return remove_sessions_listener

    def on_session_changed(self, callback: Callable[[dict[str, Any] | None, dict[str, Any] | None], Awaitable[None]]) -> Callable[[], None]:
        """Registers a callback for individual session changes."""
        def remove_session_changed_listener() -> None:
            self._session_changed_listeners.discard(callback)
        self._session_changed_listeners.add(callback)
        return remove_session_changed_listener

    def on_library_changed(self, library_id: str, user_id: str, item_type: str, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> Callable[[], None]:
        """Registers a callback for library changes."""
        key = (library_id, user_id, item_type)
        library_listeners = self._library_listeners.setdefault(key, set())
        self._library_infos.setdefault(key, {}) # Ensure info dict exists
        library_listeners.add(callback)
        def remove_library_listener() -> None:
            library_listeners.discard(callback)
            # Clean up if no more listeners for this key
            if not library_listeners:
                self._library_infos.pop(key, None)
                self._library_listeners.pop(key, None)
        return remove_library_listener

    def on_websocket_message(self, callback: Callable[[str, dict[str, Any] | None], Awaitable[None]]) -> Callable[[], None]:
        """Registers a callback for WebSocket messages."""
        def remove_websocket_listener() -> None:
            self._websocket_listeners.discard(callback)
        self._websocket_listeners.add(callback)
        return remove_websocket_listener

    # --- API Call Methods ---
    async def async_command(self, session_id: str, command: str, data: dict | None = None, params: dict | None = None) -> str:
        """Send a command to a specific session."""
        await self._async_needs_authentication()
        url = f"{ApiUrl.SESSIONS}/{session_id}{ApiUrl.COMMAND}"
        cmd_data = {"Name": command, "Arguments": data or {}}
        return await self._async_rest_post_get_text(url, cmd_data, params)

    async def async_get_artists(self, params: dict) -> dict:
        """Get artists from the server."""
        await self._async_needs_authentication()
        return await self._async_rest_get_json(ApiUrl.ARTISTS, params)

    async def async_get_genres(self, params: dict) -> dict:
        """Get genres from the server."""
        await self._async_needs_authentication()
        return await self._async_rest_get_json(ApiUrl.GENRES, params)

    async def async_get_items(self, params: dict) -> dict:
        """Get items from the server."""
        await self._async_needs_authentication()
        response = await self._async_rest_get_json(ApiUrl.ITEMS, params)
        return response or {Response.ITEMS: [], Response.TOTAL_RECORD_COUNT: 0}

    async def async_get_libraries(self) -> list[dict]:
        """Get libraries and channels from the server."""
        await self._async_needs_authentication()
        libs = []
        chans = []
        try:
            libs_resp = await self._async_rest_get_json(ApiUrl.LIBRARIES, {Query.IS_HIDDEN: Value.FALSE}) or {}
            libs = libs_resp.get(Response.ITEMS, [])
        except Exception as e:
            _LOGGER.error("Error fetching libraries: %s", e)
        try:
            chans_resp = await self._async_rest_get_json(ApiUrl.CHANNELS) or {}
            chans = chans_resp.get(Response.ITEMS, [])
        except Exception as e:
            _LOGGER.error("Error fetching channels: %s", e)
        return sorted(libs + chans, key=lambda x: x.get(Item.NAME, ""))

    async def async_get_persons(self, params: dict) -> dict:
        """Get persons from the server."""
        await self._async_needs_authentication()
        return await self._async_rest_get_json(ApiUrl.PERSONS, params)

    async def async_get_sessions(self) -> list[dict]:
        """Get current sessions from the server."""
        await self._async_needs_authentication()
        response = await self._async_rest_get_json(ApiUrl.SESSIONS)
        return self._preprocess_sessions(response or [])

    async def async_refresh_session(self, session_id: str) -> None:
        """Fetches latest state for a single session and triggers update."""
        _LOGGER.debug("Refreshing session %s state via REST API", session_id)
        if not self.is_available:
            _LOGGER.warning("Cannot refresh session, hub is unavailable.")
            return

        try:
            # Fetch all sessions (often needed anyway to get full details)
            # Alternatively, could try a direct GET to /Sessions/{session_id} if supported and provides enough info
            all_sessions = await self.async_get_sessions()

            # Find the specific session
            updated_session_data = None
            for session in all_sessions:
                if session.get(Session.ID) == session_id:
                    updated_session_data = session
                    break

            if updated_session_data:
                old_session_data = self._sessions.get(session_id)
                if old_session_data != updated_session_data:
                    _LOGGER.debug("Session %s state changed after refresh.", session_id)
                    # Update internal cache
                    self._sessions[session_id] = updated_session_data
                    # Update raw cache if needed for events
                    self._raw_sessions[session_id] = get_session_event_data(deepcopy(updated_session_data))
                    # Trigger listeners
                    if self._session_changed_listeners:
                        # Simulate an update event for this specific session
                        asyncio.create_task(self._call_session_changed_listeners([], [], [(old_session_data, updated_session_data)]))
                else:
                    _LOGGER.debug("Session %s state unchanged after refresh.", session_id)
            else:
                # Session might have ended
                _LOGGER.debug("Session %s not found during refresh, might have ended.", session_id)
                old_session_data = self._sessions.pop(session_id, None)
                self._raw_sessions.pop(session_id, None)
                if old_session_data and self._session_changed_listeners:
                    # Simulate a removal event
                    asyncio.create_task(self._call_session_changed_listeners([], [old_session_data], []))


        except Exception as e:
            _LOGGER.error("Error refreshing session %s: %s", session_id, e)


    async def async_get_last_sessions(self) -> list[dict]:
        """Get last known sessions, fetching if available, otherwise using cache."""
        if self.is_available:
            try:
                return await self.async_get_sessions()
            except Exception as e:
                _LOGGER.warning("Failed to get sessions: %s, using cache", e)
        return list(self._sessions.values())

    async def async_get_playback_info(self, item_id: str) -> dict | None:
        """Get playback information for an item."""
        await self._async_needs_authentication()
        pb_data = {
            "DeviceProfile": DEVICE_PROFILE_BASIC,
            "AutoOpenLiveStream": True,
            "IsPlayback": True
        }
        uid = self.user_id
        if uid:
            pb_data["UserId"] = uid
        else:
            _LOGGER.warning("No UserID available for playback info request.")
            # Decide if you want to proceed without UserId or return None/raise error
            # return None # Example: return None if UserId is mandatory

        url = f"{ApiUrl.ITEMS}/{item_id}{ApiUrl.PLAYBACK_INFO}"
        return await self._async_rest_post_get_json(url, pb_data)

    async def async_get_prefixes(self, params: dict) -> list[dict]:
        """Get item name prefixes (differs between Emby/Jellyfin)."""
        await self._async_needs_authentication()
        if self.server_type == ServerType.UNKNOWN:
            await self._async_determine_server_type()

        if self.server_type == ServerType.EMBY:
            response = await self._async_rest_get_json(ApiUrl.PREFIXES, params)
            return response or []
        else: # Jellyfin - simulate prefixes by getting first letter of names
            items_resp = await self.async_get_items(params | {Query.FIELDS: Item.NAME})
            items = items_resp.get(Response.ITEMS, [])
            prefixes = {item[Item.NAME][0].upper() for item in items if item.get(Item.NAME)}
            return [{Item.NAME: p} for p in sorted(list(prefixes))]

    async def async_get_studios(self, params: dict) -> dict:
        """Get studios from the server."""
        await self._async_needs_authentication()
        return await self._async_rest_get_json(ApiUrl.STUDIOS, params)

    async def async_get_user_items(self, uid: str, params: dict) -> dict:
        """Get items for a specific user."""
        await self._async_needs_authentication()
        if not uid:
            _LOGGER.warning("Invalid UserID provided for get_user_items.")
            return {Response.ITEMS: [], Response.TOTAL_RECORD_COUNT: 0}
        url = f"{ApiUrl.USERS}/{uid}{ApiUrl.ITEMS}"
        return await self._async_rest_get_json(url, params)

    async def async_get_users(self) -> list[dict]:
        """Get users from the server."""
        await self._async_needs_authentication()
        response = await self._async_rest_get_json(ApiUrl.USERS)
        return response or []

    async def async_get_years(self, params: dict) -> dict:
        """Get years from the server."""
        await self._async_needs_authentication()
        return await self._async_rest_get_json(ApiUrl.YEARS, params)

    async def async_play(self, session_id: str, params: dict | None = None) -> str:
        """Send play command to a session."""
        await self._async_needs_authentication()
        url = f"{ApiUrl.SESSIONS}/{session_id}{ApiUrl.PLAYING}"
        return await self._async_rest_post_get_text(url, params=params) # Assuming play takes query params, not body

    async def async_play_command(self, session_id: str, command: str, params: dict | None = None) -> str:
        """Send a specific playback command (e.g., PlayPause, Stop)."""
        await self._async_needs_authentication()
        url = f"{ApiUrl.SESSIONS}/{session_id}{ApiUrl.PLAYING}/{command}"
        return await self._async_rest_post_get_text(url, params=params) # Assuming commands are POSTs with no body

    async def async_rescan(self) -> None:
        """Trigger a library rescan on the server."""
        await self._async_needs_authentication()
        await self._async_rest_post_get_text(ApiUrl.LIBRARY_REFRESH)

    async def async_restart(self) -> None:
        """Restart the media server."""
        await self._async_needs_authentication()
        await self._async_rest_post_get_text(ApiUrl.RESTART)

    async def async_shutdown(self) -> None:
        """Shutdown the media server."""
        await self._async_needs_authentication()
        await self._async_rest_post_get_text(ApiUrl.SHUTDOWN)

    async def async_start(self, websocket: bool = True) -> None:
        """Start the hub, verify server, authenticate, get sessions, and optionally start websocket."""
        if not self.api_key:
            raise ConfigEntryAuthFailed("API Key is missing, cannot start hub.")
        await self._async_needs_server_verification()
        await self._async_needs_authentication()
        await self._async_needs_sessions()
        if websocket:
            if self._ws_loop is None or self._ws_loop.done():
                _LOGGER.debug("Starting WebSocket loop.")
                self._ws_loop = asyncio.create_task(self._async_ws_loop())
            else:
                 _LOGGER.debug("WebSocket loop already running.")

    async def async_test_api_key(self) -> dict:
        """Test the API key by fetching server info."""
        if not self.api_key:
            raise ConfigEntryAuthFailed("API Key is missing for validation.")
        try:
            # Use GET for /System/Info as POST is often not allowed or needed
            info = await self._async_rest_get_json(ApiUrl.INFO)
            if info and isinstance(info, dict) and "Id" in info and "ServerName" in info:
                self._is_api_key_validated = True
                _LOGGER.debug("API key test successful via /System/Info.")
                # Optionally try to fetch user info if needed here, but primary test is server info
                # try:
                #     if not self.user_id:
                #         users = await self.async_get_users() # Example
                #         # Logic to find user ID if needed
                #         _LOGGER.debug("API Key confirmed. UserID TBD.")
                # except Exception as user_err:
                #     _LOGGER.warning("Could not fetch user info during API key test: %s", user_err)
                return info
            else:
                _LOGGER.warning("API key test failed: Invalid or incomplete /System/Info response: %s", info)
                raise ConfigEntryAuthFailed("API key test failed: Bad response from server.")
        except ConfigEntryAuthFailed: # Re-raise if it's already the correct type
            raise
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                raise ConfigEntryAuthFailed("Invalid API Key") from err
            if err.status == 403:
                raise ConfigEntryAuthFailed("API Key lacks necessary permissions") from err
            _LOGGER.error("API key test failed - HTTP %d: %s", err.status, err.message)
            raise RequestError(f"API key test failed: Server returned status {err.status}") from err
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as err:
             _LOGGER.error("API key test failed - Connection Error: %s", err)
             raise ConnectError(f"API key test failed: Could not connect to server - {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during API key test: %s", err)
            # Wrap unexpected errors in ConfigEntryAuthFailed or a more specific error if possible
            raise ConfigEntryAuthFailed(f"API key test failed due to an unexpected error: {err}") from err

    # --- Internal Helpers ---
    async def _async_get_activity_log_entries(self, params: dict) -> dict:
        """Fetch activity log entries."""
        await self._async_needs_authentication()
        return await self._async_rest_get_json(ApiUrl.ACTIVITY_LOG_ENTRIES, params)

    async def _async_needs_authentication(self) -> None:
        """Ensure the API key is present and validated."""
        if not self.api_key:
            raise ConfigEntryAuthFailed("API Key is missing.")
        if not self._is_api_key_validated:
            _LOGGER.debug("API key not yet validated, attempting validation...")
            try:
                await self.async_test_api_key()
                _LOGGER.debug("API key validation successful.")
            except ConfigEntryAuthFailed as err:
                _LOGGER.warning("API key validation failed: %s", err)
                self._set_available(False) # Mark as unavailable on auth failure
                raise # Re-raise the specific auth error
            except Exception as err:
                # Catch other potential errors during validation (ConnectError, RequestError)
                _LOGGER.error("Unexpected error during API key validation check: %s", err, exc_info=True)
                self._set_available(False)
                # Raise a generic auth failed error wrapping the original
                raise ConfigEntryAuthFailed(f"API key validation failed due to an underlying error: {err}") from err

    async def _async_needs_sessions(self) -> None:
        """Ensure initial sessions are fetched if not already present."""
        if not self._sessions: # Only fetch if sessions dict is empty
            _LOGGER.debug("Initial sessions not fetched, attempting fetch...")
            try:
                session_list = await self.async_get_sessions()
                # Use Session.ID constant if available
                self._sessions = {s[Session.ID]: s for s in session_list if Session.ID in s}
                self._raw_sessions = {s[Session.ID]: get_session_event_data(s) for s in session_list if Session.ID in s}
                _LOGGER.debug("Fetched initial sessions: %d", len(self._sessions))
            except Exception as e:
                _LOGGER.warning("Failed to fetch initial sessions: %s", e)
                # Consider if this should mark the hub as unavailable or retry

    async def _async_determine_server_type(self) -> None:
        """Determine if the server is Emby or Jellyfin."""
        _LOGGER.debug("Attempting to determine server type...")
        server_ping_result = self.server_ping
        # Try ping first if not cached
        if not server_ping_result:
            try:
                server_ping_result = await self._async_ping()
            except Exception as e:
                _LOGGER.debug("Ping failed during server type detection: %s", e)
                server_ping_result = None # Ensure it's None if ping fails

        if server_ping_result == "Jellyfin Server":
            self.server_type = ServerType.JELLYFIN
        elif server_ping_result == "Emby Server":
            self.server_type = ServerType.EMBY
        else:
            # Ping didn't help or failed, try /System/Info
            _LOGGER.debug("Ping did not determine server type, trying /System/Info...")
            try:
                # Ensure auth headers are up-to-date before the call
                self._auth_update() # Might be redundant if called elsewhere, but safe
                info = await self._async_rest_get_json(ApiUrl.INFO)
                if info and isinstance(info, dict):
                    # Jellyfin often has "ProductName": "Jellyfin Server"
                    if "ProductName" in info and "Jellyfin" in info["ProductName"]:
                        self.server_type = ServerType.JELLYFIN
                    # Emby often has "ServerName": "Emby Server"
                    elif "ServerName" in info and "Emby" in info["ServerName"]:
                        self.server_type = ServerType.EMBY
                    else:
                        _LOGGER.warning("Could not determine server type from /System/Info, defaulting to Jellyfin.")
                        self.server_type = ServerType.JELLYFIN # Default assumption
                else:
                    _LOGGER.warning("Received invalid /System/Info response, defaulting to Jellyfin.")
                    self.server_type = ServerType.JELLYFIN
            except Exception as e:
                _LOGGER.warning("Error fetching /System/Info for type detection (%s), defaulting to Jellyfin.", e)
                self.server_type = ServerType.JELLYFIN

        _LOGGER.debug("Determined server type: %s", self.server_type)
        self._auth_update() # Update auth headers based on determined type

    async def _async_needs_server_verification(self) -> None:
        """Verify connection to the server and check for ID mismatch."""
        if self.server_type == ServerType.UNKNOWN:
            await self._async_determine_server_type() # Ensure type is known first

        try:
            # Use GET for /System/Info
            info = await self._async_rest_get_json(ApiUrl.INFO)
            if not info or not isinstance(info, dict):
                raise ConnectError("Invalid or empty response from /System/Info")

            server_id_from_info = info.get("Id")
            if not server_id_from_info:
                raise ConnectError("Server ID not found in /System/Info response")

            # Check for mismatch only if we have a cached server_id
            if self.server_id is not None and self.server_id != server_id_from_info:
                raise ClientMismatchError(f"Server ID mismatch. Expected '{self.server_id}', but server reported '{server_id_from_info}'.")

            # Update cached info
            self.server_id = server_id_from_info
            self.server_name = info.get("ServerName", self.server_name) # Keep existing if not present
            self.server_version = info.get("Version", self.server_version)

            # Refine server type determination if it was based on a guess or default
            if self.server_type == ServerType.JELLYFIN: # Or whichever was the default
                 if "ProductName" in info and "Jellyfin" in info["ProductName"]:
                     pass # Already correct
                 elif "ServerName" in info and "Emby" in info["ServerName"]:
                     _LOGGER.info("Corrected server type to Emby based on /System/Info.")
                     self.server_type = ServerType.EMBY
                     self._auth_update() # Update auth since type changed
            elif self.server_type == ServerType.EMBY:
                 if "ServerName" in info and "Emby" in info["ServerName"]:
                     pass # Already correct
                 elif "ProductName" in info and "Jellyfin" in info["ProductName"]:
                     _LOGGER.info("Corrected server type to Jellyfin based on /System/Info.")
                     self.server_type = ServerType.JELLYFIN
                     self._auth_update() # Update auth since type changed


            _LOGGER.debug("Server verification successful. ID: %s, Name: %s, Version: %s, Type: %s",
                          self.server_id, self.server_name, self.server_version, self.server_type)

        except aiohttp.ClientResponseError as err:
            _LOGGER.error("Server verification failed - HTTP %d fetching /System/Info: %s", err.status, err.message)
            if err.status == 401:
                raise ConfigEntryAuthFailed("Authentication failed during server verification.") from err
            if err.status == 403:
                raise ConfigEntryAuthFailed("Permissions error during server verification.") from err
            # Treat other HTTP errors as connection issues
            raise ConnectError(f"Failed to fetch server info: HTTP {err.status}") from err
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError, ConnectError) as err:
            # Catch specific connection errors and the ConnectErrors raised above
            _LOGGER.error("Server verification failed - Connection Error fetching /System/Info: %s", err)
            raise ConnectError(f"Connection error during server verification: {err}") from err
        except ClientMismatchError: # Let this specific error propagate
             raise
        except Exception as e:
            # Catch any other unexpected errors
            _LOGGER.exception("Unexpected error during server verification: %s", e)
            raise ConnectError(f"An unexpected error occurred during server verification: {e}") from e

    async def _async_ping(self) -> str | None:
        """Ping the server using the /System/Ping endpoint."""
        try:
            # Use GET for Ping
            ping_response = await self._async_rest_get_text(ApiUrl.PING)
            self.server_ping = ping_response # Cache the result

            # Update server type based on ping response if still unknown
            if self.server_type == ServerType.UNKNOWN:
                if ping_response == "Jellyfin Server":
                    self.server_type = ServerType.JELLYFIN
                    self._auth_update() # Update auth based on new type
                elif ping_response == "Emby Server":
                    self.server_type = ServerType.EMBY
                    self._auth_update() # Update auth based on new type
            return ping_response
        except (aiohttp.ClientError, asyncio.TimeoutError, RequestError) as e:
            # Catch expected request/connection errors
            _LOGGER.debug("Server ping failed: %s", e)
            return None
        except Exception as e:
            # Catch unexpected errors
            _LOGGER.exception("Unexpected error during server ping: %s", e)
            return None

    def _auth_update(self) -> None:
        """Update default headers and WebSocket URL based on API key and server type."""
        self._default_params = {} # Reset params
        # Basic headers common to both
        self._default_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*"
        }
        schema_ws = "wss" if self._use_ssl else "ws"
        # Construct base WS URL (replace http/https with ws/wss)
        base_ws_url = self.server_url.replace("http", "ws", 1)
        self._ws_url = "" # Reset WS URL

        if not self.api_key:
            _LOGGER.debug("No API key provided. WebSocket connection will be unauthenticated.")
            # Basic WS URL without auth params (might not work depending on server config)
            self._ws_url = f"{base_ws_url}/socket" # Jellyfin default path, Emby might differ
            return

        # Determine server type (default to Jellyfin if unknown for auth purposes)
        server_type_for_auth = self.server_type if self.server_type != ServerType.UNKNOWN else ServerType.JELLYFIN
        device_id = self.device_id or "ha-mediabrowser-unknown" # Fallback device ID

        if server_type_for_auth == ServerType.JELLYFIN:
            # Jellyfin uses X-Emby-Authorization header and api_key in WS URL
            self._ws_url = f"{base_ws_url}/socket?api_key={self.api_key}&deviceId={device_id}"
            auth_header_value = (
                f'MediaBrowser Client="{self.client_name}", Device="{self.device_name}", '
                f'DeviceId="{device_id}", Version="{self.device_version}", Token="{self.api_key}"'
            )
            self._default_headers["X-Emby-Authorization"] = auth_header_value
            # Ensure Emby-specific headers are removed if they exist
            self._default_headers.pop("X-Emby-Token", None)
            self._default_headers.pop("X-Emby-Device-Id", None)
            self._default_headers.pop("X-Emby-Device", None)
            self._default_headers.pop("X-Emby-Client", None)

        else: # Emby style authentication
            # Emby uses X-Emby-Token header and api_key in WS URL (different path)
            self._ws_url = f"{base_ws_url}/embywebsocket?api_key={self.api_key}&deviceId={device_id}"
            self._default_headers["X-Emby-Token"] = self.api_key
            self._default_headers["X-Emby-Device-Id"] = device_id
            self._default_headers["X-Emby-Device"] = self.device_name
            self._default_headers["X-Emby-Client"] = self.client_name
            # Ensure Jellyfin-specific header is removed
            self._default_headers.pop("X-Emby-Authorization", None)

        _LOGGER.debug("Auth updated for %s. WS URL: %s", server_type_for_auth, self._ws_url)
        # Avoid logging sensitive headers directly unless debugging verbosely
        # _LOGGER.debug("Headers: %s", self._default_headers)

    # --- REST Helpers ---
    async def _async_rest_post_response(self, url_path: str, data: Any = None, params: dict | None = None) -> aiohttp.ClientResponse:
        """Internal helper to perform a POST request and return the response object."""
        target_url = self.server_url + url_path
        request_params = self._default_params.copy()
        if params:
            request_params.update(params)

        _LOGGER.debug("POST %s | Params: %s | Headers: %s | Body: %s",
                      target_url, request_params or None, self._default_headers, str(data)[:200]) # Log truncated body

        # Determine SSL context based on _use_ssl, False disables verification if not using HTTPS
        ssl_context = None if self._use_ssl else False

        try:
            async with async_timeout.timeout(self.timeout):
                response = await self._rest.post(
                    target_url,
                    json=data, # Assumes JSON data
                    params=request_params or None,
                    headers=self._default_headers,
                    ssl=ssl_context,
                    raise_for_status=False # Handle status check manually
                )
            # Check status code after the request
            if not response.ok:
                _LOGGER.warning("POST %s failed with status %d", target_url, response.status)
                # Raise specific errors based on status
                if response.status == 401: raise UnauthorizedError(f"Unauthorized POST to {url_path}")
                if response.status == 403: raise ForbiddenError(f"Forbidden POST to {url_path}")
                if response.status == 404: raise NotFoundError(f"Not Found POST to {url_path}")
                # Raise generic RequestError for other client/server errors
                response.raise_for_status() # Raises ClientResponseError for 4xx/5xx
            return response
        except aiohttp.ClientResponseError as err:
             # Already raised specific errors or ClientResponseError
             raise err # Re-raise
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as err:
            _LOGGER.error("Connection error during POST to %s: %s", target_url, err)
            raise ConnectError(f"Connection error during POST to {url_path}: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during POST to %s: %s", target_url, err)
            raise RequestError(f"Unexpected error during POST to {url_path}: {err}") from err


    async def _async_rest_get_response(self, url_path: str, params: dict | None = None) -> aiohttp.ClientResponse:
        """Internal helper to perform a GET request and return the response object."""
        target_url = self.server_url + url_path
        request_params = self._default_params.copy()
        if params:
            request_params.update(params)

        _LOGGER.debug("GET %s | Params: %s | Headers: %s", target_url, request_params or None, self._default_headers)

        ssl_context = None if self._use_ssl else False

        try:
            async with async_timeout.timeout(self.timeout):
                response = await self._rest.get(
                    target_url,
                    params=request_params or None,
                    headers=self._default_headers,
                    ssl=ssl_context,
                    raise_for_status=False # Handle status check manually
                )

            if not response.ok:
                _LOGGER.warning("GET %s failed with status %d", target_url, response.status)
                if response.status == 401: raise UnauthorizedError(f"Unauthorized GET from {url_path}")
                if response.status == 403: raise ForbiddenError(f"Forbidden GET from {url_path}")
                if response.status == 404: raise NotFoundError(f"Not Found GET from {url_path}")
                response.raise_for_status() # Raises ClientResponseError for 4xx/5xx
            return response
        except aiohttp.ClientResponseError as err:
             raise err # Re-raise
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as err:
            _LOGGER.error("Connection error during GET to %s: %s", target_url, err)
            raise ConnectError(f"Connection error during GET to {url_path}: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during GET to %s: %s", target_url, err)
            raise RequestError(f"Unexpected error during GET to {url_path}: {err}") from err

    async def _async_rest_post_get_json(self, url_path: str, data: Any = None, params: dict | None = None) -> dict | list | None:
        """Perform POST, check for JSON response, return parsed JSON or None/empty dict on error."""
        try:
            response = await self._async_rest_post_response(url_path, data, params)
            content_type = response.headers.get('Content-Type', '')
            if 'json' in content_type.lower():
                # Handle potentially empty response body
                if response.content_length == 0:
                    _LOGGER.debug("Received empty JSON response for POST %s", url_path)
                    return {} # Or None, depending on expected behavior
                try:
                    # Use content_type=None to avoid charset issues if server sends wrong header
                    json_body = await response.json(content_type=None)
                    return json_body or {} # Return empty dict if JSON parsing results in None
                except json.JSONDecodeError as e:
                    _LOGGER.warning("Failed to decode JSON response for POST %s: %s. Body: %s", url_path, e, await response.text())
                    return {} # Or None
            else:
                body_text = await response.text()
                _LOGGER.warning("Received non-JSON response for POST %s (Content-Type: %s). Body: %s", url_path, content_type, body_text[:200])
                return {} # Or None
        except (RequestError, ConnectError, HomeAssistantError) as e: # Catch specific errors from _async_rest_post_response
            _LOGGER.error("Error during POST request for JSON to %s: %s", url_path, e)
            return None # Or raise e depending on desired handling

    async def _async_rest_post_get_text(self, url_path: str, data: Any = None, params: dict | None = None) -> str:
        """Perform POST and return response text."""
        try:
            response = await self._async_rest_post_response(url_path, data, params)
            return await response.text()
        except (RequestError, ConnectError, HomeAssistantError) as e:
            _LOGGER.error("Error during POST request for text to %s: %s", url_path, e)
            return "" # Return empty string on error, or raise e

    async def _async_rest_get_json(self, url_path: str, params: dict | None = None) -> dict | list | None:
        """Perform GET, check for JSON response, return parsed JSON or None on error."""
        try:
            response = await self._async_rest_get_response(url_path, params)
            content_type = response.headers.get('Content-Type', '')
            if 'json' in content_type.lower():
                if response.content_length == 0:
                     _LOGGER.debug("Received empty JSON response for GET %s", url_path)
                     return {} # Or None
                try:
                    json_body = await response.json(content_type=None)
                    return json_body # Return parsed JSON (can be dict, list, or None if server returns null)
                except json.JSONDecodeError as e:
                    _LOGGER.warning("Failed to decode JSON response for GET %s: %s. Body: %s", url_path, e, await response.text())
                    return None
            else:
                body_text = await response.text()
                _LOGGER.warning("Received non-JSON response for GET %s (Content-Type: %s). Body: %s", url_path, content_type, body_text[:200])
                return None
        except (RequestError, ConnectError, HomeAssistantError) as e:
            _LOGGER.error("Error during GET request for JSON from %s: %s", url_path, e)
            return None # Or raise e

    async def _async_rest_get_text(self, url_path: str, params: dict | None = None) -> str:
        """Perform GET and return response text."""
        try:
            response = await self._async_rest_get_response(url_path, params)
            return await response.text()
        except (RequestError, ConnectError, HomeAssistantError) as e:
            _LOGGER.error("Error during GET request for text from %s: %s", url_path, e)
            return "" # Return empty string on error, or raise e

    # --- Websocket Methods ---
    async def _async_ws_connect(self) -> None:
        """Establish the WebSocket connection."""
        if not self._ws_url:
            raise ConnectionError("WebSocket URL is not configured.")
        _LOGGER.debug("Attempting to connect WebSocket: %s", self._ws_url)
        self._abort = False # Reset abort flag before connection attempt
        ssl_context = None if self._use_ssl else False

        # Use the existing ClientSession (_rest) for ws_connect
        async with async_timeout.timeout(self.timeout): # Use configured timeout
            self._ws = await self._rest.ws_connect(
                self._ws_url,
                headers=self._default_headers, # Use prepared auth headers
                ssl=ssl_context,
                heartbeat=KEEP_ALIVE_TIMEOUT * 0.8 if KEEP_ALIVE_TIMEOUT else None # Optional: aiohttp heartbeat
            )
        _LOGGER.debug("WebSocket connection established.")

        # Send initial messages to subscribe to updates
        # Use constants for message types
        await self._ws.send_json({"MessageType": "SessionsStart", "Data": "0,1500"})
        if self.send_activity_events:
            await self._ws.send_json({"MessageType": "ActivityLogEntryStart", "Data": "0,1000"})
        if self.send_task_events:
            await self._ws.send_json({"MessageType": "ScheduledTasksInfoStart", "Data": "0,1500"})
        # --- End of fix ---

        _LOGGER.debug("WebSocket connected and initial subscription messages sent.")

    async def _async_ws_disconnect(self) -> None:
        """Close the WebSocket connection if it exists and is open."""
        if self._ws is not None and not self._ws.closed:
            _LOGGER.debug("Closing WebSocket connection.")
            await self._ws.close()
            self._ws = None
            _LOGGER.debug("WebSocket connection closed.")
        else:
             _LOGGER.debug("WebSocket already closed or not connected.")

    async def _async_ws_loop(self) -> None:
        """Main loop for handling WebSocket connection and messages."""
        reconnect_delay = 1 # Initial reconnect delay in seconds

        while not self._abort:
            try:
                # --- Connection Phase ---
                _LOGGER.debug("WS Loop: Verifying server and authentication...")
                # Ensure server is reachable, ID matches, and auth works before connecting WS
                await self._async_needs_server_verification()
                await self._async_needs_authentication()
                # Fetch initial sessions if needed (might have been lost during disconnect)
                await self._async_needs_sessions()

                _LOGGER.debug("WS Loop: Attempting WebSocket connection...")
                await self._async_ws_connect() # Establish connection and send initial messages

                # --- Connected Phase ---
                self._set_available(True) # Mark hub as available
                reconnect_delay = 1 # Reset reconnect delay on successful connection
                _LOGGER.info("WebSocket connection established to %s", self.name)

                # --- Message Handling Loop ---
                _LOGGER.debug("WS Loop: Entering message receive loop.")
                while not self._abort and self._ws is not None and not self._ws.closed:
                    try:
                        _LOGGER.debug("WS Loop: Waiting for message...")
                        # Use a timeout slightly longer than expected keep-alive interval
                        msg = await self._ws.receive(timeout=KEEP_ALIVE_TIMEOUT * 1.5)
                        _LOGGER.debug("WS Loop: Received message type: %s", msg.type)

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            _LOGGER.debug("WS Loop: TEXT message received: %s", msg.data[:200] + ("..." if len(msg.data) > 200 else ""))
                            # Handle message in a separate task to avoid blocking the loop
                            asyncio.create_task(self._handle_message(msg.data))
                            self._last_keep_alive = datetime.utcnow() # Assume text message resets keep-alive timer

                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                            _LOGGER.warning("WS Loop: Connection closed by server (Type: %s, Data: %s). Breaking inner loop.", msg.type, msg.data)
                            break # Exit inner loop to trigger reconnect logic

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            ws_exception = self._ws.exception()
                            _LOGGER.error("WS Loop: WebSocket error received: %s. Breaking inner loop.", ws_exception)
                            break # Exit inner loop

                        elif msg.type == aiohttp.WSMsgType.PING:
                             _LOGGER.debug("WS Loop: PING received, sending PONG.")
                             await self._ws.pong()

                        elif msg.type == aiohttp.WSMsgType.PONG:
                             _LOGGER.debug("WS Loop: PONG received.")
                             self._last_keep_alive = datetime.utcnow() # Update keep-alive time on pong

                    except asyncio.TimeoutError:
                        _LOGGER.debug("WS Loop: Receive timeout.")
                        # Check if keep-alive is needed (if dynamic timeout isn't set)
                        if self._keep_alive_timeout is None:
                            now = datetime.utcnow()
                            if (now - self._last_keep_alive).total_seconds() >= KEEP_ALIVE_TIMEOUT:
                                self._send_keep_alive()

                    except asyncio.CancelledError:
                         _LOGGER.debug("WS Loop: Task cancelled during message handling. Breaking inner loop.")
                         self._abort = True # Ensure outer loop also exits
                         break

                    except Exception as err:
                        _LOGGER.exception("WS Loop: Unexpected error handling message: %s. Breaking inner loop.", err)
                        break # Exit inner loop on unexpected errors

                _LOGGER.debug("WS Loop: Exited inner message receive loop.")
                # --- End of Message Handling Loop ---

            # --- Error Handling / Reconnect Logic ---
            except ClientMismatchError as err:
                _LOGGER.error("Server ID mismatch detected, stopping WebSocket loop: %s", err)
                self._set_available(False)
                break # Exit outer loop permanently
            except ConfigEntryAuthFailed as err:
                _LOGGER.error("Authentication failed, stopping WebSocket loop: %s", err)
                self._set_available(False)
                break # Exit outer loop permanently
            except (aiohttp.ClientConnectionError, aiohttp.WSServerHandshakeError, ConnectError) as err:
                _LOGGER.warning("WS Loop: Connection failed: %s. Will retry.", err)
            except aiohttp.ClientResponseError as err:
                _LOGGER.warning("WS Loop: HTTP error during connection attempt: %s (%s).", err.status, err.message)
                if err.status in (401, 403):
                    _LOGGER.error("WS Loop: Authorization error (%d) during connection. Stopping loop.", err.status)
                    self._set_available(False)
                    break # Exit outer loop permanently
                # Other HTTP errors might be temporary, will retry
            except (asyncio.TimeoutError, TimeoutError) as err:
                _LOGGER.warning("WS Loop: Timeout during connection attempt: %s. Will retry.", err)
            except asyncio.CancelledError:
                _LOGGER.debug("WS Loop: Task cancelled during setup/connection phase.")
                self._abort = True # Ensure outer loop exits if cancelled here
                break
            except Exception as err:
                _LOGGER.exception("WS Loop: Unexpected error during setup/connection: %s. Will retry.", err)

            # --- Cleanup and Delay before Retry ---
            self._set_available(False) # Mark as unavailable if connection loop exited/failed
            await self._async_ws_disconnect() # Ensure connection is closed before retrying

            if not self._abort:
                _LOGGER.debug("Attempting WebSocket reconnect in %d seconds", reconnect_delay)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60) # Exponential backoff up to 60s

        # --- Loop Exit ---
        _LOGGER.debug("WebSocket loop finished.")
        self._set_available(False) # Ensure unavailable on final exit
        await self._async_ws_disconnect() # Final cleanup


    # --- Listener Calling Methods ---
    async def _call_availability_listeners(self, available: bool) -> None:
        """Call all registered availability listeners."""
        # Create a copy in case listeners modify the set during iteration
        listeners_to_call = list(self._availability_listeners)
        _LOGGER.debug("Calling %d availability listeners with status: %s", len(listeners_to_call), available)
        for listener in listeners_to_call:
            try:
                await listener(available)
            except Exception as err:
                _LOGGER.error("Error calling availability listener %s: %s", getattr(listener, '__name__', repr(listener)), err, exc_info=True)

    async def _call_sessions_listeners(self, sessions: list[dict[str, Any]]) -> None:
        """Call all registered sessions listeners."""
        listeners_to_call = list(self._sessions_listeners)
        _LOGGER.debug("Calling %d sessions listeners.", len(listeners_to_call))
        for listener in listeners_to_call:
            try:
                await listener(sessions)
            except Exception as err:
                _LOGGER.error("Error calling sessions listener %s: %s", getattr(listener, '__name__', repr(listener)), err, exc_info=True)

    async def _call_session_changed_listeners(self, added: list, removed: list, updated: list[tuple]) -> None:
        """Call all registered individual session change listeners."""
        listeners_to_call = list(self._session_changed_listeners)
        # Combine changes into a list of (old_session, new_session) tuples
        events = ([(None, s) for s in added] + # Added: old is None
                  [(s, None) for s in removed] + # Removed: new is None
                  updated) # Updated: (old, new)
        if not events: return # Don't call if nothing changed

        _LOGGER.debug("Calling %d session changed listeners for %d events.", len(listeners_to_call), len(events))
        for old_session, new_session in events:
            for listener in listeners_to_call:
                try:
                    await listener(old_session, new_session)
                except Exception as err:
                    _LOGGER.error("Error calling session changed listener %s: %s", getattr(listener, '__name__', repr(listener)), err, exc_info=True)

    async def _call_library_listeners(self, library_ids: set[str]) -> None:
        """Call library listeners whose keys match the changed library IDs or KEY_ALL."""
        # Copy dictionaries to avoid issues if listeners modify them
        listeners_dict_copy = self._library_listeners.copy()
        infos_copy = self._library_infos.copy()
        listeners_to_call_map: dict[tuple, list] = {}

        # Identify which listeners need to be called
        for key, listeners in listeners_dict_copy.items():
            listener_library_id, _, _ = key
            # Call if the specific library ID changed OR if the listener is for KEY_ALL
            if listener_library_id in library_ids or listener_library_id == KEY_ALL:
                listeners_to_call_map[key] = list(listeners) # Copy the set of listeners

        if not listeners_to_call_map:
            _LOGGER.debug("No relevant library listeners found for changed IDs: %s", library_ids)
            return

        _LOGGER.debug("Calling library listeners for keys: %s", list(listeners_to_call_map.keys()))
        for key, listeners in listeners_to_call_map.items():
            info_to_pass = infos_copy.get(key) # Get the potentially updated info
            if info_to_pass is None:
                # This might happen if info fetch failed or key was removed
                _LOGGER.warning("No library info found for key %s when calling listeners.", key)
                continue

            for listener in listeners:
                try:
                    # Pass the current library info associated with the key
                    await listener(info_to_pass)
                except Exception as err:
                    _LOGGER.error("Error calling library listener %s for key %s: %s", getattr(listener, '__name__', repr(listener)), key, err, exc_info=True)

    async def _call_websocket_listeners(self, message_type: str, data: dict[str, Any] | None) -> None:
        """Call all registered generic WebSocket message listeners."""
        listeners_to_call = list(self._websocket_listeners)
        if not listeners_to_call: return

        _LOGGER.debug("Calling %d WebSocket listeners for message type: %s", len(listeners_to_call), message_type)
        for listener in listeners_to_call:
            try:
                await listener(message_type, data)
            except Exception as err:
                _LOGGER.error("Error calling WebSocket listener %s for type %s: %s", getattr(listener, '__name__', repr(listener)), message_type, err, exc_info=True)

    async def _call_websocket_listeners_for_list(self, messages: list[tuple[str, dict[str, Any] | None]]) -> None:
        """Efficiently call WebSocket listeners for a list of messages."""
        listeners_to_call = list(self._websocket_listeners)
        if not listeners_to_call or not messages:
            return

        _LOGGER.debug("Calling %d WebSocket listeners for %d messages.", len(listeners_to_call), len(messages))
        for message_type, data in messages:
            for listener in listeners_to_call:
                try:
                    await listener(message_type, data)
                except Exception as err:
                    # Log error but continue processing other messages/listeners
                    _LOGGER.error("Error calling WebSocket listener %s for type %s: %s", getattr(listener, '__name__', repr(listener)), message_type, err, exc_info=True)


    # --- Other Internal Methods ---
    def _set_available(self, availability: bool) -> None:
        """Update the availability status and notify listeners if changed."""
        if self.is_available == availability:
            return # No change

        _LOGGER.info("%s server became %s", self.name, "available" if availability else "unavailable")
        self.is_available = availability

        # Schedule calling listeners
        if self._availability_listeners:
            # Cancel any pending availability task to avoid race conditions
            if self._availability_task and not self._availability_task.done():
                self._availability_task.cancel()
            # Schedule the new call
            self._availability_task = asyncio.create_task(self._call_availability_listeners(availability))

    async def _handle_message(self, message_str: str) -> None:
        _LOGGER.debug("WS Received Raw: %s", message_str)
        """Parse and handle incoming WebSocket messages."""
        try:
            message = json.loads(message_str)
        except json.JSONDecodeError:
            _LOGGER.warning("Received invalid JSON over WebSocket: %s", message_str[:200])
            return

        message_type = message.get("MessageType")
        data = message.get("Data") # Data can be None, dict, list, str, int etc.

        if not message_type:
            _LOGGER.debug("WebSocket message received without MessageType: %s", message)
            return

        _LOGGER.debug("Handling WebSocket message: Type=%s", message_type)

        # Default: call generic listeners if enabled
        call_generic_listeners = self.send_other_events
        event_data_for_listener = data # Default data to pass

        # --- Specific Message Type Handling ---
        if message_type == WebsocketMessage.SESSIONS:
            if isinstance(data, list):
                asyncio.create_task(self._handle_sessions_message(data))
            else:
                _LOGGER.warning("Received %s message with non-list data: %s", message_type, type(data))
            call_generic_listeners = False # Handled specifically

        elif message_type == WebsocketMessage.KEEP_ALIVE:
            self._last_keep_alive = datetime.utcnow()
            _LOGGER.debug("KeepAlive received.")
            call_generic_listeners = False

        elif message_type == WebsocketMessage.FORCE_KEEP_ALIVE:
            try:
                # Server suggests a new keep-alive interval in milliseconds
                new_timeout_ms = int(data)
                # Set local timeout slightly shorter than server's interval (e.g., 80%)
                new_timeout_sec = max(5.0, (new_timeout_ms / 1000.0) * 0.8)
                self._keep_alive_timeout = new_timeout_sec
                _LOGGER.debug("Server requested dynamic keep-alive interval. New effective timeout: %.1fs", new_timeout_sec)
            except (ValueError, TypeError, Exception) as e:
                _LOGGER.warning("Failed to parse %s data (%s): %s. Using default.", message_type, data, e)
                self._keep_alive_timeout = KEEP_ALIVE_TIMEOUT # Revert to default
            call_generic_listeners = False

        elif message_type == WebsocketMessage.LIBRARY_CHANGED:
            if self._library_listeners: # Only process if there are listeners
                if isinstance(data, dict):
                    # Handle library change in background task
                    asyncio.create_task(self._handle_library_changed_message(data))
                    # Prepare data for generic listener if enabled
                    event_data_for_listener = get_library_changed_event_data(data) # Use helper
                else:
                    _LOGGER.warning("Received %s message with non-dict data: %s", message_type, type(data))
                    event_data_for_listener = {} # Pass empty dict
            else:
                call_generic_listeners = False # No library listeners, don't process

        elif message_type == WebsocketMessage.ACTIVITY_LOG_ENTRY:
            # Trigger fetching new log entries if enabled
            if self.send_activity_events:
                 asyncio.create_task(self._handle_activity_log_message())
            call_generic_listeners = False # Activity logs are handled separately

        elif message_type == WebsocketMessage.SCHEDULED_TASK_INFO:
            # Pass through to generic listeners if enabled
            call_generic_listeners = self.send_task_events

        elif message_type == WebsocketMessage.USER_DATA_CHANGED:
             # Pass through to generic listeners (optionally process data)
             _LOGGER.debug("WS: Received UserDataChanged message. Raw Data: %s", data)
             if isinstance(data, dict):
                 event_data_for_listener = get_user_data_changed_event_data(data) # Use helper
             else:
                 _LOGGER.warning("Received %s message with non-dict data: %s", message_type, type(data))
                 event_data_for_listener = {}
             # Let generic listener decide if it cares

        # --- Call Generic Listeners ---
        if call_generic_listeners and self._websocket_listeners:
            # Prepare event payload (snake_case type, add server_id)
            event_type_snake = snake_case(message_type)
            listener_payload = {"server_id": self.server_id}
            # Add the processed data under the snake_case type key
            listener_payload[event_type_snake] = event_data_for_listener or {} # Ensure it's at least an empty dict
            asyncio.create_task(self._call_websocket_listeners(event_type_snake, listener_payload))

        # --- Keep-Alive Check ---
        # Check if we need to send a manual keep-alive (if dynamic timeout isn't active)
        if self._keep_alive_timeout is None:
            now = datetime.utcnow()
            if (now - self._last_keep_alive).total_seconds() >= KEEP_ALIVE_TIMEOUT:
                self._send_keep_alive()


    async def _handle_sessions_message(self, sessions_data: list[dict]) -> None:
        """Process a 'Sessions' WebSocket message."""
        _LOGGER.debug("Processing Sessions message with %d entries.", len(sessions_data))

        # Preprocess and filter incoming sessions
        processed_sessions = self._preprocess_sessions(deepcopy(sessions_data)) # Deepcopy to avoid modifying original data

        # Create dictionaries keyed by session ID for efficient comparison
        new_raw_sessions = {s["Id"]: get_session_event_data(s) for s in sessions_data if "Id" in s} # Raw data for events
        new_processed_sessions = {s["Id"]: s for s in processed_sessions if "Id" in s} # Filtered data for state/listeners

        # Compare with previous state to find changes
        added_raw, removed_raw, updated_raw = self._get_changed_sessions(self._raw_sessions, new_raw_sessions)
        added_proc, removed_proc, updated_proc = self._get_changed_sessions(self._sessions, new_processed_sessions)

        # Update internal state
        self._raw_sessions = new_raw_sessions
        self._sessions = new_processed_sessions

        # --- Notify Listeners ---
        # Notify listeners interested in the full list of *processed* sessions if changed
        if added_proc or removed_proc or updated_proc:
            if self._sessions_listeners:
                asyncio.create_task(self._call_sessions_listeners(list(self._sessions.values())))
            # Notify listeners interested in individual *processed* session changes
            if self._session_changed_listeners:
                asyncio.create_task(self._call_session_changed_listeners(added_proc, removed_proc, updated_proc))

        # Send individual session change events via generic WebSocket listener if enabled
        if self.send_session_events and self._websocket_listeners and (added_raw or removed_raw or updated_raw):
            messages_to_send = []
            # Use the raw session data for these events
            for s in added_raw: messages_to_send.append(("session_changed", {"old": None, "new": s}))
            for s in removed_raw: messages_to_send.append(("session_changed", {"old": s, "new": None}))
            for old, new in updated_raw: messages_to_send.append(("session_changed", {"old": old, "new": new}))

            if messages_to_send:
                asyncio.create_task(self._call_websocket_listeners_for_list(messages_to_send))


    async def _handle_activity_log_message(self) -> None:
        """Fetch and process new activity log entries when triggered."""
        if not self.send_activity_events or not self._websocket_listeners:
            return # Don't process if not enabled or no listeners

        _LOGGER.debug("Handling activity log trigger...")
        params = {}
        last_entry_timestamp = self._last_activity_log_entry

        # Fetch entries since the last known timestamp, or just the latest if first time
        if last_entry_timestamp:
            params[Query.MIN_DATE] = last_entry_timestamp
        else:
            params[Query.LIMIT] = 1 # Fetch only the latest initially to set the timestamp

        try:
            response = await self._async_get_activity_log_entries(params)
            if response is None: # Handle potential None return from API call
                _LOGGER.warning("Failed to fetch activity log entries (API returned None).")
                return
        except Exception as e:
            _LOGGER.error("Failed to fetch activity log entries: %s", e)
            return

        entries = response.get(Response.ITEMS)
        if not entries:
            _LOGGER.debug("No new activity log entries found.")
            return

        # Find the timestamp of the newest entry received
        newest_entry_timestamp = None
        try:
             # Ensure Item.DATE exists and is comparable
            valid_timestamps = [e.get(Item.DATE) for e in entries if e.get(Item.DATE)]
            if valid_timestamps:
                newest_entry_timestamp = max(valid_timestamps)
        except (ValueError, TypeError) as e: # Handle potential errors comparing timestamps
             _LOGGER.warning("Error processing activity log timestamps: %s", e)
             newest_entry_timestamp = last_entry_timestamp # Keep old timestamp on error

        # Filter entries: only include those strictly newer than the last known timestamp
        entries_to_fire = []
        if last_entry_timestamp:
            # Sort by date to ensure chronological order if needed, though API might already do this
            sorted_entries = sorted((e for e in entries if e.get(Item.DATE)), key=lambda x: x.get(Item.DATE, ""))
            entries_to_fire = [e for e in sorted_entries if e.get(Item.DATE, "") > last_entry_timestamp]
        else:
            # If it's the first fetch, fire the single latest entry we got
            entries_to_fire = entries[:1] # Assuming the API returns newest first or we limited to 1

        # Update the last known timestamp if a newer one was found
        if newest_entry_timestamp and newest_entry_timestamp > (last_entry_timestamp or ""):
            self._last_activity_log_entry = newest_entry_timestamp
            _LOGGER.debug("Updated last activity log timestamp to: %s", newest_entry_timestamp)


        # Fire events for the filtered new entries
        if entries_to_fire:
            _LOGGER.debug("Firing %d new activity log events.", len(entries_to_fire))
            messages = [
                ("activity_log_entry", entry | {"server_id": self.server_id}) # Add server_id
                for entry in entries_to_fire
            ]
            asyncio.create_task(self._call_websocket_listeners_for_list(messages))
        else:
            _LOGGER.debug("No activity log entries newer than %s to fire.", last_entry_timestamp)


    async def _handle_library_changed_message(self, data: dict, force_updates: bool = False) -> None:
        """Handle LibraryChanged message: fetch updates for relevant sensors."""
        if not self._library_listeners:
            return # No sensors listening

        changed_folders = set(data.get(Item.COLLECTION_FOLDERS, [])) # Library IDs that changed
        _LOGGER.debug("Handling LibraryChanged message (Force:%s). Folders: %s", force_updates, changed_folders)

        # Determine which sensor keys (library_id, user_id, item_type) need updating
        keys_to_update = set()
        if not changed_folders and not force_updates:
            # If no specific folders changed and not forcing, only update KEY_ALL sensors
            keys_to_update = {key for key in self._library_listeners if key[0] == KEY_ALL}
            if not keys_to_update:
                _LOGGER.debug("LibraryChanged: No specific folders and no KEY_ALL sensors. Skipping update.")
                return
        else:
            # Update sensors matching changed folders, KEY_ALL sensors, or all if forcing
            keys_to_update = {
                key for key in self._library_listeners
                if force_updates or key[0] == KEY_ALL or key[0] in changed_folders
            }

        if not keys_to_update:
            _LOGGER.debug("LibraryChanged: No sensors match the changed folders or require update.")
            return

        _LOGGER.debug("LibraryChanged: Updating library sensors for keys: %s", keys_to_update)

        # --- Fetch updated info concurrently ---
        old_infos = self._library_infos.copy() # Keep track of old state for comparison
        new_infos = self._library_infos.copy() # Start with current state, update as fetches complete
        fetch_tasks = {
            key: asyncio.create_task(self._fetch_library_info(*key))
            for key in keys_to_update
        }

        # Wait for all fetches to complete (or fail)
        results = await asyncio.gather(*fetch_tasks.values(), return_exceptions=True)

        # --- Process results and identify changed sensors ---
        updated_keys = set() # Track keys whose info actually changed
        keys_with_fetch_errors = set()

        for i, key in enumerate(fetch_tasks.keys()):
            result_or_exception = results[i]
            if isinstance(result_or_exception, Exception):
                _LOGGER.error("Failed to fetch library info for key %s: %s", key, result_or_exception)
                # Optionally remove the info for this key or keep the old one
                new_infos.pop(key, None)
                keys_with_fetch_errors.add(key)
            else:
                # Fetch successful, result is the new library info (dict or None)
                new_info_data = result_or_exception
                if new_info_data is None:
                     # API might return None if user/library doesn't exist or on error
                     _LOGGER.warning("Received None fetching library info for key %s. Treating as empty.", key)
                     new_info_data = {Response.ITEMS: [], Response.TOTAL_RECORD_COUNT: 0} # Default to empty

                new_infos[key] = new_info_data # Update the info cache

                # Check if the info actually changed compared to the old state or if forced
                if force_updates or old_infos.get(key) != new_info_data:
                    updated_keys.add(key)
                else:
                    _LOGGER.debug("Library info for key %s did not change.", key)


        # Update the main library info cache
        self._library_infos = new_infos

        # --- Notify listeners for keys whose info changed ---
        if updated_keys:
            _LOGGER.debug("Library info changed for keys: %s. Notifying listeners.", updated_keys)
            # Create map of {key: [listeners]} for changed keys only
            listeners_to_notify = {
                key: list(self._library_listeners.get(key, []))
                for key in updated_keys if key in self._library_listeners # Ensure key still has listeners
            }

            for key, listeners in listeners_to_notify.items():
                info_to_pass = new_infos.get(key) # Get the final updated info
                if info_to_pass is None: # Should not happen if handled above, but safety check
                    _LOGGER.warning("Missing library info for key %s during notification.", key)
                    continue

                for listener_callback in listeners:
                    try:
                        # Schedule the listener call
                        asyncio.create_task(listener_callback(info_to_pass))
                    except Exception as e:
                        _LOGGER.error("Error scheduling library listener call for key %s: %s", key, e, exc_info=True)
        else:
             _LOGGER.debug("Library info fetched, but no changes detected requiring listener notification.")


    async def _fetch_library_info(self, library_id: str, user_id: str, item_type: str) -> dict | None:
        """Fetch the latest items for a specific library/user/type combination."""
        key = (library_id, user_id, item_type)
        _LOGGER.debug("Fetching library info for key: %s", key)
        try:
            params = LATEST_QUERY_PARAMS.copy() # Start with base params (e.g., sort, limit)
            params[Query.INCLUDE_ITEM_TYPES] = item_type

            if library_id != KEY_ALL:
                params[Query.PARENT_ID] = library_id

            if user_id != KEY_ALL:
                # Fetch items specific to the user
                if not user_id: # Basic validation
                    _LOGGER.warning("Invalid (empty) UserID provided for library fetch key %s.", key)
                    return None # Or return empty dict?
                return await self.async_get_user_items(user_id, params)
            else:
                # Fetch items from the general endpoint (not user-specific)
                return await self.async_get_items(params)

        except Exception as e:
            # Log the specific exception during the fetch
            _LOGGER.error("Exception occurred while fetching library info for key %s: %s", key, e)
            raise # Re-raise the exception to be caught by the gather in _handle_library_changed_message

    def force_library_change(self, library_id: str = KEY_ALL) -> None:
        """Manually trigger an update check for specific library sensors."""
        _LOGGER.debug("Forcing library update check for Library ID: %s", library_id)
        # Schedule the handler with the specified library ID and force_updates=True
        asyncio.create_task(self._handle_library_changed_message(
            {Item.COLLECTION_FOLDERS: [library_id] if library_id != KEY_ALL else []}, # Pass folder if specific
            force_updates=True
        ))

    def _get_changed_sessions(self, old_sessions: dict, new_sessions: dict) -> tuple[list, list, list[tuple]]:
        """Compare two dictionaries of sessions and return added, removed, updated."""
        old_ids = set(old_sessions.keys())
        new_ids = set(new_sessions.keys())

        added_ids = new_ids - old_ids
        removed_ids = old_ids - new_ids
        common_ids = old_ids & new_ids

        added = [new_sessions[id] for id in added_ids]
        removed = [old_sessions[id] for id in removed_ids]
        updated = []
        for id in common_ids:
            if old_sessions[id] != new_sessions[id]:
                updated.append((old_sessions[id], new_sessions[id])) # Tuple of (old, new)

        return added, removed, updated

    def _preprocess_sessions(self, sessions: list[dict]) -> list[dict]:
        """Filter a list of sessions based on configured ignore rules."""
        if not sessions:
            return []

        filtered_sessions = []
        for session in sessions:
            # Ignore self
            if session.get(Session.DEVICE_ID) == self.device_id and session.get(Session.CLIENT) == self.client_name:
                continue
            # Ignore based on client type flags
            client = session.get(Session.CLIENT)
            if self.ignore_web_players and client in WEB_PLAYERS:
                continue
            if self.ignore_dlna_players and client in DLNA_PLAYERS:
                continue
            if self.ignore_mobile_players and client in MOBILE_PLAYERS:
                continue
            if self.ignore_app_players and client in APP_PLAYERS:
                continue

            filtered_sessions.append(session) # Keep the session if no rules matched

        return filtered_sessions

    def _send_keep_alive(self) -> None:
        """Send a KeepAlive message over the WebSocket if connected."""
        if self._abort or self._ws is None or self._ws.closed:
            _LOGGER.debug("Cannot send KeepAlive: WebSocket not connected or hub stopping.")
            return

        _LOGGER.debug("Sending KeepAlive message to %s", self.name)
        try:
            # Send the message in a separate task to avoid blocking
            asyncio.create_task(self._ws.send_json({"MessageType": WebsocketMessage.KEEP_ALIVE}))
            self._last_keep_alive = datetime.utcnow() # Update time *after* scheduling send
        except Exception as e:
            # Log errors during sending (e.g., connection closing)
            _LOGGER.warning("Failed to send KeepAlive message: %s", e)


    async def async_stop(self) -> None:
        """Stop the hub, cancel tasks, and close connections."""
        _LOGGER.debug("Stopping hub %s...", self.name)
        self._abort = True # Signal loops and tasks to stop

        # Cancel the main WebSocket loop task
        if self._ws_loop is not None and not self._ws_loop.done():
            _LOGGER.debug("Cancelling WebSocket loop task...")
            self._ws_loop.cancel()
            try:
                await self._ws_loop # Wait for the task to finish cancelling
            except asyncio.CancelledError:
                _LOGGER.debug("WebSocket loop task successfully cancelled.")
            except Exception as e:
                 _LOGGER.warning("Error waiting for WebSocket loop task cancellation: %s", e)
        self._ws_loop = None # Clear the task reference

        # Explicitly close WebSocket connection (might be redundant if loop handled it)
        await self._async_ws_disconnect()

        # Cancel availability listener task if running
        if self._availability_task and not self._availability_task.done():
             self._availability_task.cancel()
             self._availability_task = None

        # Close the aiohttp ClientSession
        if self._rest and not self._rest.closed:
            _LOGGER.debug("Closing aiohttp ClientSession...")
            await self._rest.close()
            _LOGGER.debug("aiohttp ClientSession closed.")

        # Clear listeners (optional, helps with garbage collection)
        self._availability_listeners.clear()
        self._sessions_listeners.clear()
        self._session_changed_listeners.clear()
        self._library_listeners.clear()
        self._websocket_listeners.clear()

        _LOGGER.debug("Hub %s stop complete.", self.name)


class ClientMismatchError(ConnectError):
    """Error to indicate that the connected server's unique ID does not match the expected ID."""
    pass

# --- End of MediaBrowserHub class ---
