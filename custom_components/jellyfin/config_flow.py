"""Config flow for Jellyfin integration."""
from __future__ import annotations

import logging
from typing import Any
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .jellyfin_api import JellyfinAPI

_LOGGER = logging.getLogger(__name__)


def _parse_url(url: str) -> dict[str, Any]:
    """Parse URL to extract host, port, and SSL settings."""
    # Remove trailing slash
    url = url.rstrip('/')

    # Check if it's a full URL
    if url.startswith(('http://', 'https://')):
        use_ssl = url.startswith('https://')
        # Remove protocol
        url_without_protocol = url.replace('https://', '').replace('http://', '')

        # Check for port
        if ':' in url_without_protocol:
            host, port_str = url_without_protocol.rsplit(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                # Port is not a number, treat as part of host
                host = url_without_protocol
                port = 443 if use_ssl else 8096
        else:
            host = url_without_protocol
            port = 443 if use_ssl else 8096
    else:
        # Assume it's just a host/IP
        host = url
        port = 8096
        use_ssl = False

        # Check for port in host
        if ':' in host:
            host_part, port_str = host.rsplit(':', 1)
            try:
                port = int(port_str)
                host = host_part
                # If port is 443, assume SSL
                if port == 443:
                    use_ssl = True
            except ValueError:
                # Port is not a number, keep original host
                host = url
                port = 8096

    return {
        "host": host,
        "port": port,
        "use_ssl": use_ssl
    }


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("url", default="http://localhost:8096"): str,
        vol.Required(CONF_API_KEY): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)

    # Parse the URL
    url_parts = _parse_url(data["url"])

    api = JellyfinAPI(
        session,
        url_parts["host"],
        data[CONF_API_KEY],
        url_parts["port"],
        url_parts["use_ssl"],
        "2.1.0"  # Default version for validation
    )

    try:
        system_info = await api.get_system_info()
    except Exception as err:
        _LOGGER.error("Failed to connect to Jellyfin server: %s", err)
        raise CannotConnect from err

    # Return info that you want to store in the config entry.
    return {
        "title": f"Jellyfin ({system_info.get('ServerName', 'Unknown')})",
        "server_name": system_info.get("ServerName", "Unknown"),
        "server_id": system_info.get("Id"),
        "version": system_info.get("Version"),
        "host": url_parts["host"],
        "port": url_parts["port"],
        "use_ssl": url_parts["use_ssl"],
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Jellyfin."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create a unique ID based on server ID
                server_id = info.get("server_id")
                if server_id:
                    await self.async_set_unique_id(server_id)
                    self._abort_if_unique_id_configured()

                # Store the parsed connection details
                config_data = {
                    CONF_HOST: info["host"],
                    CONF_PORT: info["port"],
                    CONF_SSL: info["use_ssl"],
                    CONF_API_KEY: user_input[CONF_API_KEY],
                }

                return self.async_create_entry(title=info["title"], data=config_data)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""