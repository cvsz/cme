"""CMe-owned TikTok transport.

Only approved official API capabilities may be enabled in production.
"""

from urllib.parse import urlparse

import httpx


class TikTokTransportError(RuntimeError):
    pass


class TikTokClient:
    API = "https://open.tiktokapis.com"
    AUTHORIZE = "https://www.tiktok.com/v2/auth/authorize/"

    def __init__(
        self,
        client_key: str,
        client_secret: str,
        redirect_uri: str,
        transport=None,
    ):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.transport = transport

    async def _request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        form=None,
        data=None,
    ):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        ) as client:
            response = await client.request(method, url, headers=headers, data=form, json=data)
            if response.status_code == 429:
                raise TikTokTransportError("TikTok rate limit exceeded")
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise TikTokTransportError("unexpected TikTok response")
        error = payload.get("error")
        if isinstance(error, dict) and error.get("code") not in (None, "", "ok"):
            raise TikTokTransportError("TikTok rejected request: " + str(error.get("code"))[:70])
        return payload

    async def exchange(self, code: str):
        return await self._request(
            "POST",
            self.API + "/v2/oauth/token/",
            form={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            },
        )

    async def refresh(self, refresh_token: str):
        return await self._request(
            "POST",
            self.API + "/v2/oauth/token/",
            form={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

    async def user_info(self, token: str):
        return await self._request(
            "GET",
            self.API + "/v2/user/info/?fields=open_id,avatar_url,display_name",
            token=token,
        )

    @staticmethod
    def validate_upload_url(url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host != "open-upload.tiktokapis.com":
            raise TikTokTransportError("unexpected upload destination")
