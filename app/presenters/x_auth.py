from __future__ import annotations

from app.schemas.x_auth import XAuthorizationStart, XAuthTokenStatus


def render_x_authorization_start(payload: XAuthorizationStart) -> str:
    return "\n".join(
        [
            "Open this URL in your browser and complete the X authorization flow:",
            payload.authorization_url,
            "",
            "Next step:",
            "python -m app.pipelines.x_auth exchange-code --callback-url \"<FULL_CALLBACK_URL>\"",
            "",
            f"state={payload.state}",
            f"expires_at={payload.expires_at.isoformat()}",
            f"scopes={' '.join(payload.scopes)}",
        ]
    )


def render_x_token_status(payload: XAuthTokenStatus) -> str:
    return "\n".join(
        [
            f"ready={str(payload.ready).lower()}",
            f"provider={payload.provider}",
            f"subject_id={payload.subject_id or '-'}",
            f"subject_username={payload.subject_username or '-'}",
            f"expires_at={payload.expires_at.isoformat() if payload.expires_at else '-'}",
            f"has_refresh_token={str(payload.has_refresh_token).lower()}",
            f"scope={payload.scope or '-'}",
            f"last_verified_at={payload.last_verified_at.isoformat() if payload.last_verified_at else '-'}",
        ]
    )
