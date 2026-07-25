"""OAuth provider clients for Yandex ID, VK ID, Google."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OAuthUserInfo:
    """Normalised user info returned by any provider."""

    provider: str
    provider_user_id: str
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    raw_profile: dict[str, Any] | None = None
    access_token: str | None = None
    refresh_token: str | None = None


class OAuthProvider:
    """Base class — subclasses implement provider-specific URLs/parsing."""

    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str]

    def get_client_id(self) -> str:
        raise NotImplementedError

    def get_client_secret(self) -> str:
        raise NotImplementedError

    def get_redirect_uri(self, base_url: str | None = None) -> str:
        origin = base_url or settings.app_url
        return f"{origin}/api/auth/oauth/{self.name}/callback"

    def build_authorize_url(self, state: str, base_url: str | None = None) -> str:
        """Build the full authorization redirect URL."""
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self.get_client_id(),
            "redirect_uri": self.get_redirect_uri(base_url),
            "state": state,
        }
        if self.scopes:
            params["scope"] = " ".join(self.scopes)
        return f"{self.authorize_url}?{urlencode(params)}"

    async def exchange_code(self, code: str, base_url: str | None = None) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.get_client_id(),
                    "client_secret": self.get_client_secret(),
                    "redirect_uri": self.get_redirect_uri(base_url),
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch user profile and return normalised OAuthUserInfo."""
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Return True if both client_id and secret are set."""
        return bool(self.get_client_id() and self.get_client_secret())


# ---------------------------------------------------------------------------
# Yandex ID
# ---------------------------------------------------------------------------

class YandexProvider(OAuthProvider):
    name = "yandex"
    authorize_url = "https://oauth.yandex.ru/authorize"
    token_url = "https://oauth.yandex.ru/token"
    userinfo_url = "https://login.yandex.ru/info"
    scopes = ["login:info", "login:email", "login:avatar"]

    def get_client_id(self) -> str:
        return settings.yandex_client_id

    def get_client_secret(self) -> str:
        return settings.yandex_client_secret

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                self.userinfo_url,
                params={"format": "json"},
                headers={"Authorization": f"OAuth {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        avatar_id = data.get("default_avatar_id")
        avatar_url = (
            f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200"
            if avatar_id
            else None
        )
        display_name = data.get("display_name") or data.get("real_name")

        return OAuthUserInfo(
            provider=self.name,
            provider_user_id=str(data["id"]),
            email=data.get("default_email"),
            display_name=display_name,
            avatar_url=avatar_url,
            raw_profile=data,
            access_token=access_token,
        )


# ---------------------------------------------------------------------------
# VK ID
# ---------------------------------------------------------------------------

class VKProvider(OAuthProvider):
    name = "vk"
    authorize_url = "https://id.vk.com/authorize"
    token_url = "https://id.vk.com/oauth2/auth"
    userinfo_url = "https://id.vk.com/oauth2/user_info"
    scopes = ["vkid.personal_info", "email"]

    def get_client_id(self) -> str:
        return settings.vk_client_id

    def get_client_secret(self) -> str:
        return settings.vk_client_secret

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """VK ID uses a slightly different token exchange flow."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.get_client_id(),
                    "redirect_uri": self.redirect_uri,
                    "device_id": "",
                    "state": "",
                    "code_verifier": "",
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self.userinfo_url,
                data={
                    "access_token": access_token,
                    "client_id": self.get_client_id(),
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        user = data.get("user", data)
        first = user.get("first_name", "")
        last = user.get("last_name", "")
        display_name = f"{first} {last}".strip() or None

        return OAuthUserInfo(
            provider=self.name,
            provider_user_id=str(user["user_id"]),
            email=user.get("email"),
            display_name=display_name,
            avatar_url=user.get("avatar"),
            raw_profile=data,
            access_token=access_token,
        )


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

class GoogleProvider(OAuthProvider):
    name = "google"
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    scopes = ["openid", "email", "profile"]

    def get_client_id(self) -> str:
        return settings.google_client_id

    def get_client_secret(self) -> str:
        return settings.google_client_secret

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        return OAuthUserInfo(
            provider=self.name,
            provider_user_id=str(data["id"]),
            email=data.get("email"),
            display_name=data.get("name"),
            avatar_url=data.get("picture"),
            raw_profile=data,
            access_token=access_token,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

OAUTH_PROVIDERS: dict[str, OAuthProvider] = {
    "yandex": YandexProvider(),
    "vk": VKProvider(),
    "google": GoogleProvider(),
}


def get_provider(name: str) -> OAuthProvider:
    """Return a provider by name. Raises KeyError if not found."""
    return OAUTH_PROVIDERS[name]
