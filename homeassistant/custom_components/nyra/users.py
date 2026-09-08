from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUserReference:
    user_id: str
    display_name: str | None


def authenticated_user_reference(user) -> AuthenticatedUserReference:
    user_id = getattr(user, "id", None)
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("an authenticated Home Assistant user is required")
    raw_name = getattr(user, "name", None)
    display_name = raw_name.strip() if isinstance(raw_name, str) else None
    if not display_name or len(display_name) > 255:
        display_name = None
    return AuthenticatedUserReference(user_id.strip(), display_name)


async def async_resolve_user_reference(hass, user_id: str) -> AuthenticatedUserReference:
    stable_user_id = user_id.strip()
    if not stable_user_id:
        raise ValueError("an authenticated Home Assistant user is required")
    try:
        user = await hass.auth.async_get_user(stable_user_id)
    except Exception:
        user = None
    if user is None or getattr(user, "id", None) != stable_user_id:
        return AuthenticatedUserReference(stable_user_id, None)
    return authenticated_user_reference(user)


async def async_sync_user_reference(client, reference: AuthenticatedUserReference) -> bool:
    if client is None or reference.display_name is None:
        return False
    try:
        return bool(await client.async_sync_user_reference(
            user_id=reference.user_id,
            display_name=reference.display_name,
            provider="home_assistant",
        ))
    except Exception:
        return False
