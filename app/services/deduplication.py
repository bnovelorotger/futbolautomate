from __future__ import annotations

from app.schemas.match import MatchRecord
from app.schemas.news import NewsRecord
from app.schemas.standing import StandingRecord
from app.utils.hashing import stable_hash


def match_content_hash(record: MatchRecord, normalized_home: str, normalized_away: str) -> str:
    return stable_hash(
        {
            "source": record.source_name,
            "url": record.source_url,
            "competition": record.competition_code,
            "season": record.season,
            "round": record.round_name,
            "date": record.match_date_raw,
            "time": record.match_time_raw,
            "home": normalized_home,
            "away": normalized_away,
            "home_score": record.home_score,
            "away_score": record.away_score,
            "status": str(record.status),
            "venue": record.venue,
        }
    )


def standing_content_hash(record: StandingRecord, normalized_team: str) -> str:
    return stable_hash(
        {
            "source": record.source_name,
            "url": record.source_url,
            "competition": record.competition_code,
            "season": record.season,
            "group": record.group_name,
            "position": record.position,
            "team": normalized_team,
            "played": record.played,
            "wins": record.wins,
            "draws": record.draws,
            "losses": record.losses,
            "goals_for": record.goals_for,
            "goals_against": record.goals_against,
            "goal_difference": record.goal_difference,
            "points": record.points,
            "form_text": record.form_text,
        }
    )


def news_content_hash(record: NewsRecord) -> str:
    return stable_hash(
        {
            "source": record.source_name,
            "title": record.title,
            "subtitle": record.subtitle,
            "published_at": record.published_at,
            "summary": record.summary,
            "body_text": record.body_text,
            "news_type": str(record.news_type),
            "raw_category": record.raw_category,
        }
    )
