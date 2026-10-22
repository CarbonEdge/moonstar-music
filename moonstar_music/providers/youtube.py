import httpx

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
_PRIVACY = ("private", "unlisted", "public")
AI_DISCLOSURE = "AI-generated music."


class YouTubeProvider:
    """PublishProvider backed by the YouTube Data API v3 (resumable upload)."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 privacy_status: str = "private"):
        if privacy_status not in _PRIVACY:
            raise ValueError(f"privacy_status must be one of {_PRIVACY}, got {privacy_status!r}")
        self.privacy_status = privacy_status
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.client = httpx.AsyncClient()

    async def close(self) -> None:
        await self.client.aclose()

    async def _refresh_access_token(self) -> str:
        resp = await self.client.post(
            _TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    async def upload(self, video_path: str, title: str, description: str) -> str:
        access_token = await self._refresh_access_token()
        with open(video_path, "rb") as f:
            video_bytes = f.read()

        metadata = {
            "snippet": {
                "title": title,
                "description": f"{description.rstrip()}\n\n{AI_DISCLOSURE}",
                "categoryId": "10",
            },
            "status": {"privacyStatus": self.privacy_status},
        }
        auth = {"Authorization": f"Bearer {access_token}"}
        init = await self.client.post(
            _UPLOAD_URL,
            headers={**auth, "X-Upload-Content-Type": "video/mp4"},
            json=metadata,
            timeout=30.0,
        )
        init.raise_for_status()
        session_url = init.headers.get("Location")
        if not session_url:
            raise RuntimeError("YouTube resumable upload: no session Location header")

        resp = await self.client.put(
            session_url,
            headers={**auth, "Content-Type": "video/mp4"},
            content=video_bytes,
            timeout=600.0,
        )
        resp.raise_for_status()
        return f"https://youtu.be/{resp.json()['id']}"
