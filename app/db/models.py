from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Competition(Base, TimestampMixin):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    category_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str] = mapped_column(String(20), default="unknown")
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str] = mapped_column(String(120), default="Spain")
    federation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_competition_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    matches: Mapped[list["Match"]] = relationship(back_populates="competition")
    standings: Mapped[list["Standing"]] = relationship(back_populates="competition")


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    island: Mapped[str | None] = mapped_column(String(120), nullable=True)
    municipality: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gender: Mapped[str] = mapped_column(String(20), default="unknown")
    source_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_team_id: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Match(Base, TimestampMixin):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("source_name", "external_id", name="uq_matches_source_external_id"),
        UniqueConstraint("source_name", "source_url", name="uq_matches_source_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_name: Mapped[str] = mapped_column(String(50), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    season: Mapped[str | None] = mapped_column(String(50), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    round_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_match_date: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_match_time: Mapped[str | None] = mapped_column(String(120), nullable=True)
    match_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    match_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    kickoff_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    home_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    away_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    home_team_raw: Mapped[str] = mapped_column(String(255))
    away_team_raw: Mapped[str] = mapped_column(String(255))
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    has_lineups: Mapped[bool] = mapped_column(Boolean, default=False)
    has_scorers: Mapped[bool] = mapped_column(Boolean, default=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    competition: Mapped["Competition"] = relationship(back_populates="matches")


class Standing(Base, TimestampMixin):
    __tablename__ = "standings"
    __table_args__ = (
        UniqueConstraint("source_name", "competition_id", "season", "group_name", "team_raw"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(50), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    season: Mapped[str | None] = mapped_column(String(50), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    team_raw: Mapped[str] = mapped_column(String(255))
    played: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draws: Mapped[int | None] = mapped_column(Integer, nullable=True)
    losses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_for: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_against: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goal_difference: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    form_text: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    competition: Mapped["Competition"] = relationship(back_populates="standings")


class News(Base, TimestampMixin):
    __tablename__ = "news"
    __table_args__ = (UniqueConstraint("source_name", "source_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(50), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(500))
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    news_type: Mapped[str] = mapped_column(String(40), default="other")
    clubs_detected: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    competition_detected: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    enrichment: Mapped["NewsEnrichment | None"] = relationship(
        back_populates="news",
        uselist=False,
        cascade="all, delete-orphan",
    )


class NewsEnrichment(Base, TimestampMixin):
    __tablename__ = "news_enrichments"
    __table_args__ = (UniqueConstraint("news_id", name="uq_news_enrichments_news_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"), index=True)
    sport_detected: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    is_football: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_balearic_related: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    clubs_detected: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    competition_detected: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    editorial_relevance_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    news: Mapped["News"] = relationship(back_populates="enrichment")


class ContentCandidate(Base, TimestampMixin):
    __tablename__ = "content_candidates"
    __table_args__ = (
        UniqueConstraint(
            "competition_slug",
            "content_type",
            "source_summary_hash",
            name="uq_content_candidates_slug_type_hash",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_slug: Mapped[str] = mapped_column(ForeignKey("competitions.code"), index=True)
    content_type: Mapped[str] = mapped_column(String(50), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    text_draft: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSON)
    source_summary_hash: Mapped[str] = mapped_column(String(64), index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    rewritten_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rewrite_status: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    rewrite_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rewrite_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rewrite_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    autoapproved: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    autoapproved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    autoapproval_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_publication_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_channel: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    external_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_publication_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_publication_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_publication_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_check_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    quality_check_errors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    quality_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChannelAuthSession(Base, TimestampMixin):
    __tablename__ = "channel_auth_sessions"
    __table_args__ = (
        UniqueConstraint("provider", "state", name="uq_channel_auth_sessions_provider_state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    state: Mapped[str] = mapped_column(String(255), index=True)
    code_verifier: Mapped[str] = mapped_column(String(255))
    redirect_uri: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChannelUserToken(Base, TimestampMixin):
    __tablename__ = "channel_user_tokens"
    __table_args__ = (
        UniqueConstraint("provider", name="uq_channel_user_tokens_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    subject_username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScraperRun(Base):
    __tablename__ = "scraper_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scraper_name: Mapped[str] = mapped_column(String(120), index=True)
    source_name: Mapped[str] = mapped_column(String(50), index=True)
    target_type: Mapped[str] = mapped_column(String(50), index=True)
    competition_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
