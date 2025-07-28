"""Jellyfin API client."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import aiohttp

_LOGGER = logging.getLogger(__name__)


class JellyfinAPI:
    """Jellyfin API client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        api_key: str,
        port: int = 8096,
        use_ssl: bool = False,
        integration_version: str = "2.1.0"
    ) -> None:
        """Initialize the API client."""
        self.session = session
        self.host = host
        self.port = port
        self.api_key = api_key
        self.use_ssl = use_ssl

        protocol = "https" if use_ssl else "http"
        self.base_url = f"{protocol}://{host}:{port}"

        # Improved client identification with dynamic version
        self.headers = {
            "X-Emby-Token": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Emby-Authorization": f'Client="Home Assistant", Device="Home Assistant Hub", DeviceId="homeassistant-jellyfin-integration", Version="{integration_version}"',
        }

    async def _request(self, endpoint: str, method: str = "GET", data: dict = None) -> dict[str, Any]:
        """Make a request to the Jellyfin API."""
        url = f"{self.base_url}/{endpoint}"

        try:
            if method == "GET":
                async with self.session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method == "POST":
                async with self.session.post(url, headers=self.headers, json=data) as response:
                    response.raise_for_status()
                    if response.content_type == "application/json":
                        return await response.json()
                    return {}
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching data from %s: %s", url, err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error fetching data from %s: %s", url, err)
            raise

    async def get_system_info(self) -> dict[str, Any]:
        """Get system information."""
        return await self._request("System/Info")

    async def get_sessions(self) -> list[dict[str, Any]]:
        """Get active sessions."""
        return await self._request("Sessions")

    async def get_users(self) -> list[dict[str, Any]]:
        """Get all users."""
        return await self._request("Users")

    async def get_library_stats(self) -> dict[str, Any]:
        """Get library statistics."""
        try:
            # Get all items with basic info
            items = await self._request("Items?Recursive=true&Fields=Type")

            stats = {
                "movies": 0,
                "shows": 0,
                "episodes": 0,
                "music": 0,
            }

            for item in items.get("Items", []):
                item_type = item.get("Type", "").lower()

                if item_type == "movie":
                    stats["movies"] += 1
                elif item_type == "series":
                    stats["shows"] += 1
                elif item_type == "episode":
                    stats["episodes"] += 1
                elif item_type == "audio":
                    stats["music"] += 1

            return stats

        except Exception as err:
            _LOGGER.error("Error fetching library stats: %s", err)
            return {
                "movies": 0,
                "shows": 0,
                "episodes": 0,
                "music": 0,
            }

    async def get_upcoming_media(self) -> list[dict[str, Any]]:
        """Get upcoming TV episodes for upcoming-media-card."""
        try:
            # Get upcoming episodes with comprehensive fields
            fields = "Overview,Genres,Studios,Tags,CommunityRating,OfficialRating,ProductionYear,PremiereDate,DateCreated,RunTimeTicks,SeriesName,ParentIndexNumber,IndexNumber,SeriesId"
            endpoint = f"Shows/Upcoming?Limit=50&Fields={fields}"

            response = await self._request(endpoint)
            items = response.get("Items", [])

            # Format items for upcoming-media-card compatibility
            formatted_items = []
            for item in items:
                formatted_item = {
                    "title": item.get("Name", ""),
                    "episode": item.get("IndexNumber"),
                    "season": item.get("ParentIndexNumber"),
                    "series": item.get("SeriesName", ""),
                    "airdate": item.get("PremiereDate", ""),
                    "poster": self.get_image_url(item.get("Id", "")) if item.get("Id") else None,
                    "fanart": self.get_image_url(item.get("SeriesId", ""), "Backdrop") if item.get("SeriesId") else None,
                    "overview": item.get("Overview", ""),
                    "genres": item.get("Genres", []),
                    "studio": item.get("Studios", [{}])[0].get("Name", "") if item.get("Studios") else "",
                    "rating": item.get("CommunityRating"),
                    "runtime": int(item.get("RunTimeTicks", 0) / 10000000) if item.get("RunTimeTicks") else 0,
                    "id": item.get("Id", ""),
                }
                formatted_items.append(formatted_item)

            return formatted_items

        except Exception as err:
            _LOGGER.error("Error fetching upcoming media: %s", err)
            return []

    async def get_latest_media(self, media_type: str, limit: int = 30) -> list[dict[str, Any]]:
        """Get latest media items of specified type."""
        try:
            # Get latest items with comprehensive fields
            fields = "Overview,Genres,Studios,Tags,CommunityRating,OfficialRating,ProductionYear,PremiereDate,DateCreated,RunTimeTicks,SeriesName,ParentIndexNumber,IndexNumber,SeriesId"

            if media_type == "Episode":
                endpoint = f"Items?IncludeItemTypes={media_type}&Recursive=true&SortBy=DateCreated&SortOrder=Descending&Limit={limit}&Fields={fields}"
            else:
                endpoint = f"Items?IncludeItemTypes={media_type}&Recursive=true&SortBy=DateCreated&SortOrder=Descending&Limit={limit}&Fields={fields}"

            response = await self._request(endpoint)
            items = response.get("Items", [])

            # Format items with all required data
            formatted_items = []
            for item in items:
                formatted_item = {
                    "id": item.get("Id", ""),
                    "name": item.get("Name", ""),
                    "community_rating": item.get("CommunityRating"),
                    "official_rating": item.get("OfficialRating", ""),
                    "overview": item.get("Overview", ""),
                    "production_year": item.get("ProductionYear"),
                    "date_created": item.get("DateCreated", ""),
                    "premiere_date": item.get("PremiereDate", ""),
                    "runtime": int(item.get("RunTimeTicks", 0) / 10000000) if item.get("RunTimeTicks") else 0,
                    "genres": item.get("Genres", []),
                    "studios": item.get("Studios", []),
                    "image_primary": self.get_image_url(item.get("Id", "")),
                    "image_backdrop": self.get_image_url(item.get("Id", ""), "Backdrop"),
                    "image_thumb": self.get_image_url(item.get("Id", ""), "Thumb"),
                    "image_logo": self.get_image_url(item.get("Id", ""), "Logo"),
                }

                # Add episode-specific data
                if media_type == "Episode":
                    formatted_item.update({
                        "series_name": item.get("SeriesName", ""),
                        "season_name": item.get("SeasonName", ""),
                        "season_number": item.get("ParentIndexNumber"),
                        "episode_number": item.get("IndexNumber"),
                        "episode": f"S{item.get('ParentIndexNumber', 0):02d}E{item.get('IndexNumber', 0):02d}",
                        "image_primary_series": self.get_image_url(item.get("SeriesId", "")) if item.get("SeriesId") else None,
                        "image_backdrop_parent": self.get_image_url(item.get("SeriesId", ""), "Backdrop") if item.get("SeriesId") else None,
                        "image_thumb_parent": self.get_image_url(item.get("SeriesId", ""), "Thumb") if item.get("SeriesId") else None,
                        "image_logo_parent": self.get_image_url(item.get("SeriesId", ""), "Logo") if item.get("SeriesId") else None,
                    })

                formatted_items.append(formatted_item)

            return formatted_items

        except Exception as err:
            _LOGGER.error("Error fetching latest %s: %s", media_type, err)
            return []

    async def get_session_by_user_id(self, user_id: str) -> dict[str, Any] | None:
        """Get session for a specific user."""
        sessions = await self.get_sessions()
        for session in sessions:
            if session.get("UserId") == user_id:
                return session
        return None

    async def play_pause(self, session_id: str) -> None:
        """Toggle play/pause for a session."""
        await self._request(f"Sessions/{session_id}/Playing/PlayPause", method="POST")

    async def stop(self, session_id: str) -> None:
        """Stop playback for a session."""
        await self._request(f"Sessions/{session_id}/Playing/Stop", method="POST")

    async def next_track(self, session_id: str) -> None:
        """Skip to next track for a session."""
        await self._request(f"Sessions/{session_id}/Playing/NextTrack", method="POST")

    async def previous_track(self, session_id: str) -> None:
        """Skip to previous track for a session."""
        await self._request(f"Sessions/{session_id}/Playing/PreviousTrack", method="POST")

    async def seek(self, session_id: str, position_ticks: int) -> None:
        """Seek to position for a session."""
        data = {"SeekPositionTicks": position_ticks}
        await self._request(f"Sessions/{session_id}/Playing/Seek", method="POST", data=data)

    async def set_volume(self, session_id: str, volume: int) -> None:
        """Set volume level for a session."""
        # Use the correct endpoint format
        await self._request(f"Sessions/{session_id}/Command", method="POST", data={
            "Name": "SetVolume",
            "Arguments": {
                "Volume": str(volume)
            }
        })

    async def mute(self, session_id: str, mute: bool = True) -> None:
        """Mute/unmute a session."""
        command = "Mute" if mute else "Unmute"
        await self._request(f"Sessions/{session_id}/Command", method="POST", data={
            "Name": command
        })

    async def rescan_library(self) -> None:
        """Trigger a library rescan."""
        await self._request("Library/Refresh", method="POST")

    async def restart_server(self) -> None:
        """Restart the Jellyfin server."""
        await self._request("System/Restart", method="POST")

    async def shutdown_server(self) -> None:
        """Shutdown the Jellyfin server."""
        await self._request("System/Shutdown", method="POST")

    async def send_message_to_session(self, session_id: str, message: str, header: str = "Home Assistant", timeout: int = 5000) -> None:
        """Send a message to a specific session."""
        data = {
            "Text": message,
            "Header": header,
            "TimeoutMs": timeout
        }
        await self._request(f"Sessions/{session_id}/Message", method="POST", data=data)

    def get_image_url(self, item_id: str, image_type: str = "Primary", max_width: int = 300) -> str:
        """Get image URL for an item."""
        if not item_id:
            return None
        return f"{self.base_url}/Items/{item_id}/Images/{image_type}?maxWidth={max_width}&api_key={self.api_key}"

    async def test_connection(self) -> bool:
        """Test the connection to Jellyfin."""
        try:
            await self.get_system_info()
            return True
        except Exception:
            return False