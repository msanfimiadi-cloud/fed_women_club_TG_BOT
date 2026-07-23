from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class LoginCodeError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoginCodeIdentity:
    provider: str
    provider_user_id: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class LoginCodeResult:
    login_code: str
    expires_in: int


class LoginCodeClient:
    def __init__(self, api_base_url: str, service_token: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._api_base_url,
            timeout=15,
            headers={"Authorization": f"Bearer {service_token}"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def create_login_code(self, identity: LoginCodeIdentity) -> LoginCodeResult:
        payload: dict[str, Any] = {
            "provider": identity.provider,
            "provider_user_id": str(identity.provider_user_id),
            "source": identity.source,
        }
        if identity.first_name:
            payload["first_name"] = identity.first_name
        if identity.last_name:
            payload["last_name"] = identity.last_name
        if identity.username:
            payload["username"] = identity.username

        try:
            response = await self._client.post("/internal/login-code", json=payload)
        except httpx.TimeoutException as exc:
            raise LoginCodeError("Не удалось получить код входа.\n\nПопробуйте позже.") from exc
        except httpx.HTTPError as exc:
            raise LoginCodeError("Не удалось получить код входа.\n\nПопробуйте позже.") from exc

        if response.status_code >= 400:
            raise LoginCodeError("Не удалось получить код входа.\n\nПопробуйте позже.")

        try:
            data = response.json()
        except ValueError as exc:
            raise LoginCodeError("Не удалось получить код входа.\n\nПопробуйте позже.") from exc

        result = self._extract_result(data)
        if result is None:
            raise LoginCodeError("Не удалось получить код входа.\n\nПопробуйте позже.")
        return result

    @staticmethod
    def _extract_result(data: Any) -> LoginCodeResult | None:
        if not isinstance(data, dict):
            return None
        code = data.get("login_code") or data.get("code")
        expires_in = data.get("expires_in")
        if isinstance(code, str) and code and isinstance(expires_in, int) and expires_in > 0:
            return LoginCodeResult(login_code=code, expires_in=expires_in)
        nested = data.get("data")
        if nested is not data:
            return LoginCodeClient._extract_result(nested)
        return None
