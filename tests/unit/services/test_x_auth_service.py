from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.channels.x.auth import XAuthError
from app.core.config import Settings
from app.db.base import Base
from app.db.models import ChannelAuthSession, ChannelUserToken
from app.services.x_auth_service import XAuthService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_settings(**overrides) -> Settings:
    payload = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "x_client_id": "client-id",
        "x_redirect_uri": "http://127.0.0.1:8000/callback",
        "x_scopes": "tweet.read tweet.write users.read offline.access",
    }
    payload.update(overrides)
    return Settings(**payload)


def test_x_auth_service_starts_authorization_and_persists_session() -> None:
    session = build_session()
    try:
        service = XAuthService(
            session,
            settings=build_settings(),
            oauth_client=Mock(),
            api_client=Mock(),
        )

        payload = service.start_authorization()
        session.commit()

        stored = session.query(ChannelAuthSession).one()
        assert stored.provider == "x"
        assert stored.state == payload.state
        assert stored.used_at is None
        assert "https://x.com/i/oauth2/authorize?" in payload.authorization_url
    finally:
        session.close()


def test_x_auth_service_exchanges_code_and_persists_user_token() -> None:
    session = build_session()
    try:
        oauth_client = Mock()
        oauth_client.exchange_code.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "bearer",
            "scope": "tweet.read tweet.write users.read offline.access",
            "expires_in": 7200,
        }
        api_client = Mock()
        api_client.get_authenticated_user.return_value = {"id": "user-1", "username": "ufutbolbalear"}
        service = XAuthService(
            session,
            settings=build_settings(),
            oauth_client=oauth_client,
            api_client=api_client,
        )
        start = service.start_authorization()
        session.commit()

        status = service.exchange_code(code="auth-code", state=start.state)
        session.commit()

        token = session.query(ChannelUserToken).one()
        auth_session = session.query(ChannelAuthSession).one()
        assert status.ready is True
        assert token.access_token == "access-token"
        assert token.refresh_token == "refresh-token"
        assert token.subject_username == "ufutbolbalear"
        assert auth_session.used_at is not None
    finally:
        session.close()


def test_x_auth_service_refreshes_expired_token() -> None:
    session = build_session()
    try:
        expired = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.add(
            ChannelUserToken(
                provider="x",
                access_token="stale-token",
                refresh_token="refresh-token",
                token_type="bearer",
                scope="tweet.read tweet.write users.read offline.access",
                expires_at=expired,
                subject_id="user-1",
                subject_username="ufutbolbalear",
                last_verified_at=None,
            )
        )
        session.commit()

        oauth_client = Mock()
        oauth_client.refresh_token.return_value = {
            "access_token": "fresh-token",
            "refresh_token": "fresh-refresh-token",
            "token_type": "bearer",
            "scope": "tweet.read tweet.write users.read offline.access",
            "expires_in": 7200,
        }
        api_client = Mock()
        api_client.get_authenticated_user.return_value = {"id": "user-1", "username": "ufutbolbalear"}
        service = XAuthService(
            session,
            settings=build_settings(),
            oauth_client=oauth_client,
            api_client=api_client,
        )

        access_token = service.get_valid_user_access_token()
        session.commit()

        token = session.query(ChannelUserToken).one()
        assert access_token == "fresh-token"
        assert token.refresh_token == "fresh-refresh-token"
    finally:
        session.close()


def test_x_auth_service_requires_state_or_callback_url_for_exchange() -> None:
    session = build_session()
    try:
        service = XAuthService(
            session,
            settings=build_settings(),
            oauth_client=Mock(),
            api_client=Mock(),
        )
        with pytest.raises(XAuthError):
            service.exchange_code(code="auth-code", state=None)
    finally:
        session.close()


def test_x_auth_service_accepts_full_callback_url() -> None:
    session = build_session()
    try:
        oauth_client = Mock()
        oauth_client.exchange_code.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "bearer",
            "scope": "tweet.read tweet.write users.read offline.access",
            "expires_in": 7200,
        }
        api_client = Mock()
        api_client.get_authenticated_user.return_value = {"id": "user-1", "username": "ufutbolbalear"}
        service = XAuthService(
            session,
            settings=build_settings(),
            oauth_client=oauth_client,
            api_client=api_client,
        )
        start = service.start_authorization()
        session.commit()

        status = service.exchange_code(
            callback_url=f"http://127.0.0.1:8000/callback?state={start.state}&code=auth-code"
        )
        session.commit()

        assert status.ready is True
        oauth_client.exchange_code.assert_called_once()
    finally:
        session.close()
