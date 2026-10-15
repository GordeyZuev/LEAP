"""YouTube playlist manager."""

import asyncio
from typing import Any

from googleapiclient.errors import HttpError

from logger import get_logger

from ...config_factory import YouTubeConfig
from ...credentials_provider import CredentialProvider
from .token_handler import TokenRefreshError, requires_valid_token

logger = get_logger()


class YouTubePlaylistManager:
    """YouTube playlist manager."""

    def __init__(
        self,
        service,
        config: YouTubeConfig,
        credentials=None,
        credential_provider: CredentialProvider | None = None,
    ):
        self.service = service
        self.config = config
        self.credentials = credentials
        self.credential_provider = credential_provider

    @requires_valid_token(max_retries=1)
    async def create_playlist(self, title: str, description: str = "", privacy_status: str = "unlisted") -> str | None:
        """Create playlist."""
        try:
            response = await self.create_playlist_record(title, description, privacy_status)
            playlist_id = response["id"]
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

            logger.info(f"Playlist created: {playlist_url}")
            return playlist_id

        except TimeoutError:
            logger.error("Timeout creating playlist")
            return None
        except TokenRefreshError as e:
            logger.error(f"Token error during create_playlist: {e}")
            return None
        except HttpError as e:
            logger.error(f"Playlist creation error: {e}")
            return None

    @requires_valid_token(max_retries=1)
    async def list_playlists(self, *, page_token: str | None = None) -> dict[str, Any]:
        """List the authenticated channel's playlists, preserving YouTube pagination."""
        request = self.service.playlists().list(
            part="snippet,contentDetails,status",
            mine=True,
            maxResults=50,
            pageToken=page_token,
        )
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)

    @requires_valid_token(max_retries=1)
    async def get_playlist_record(self, playlist_id: str) -> dict[str, Any] | None:
        """Get one playlist resource from the authenticated channel."""
        request = self.service.playlists().list(
            part="snippet,contentDetails,status",
            id=playlist_id,
            maxResults=1,
        )
        loop = asyncio.get_running_loop()
        response = await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)
        items = response.get("items") or []
        return items[0] if items else None

    @requires_valid_token(max_retries=1)
    async def create_playlist_record(
        self, title: str, description: str = "", privacy_status: str = "unlisted"
    ) -> dict[str, Any]:
        """Create a playlist and return the provider response."""
        body = {
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy_status},
        }
        request = self.service.playlists().insert(part="snippet,status", body=body)
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)

    @requires_valid_token(max_retries=1)
    async def update_playlist_record(
        self,
        playlist_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        privacy_status: str | None = None,
    ) -> dict[str, Any]:
        """Update playlist fields and return the updated YouTube resource."""
        current_request = self.service.playlists().list(
            part="snippet,status",
            id=playlist_id,
            maxResults=1,
        )
        loop = asyncio.get_running_loop()
        current_response = await asyncio.wait_for(loop.run_in_executor(None, current_request.execute), timeout=30.0)
        items = current_response.get("items") or []
        if not items:
            raise ValueError("YouTube playlist not found")
        current = items[0]
        snippet = current.get("snippet") or {}
        current_status = current.get("status") or {}
        body: dict[str, Any] = {
            "id": playlist_id,
            "snippet": {
                "title": title if title is not None else snippet.get("title", ""),
                "description": description if description is not None else snippet.get("description", ""),
            },
            "status": {"privacyStatus": privacy_status or current_status.get("privacyStatus", "private")},
        }
        if "defaultLanguage" in snippet:
            body["snippet"]["defaultLanguage"] = snippet["defaultLanguage"]
        if "podcastStatus" in current_status:
            body["status"]["podcastStatus"] = current_status["podcastStatus"]
        request = self.service.playlists().update(part="snippet,status", body=body)
        return await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)

    @requires_valid_token(max_retries=1)
    async def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """Add video to playlist."""
        try:
            body = {
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            }

            request = self.service.playlistItems().insert(part="snippet", body=body)

            loop = asyncio.get_event_loop()
            await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)

            logger.info(f"Video added to playlist {playlist_id}")
            return True
        except TimeoutError:
            logger.error(f"Timeout adding video to playlist {playlist_id}")
            return False
        except TokenRefreshError as e:
            logger.error(f"Token error during add_video_to_playlist: {e}")
            return False
        except HttpError as e:
            logger.error(f"Error adding to playlist: {e}")
            return False

    @requires_valid_token(max_retries=1)
    async def remove_video_from_playlist(self, playlist_item_id: str) -> bool:
        """Remove video from playlist."""
        try:
            request = self.service.playlistItems().delete(id=playlist_item_id)

            loop = asyncio.get_event_loop()
            await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)

            logger.info("Video removed from playlist")
            return True
        except TimeoutError:
            logger.error("Timeout removing video from playlist")
            return False
        except TokenRefreshError as e:
            logger.error(f"Token error during remove_video_from_playlist: {e}")
            return False
        except HttpError as e:
            logger.error(f"Error removing from playlist: {e}")
            return False

    @requires_valid_token(max_retries=1)
    async def get_playlist_info(self, playlist_id: str) -> dict[str, Any] | None:
        """Get playlist information."""
        try:
            request = self.service.playlists().list(part="snippet,contentDetails,status", id=playlist_id)

            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)

            if response["items"]:
                playlist = response["items"][0]
                return {
                    "title": playlist["snippet"]["title"],
                    "description": playlist["snippet"]["description"],
                    "item_count": playlist["contentDetails"]["itemCount"],
                    "privacy_status": playlist["status"]["privacyStatus"],
                    "published_at": playlist["snippet"]["publishedAt"],
                }
            return None

        except TimeoutError:
            logger.error(f"Timeout getting playlist info for {playlist_id}")
            return None
        except TokenRefreshError as e:
            logger.error(f"Token error during get_playlist_info: {e}")
            return None
        except HttpError as e:
            logger.error(f"Error getting playlist info: {e}")
            return None

    async def get_playlist_videos(self, playlist_id: str, max_results: int = 50) -> list[dict[str, Any]]:
        """Get list of videos in playlist."""
        try:
            videos = []
            next_page_token = None

            while True:
                request = self.service.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=min(max_results, 50),
                    pageToken=next_page_token,
                )

                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)

                for item in response["items"]:
                    videos.append(
                        {
                            "video_id": item["contentDetails"]["videoId"],
                            "title": item["snippet"]["title"],
                            "description": item["snippet"]["description"],
                            "position": item["snippet"]["position"],
                        }
                    )

                if len(videos) >= max_results or "nextPageToken" not in response:
                    break

                next_page_token = response["nextPageToken"]

            return videos[:max_results]

        except TimeoutError:
            logger.error(f"Timeout getting playlist videos for {playlist_id}")
            return []
        except HttpError as e:
            logger.error(f"Error getting playlist videos: {e}")
            return []

    async def update_playlist(
        self,
        playlist_id: str,
        title: str | None = None,
        description: str | None = None,
        privacy_status: str | None = None,
    ) -> bool:
        """Update playlist."""
        try:
            await self.update_playlist_record(
                playlist_id,
                title=title,
                description=description,
                privacy_status=privacy_status,
            )
            logger.info(f"Playlist updated: {playlist_id}")
            return True

        except TimeoutError:
            logger.error(f"Timeout updating playlist {playlist_id}")
            return False
        except TokenRefreshError as e:
            logger.error(f"Token error updating playlist {playlist_id}: {e}")
            return False
        except HttpError as e:
            logger.error(f"Playlist update error: {e}")
            return False
        except ValueError as e:
            logger.error(f"Playlist update failed: {e}")
            return False

    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete playlist."""
        try:
            request = self.service.playlists().delete(id=playlist_id)

            loop = asyncio.get_event_loop()
            await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)

            logger.info(f"Playlist deleted: {playlist_id}")
            return True

        except TimeoutError:
            logger.error(f"Timeout deleting playlist {playlist_id}")
            return False
        except HttpError as e:
            logger.error(f"Playlist deletion error: {e}")
            return False

    async def get_user_playlists(self, max_results: int = 50) -> list[dict[str, Any]]:
        """Get user playlists."""
        try:
            playlists = []
            next_page_token = None

            while True:
                request = self.service.playlists().list(
                    part="snippet,contentDetails",
                    mine=True,
                    maxResults=min(max_results, 50),
                    pageToken=next_page_token,
                )

                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(loop.run_in_executor(None, request.execute), timeout=30.0)

                for playlist in response["items"]:
                    playlists.append(
                        {
                            "playlist_id": playlist["id"],
                            "title": playlist["snippet"]["title"],
                            "description": playlist["snippet"]["description"],
                            "item_count": playlist["contentDetails"]["itemCount"],
                            "published_at": playlist["snippet"]["publishedAt"],
                        }
                    )

                if len(playlists) >= max_results or "nextPageToken" not in response:
                    break

                next_page_token = response["nextPageToken"]

            return playlists[:max_results]

        except TimeoutError:
            logger.error("Timeout getting user playlists")
            return []
        except HttpError as e:
            logger.error(f"Error getting user playlists: {e}")
            return []
