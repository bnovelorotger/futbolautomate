from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import CompetitionIntegrationStatus, ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError
from app.db.models import Competition, ContentCandidate
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.db.repositories.match_events import MatchEventRepository
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.match_event import TopScorerResult
from app.services.editorial_formatter import EditorialFormatterService
from app.services.top_scorer_tracker import (
    MIN_TOP_SCORER_COVERAGE_RATIO,
    MIN_TOP_SCORER_GOAL_EVENTS,
    MIN_TOP_SCORER_LEADER_GOALS,
    MIN_TOP_SCORER_SCORER_MATCHES,
    TopScorerTrackerService,
)
from app.utils.hashing import stable_hash

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARACTERS = 240
DEFAULT_TOP_SCORERS = 8
_GOAL_EVENT_TYPES = ("goal",)


def _candidate_hash(
    competition_slug: str,
    content_type: ContentType,
    content_key: str,
    source_payload: dict[str, Any],
) -> str:
    return stable_hash(
        {
            "competition_slug": competition_slug,
            "content_type": str(content_type),
            "content_key": content_key,
            "source_payload": source_payload,
        }
    )


def _build_text(
    competition_name: str,
    scorers: list[dict[str, Any]],
    *,
    max_characters: int,
) -> str:
    header = f"GOLEADORES | {competition_name}"
    lines = [header, ""]
    result = "\n".join(lines)
    for index, scorer in enumerate(scorers, start=1):
        line = f"{index}. {scorer['player']} ({scorer['goals']})"
        trial = result + line
        if len(trial) > max_characters and index > 1:
            break
        result = trial + "\n"
    return result.rstrip()


class TopScorerService:
    """Generates TOP_SCORER_UPDATE content candidates from match_events data."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        max_characters: int = DEFAULT_MAX_CHARACTERS,
        top_scorers: int = DEFAULT_TOP_SCORERS,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = ContentCandidateRepository(session)
        self.event_repository = MatchEventRepository(session)
        self.tracker = TopScorerTrackerService(session)
        self.catalog = load_competition_catalog()
        self.max_characters = max_characters
        self.top_scorers = top_scorers

    def generate(
        self,
        competition_slug: str,
        *,
        dry_run: bool = False,
    ) -> ContentCandidate | None:
        competition = self._competition(competition_slug)
        tracker_result = self.tracker.top_scorers_for_competition(
            competition_slug,
            limit=self.top_scorers,
        )
        if not self._has_enough_data(tracker_result):
            logger.info(
                "top_scorer_service: datos insuficientes para %s (scorer_matches=%d, goal_events=%d, leader_goals=%d)",
                competition_slug,
                tracker_result.scorer_matches_count,
                tracker_result.goal_events_count,
                tracker_result.rows[0].goals if tracker_result.rows else 0,
            )
            return None

        competition_name = self._competition_name(competition)
        scorers = [{"player": row.player, "goals": row.goals} for row in tracker_result.rows]
        text_draft = _build_text(competition_name, scorers, max_characters=self.max_characters)
        source_payload: dict[str, Any] = {
            "season": tracker_result.season,
            "reference_date": tracker_result.reference_date.isoformat() if tracker_result.reference_date else None,
            "finished_matches_count": tracker_result.finished_matches_count,
            "scorer_covered_matches_count": tracker_result.scorer_covered_matches_count,
            "scorer_coverage_ratio": tracker_result.scorer_coverage_ratio,
            "scorer_matches_count": tracker_result.scorer_matches_count,
            "goal_events_count": tracker_result.goal_events_count,
            "distinct_scorers_count": tracker_result.distinct_scorers_count,
            "leader": {
                "player": tracker_result.rows[0].player,
                "team": tracker_result.rows[0].team,
                "goals": tracker_result.rows[0].goals,
            }
            if tracker_result.rows
            else None,
            "leader_goals": tracker_result.rows[0].goals if tracker_result.rows else 0,
            "scorers": scorers,
            "rows": [
                {"player": row.player, "team": row.team, "goals": row.goals}
                for row in tracker_result.rows
            ],
        }
        scorers_signature = stable_hash(scorers)[:12]
        content_key = f"top_scorer_update:{competition_slug}:{tracker_result.season or 'unknown'}:{scorers_signature}"
        stable_source_payload = {key: value for key, value in source_payload.items() if key != "reference_date"}
        candidate_draft = ContentCandidateDraft(
            competition_slug=competition_slug,
            content_type=ContentType.TOP_SCORER_UPDATE,
            priority=75,
            text_draft=text_draft,
            payload_json={
                "content_key": content_key,
                "template_name": "top_scorer_update_v1",
                "competition_name": competition_name,
                "reference_date": source_payload["reference_date"],
                "source_payload": source_payload,
            },
            source_summary_hash=_candidate_hash(
                competition_slug,
                ContentType.TOP_SCORER_UPDATE,
                content_key,
                stable_source_payload,
            ),
            scheduled_at=None,
            status=ContentCandidateStatus.DRAFT,
        )
        candidate_draft = self._reuse_existing_candidate_hash(candidate_draft)

        if dry_run:
            logger.info(
                "top_scorer_service: dry_run — omitiria upsert para %s",
                competition_slug,
            )
            return ContentCandidate(
                competition_slug=candidate_draft.competition_slug,
                content_type=str(candidate_draft.content_type),
                priority=candidate_draft.priority,
                text_draft=candidate_draft.text_draft,
                payload_json=candidate_draft.payload_json,
                source_summary_hash=candidate_draft.source_summary_hash,
                status=str(candidate_draft.status),
            )

        [formatted_draft] = EditorialFormatterService(self.session).apply_to_drafts([candidate_draft])
        row, inserted, updated = self.repository.upsert(formatted_draft.model_dump(mode="python"))
        logger.info(
            "top_scorer_service: %s inserted=%s updated=%s",
            competition_slug,
            inserted,
            updated,
        )
        return row

    def generate_all(self, *, dry_run: bool = False) -> list[ContentCandidate]:
        results: list[ContentCandidate] = []
        for definition in sorted(self.catalog.values(), key=lambda d: d.priority):
            if definition.status != CompetitionIntegrationStatus.INTEGRATED:
                continue
            try:
                candidate = self.generate(definition.code, dry_run=dry_run)
            except ConfigurationError as exc:
                logger.warning(
                    "top_scorer_service: generate_all — saltando %s: %s",
                    definition.code,
                    exc,
                )
                continue
            if candidate is not None:
                results.append(candidate)
        return results

    def _has_enough_data(self, result: TopScorerResult) -> bool:
        if result.finished_matches_count <= 0:
            return False
        if result.scorer_coverage_ratio < MIN_TOP_SCORER_COVERAGE_RATIO:
            return False
        if result.scorer_matches_count < MIN_TOP_SCORER_SCORER_MATCHES:
            return False
        if result.goal_events_count < MIN_TOP_SCORER_GOAL_EVENTS:
            return False
        if not result.rows:
            return False
        return result.rows[0].goals >= MIN_TOP_SCORER_LEADER_GOALS

    def _reuse_existing_candidate_hash(self, candidate: ContentCandidateDraft) -> ContentCandidateDraft:
        row = (
            self.session.execute(
                select(ContentCandidate)
                .where(
                    ContentCandidate.competition_slug == candidate.competition_slug,
                    ContentCandidate.content_type == str(candidate.content_type),
                    ContentCandidate.text_draft == candidate.text_draft,
                    ContentCandidate.status != str(ContentCandidateStatus.REJECTED),
                )
                .order_by(ContentCandidate.created_at.asc(), ContentCandidate.id.asc())
            )
            .scalars()
            .first()
        )
        if row is None:
            return candidate
        payload_json = dict(candidate.payload_json)
        payload_json["content_key"] = (row.payload_json or {}).get("content_key", payload_json.get("content_key"))
        return candidate.model_copy(
            update={
                "payload_json": payload_json,
                "source_summary_hash": row.source_summary_hash,
            }
        )

    def _competition(self, competition_slug: str) -> Competition:
        competition = self.session.scalar(select(Competition).where(Competition.code == competition_slug))
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_slug}")
        return competition

    def _competition_name(self, competition: Competition) -> str:
        definition = self.catalog.get(competition.code)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        return competition.name
