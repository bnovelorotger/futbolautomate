from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError
from app.core.match_importance import MatchImportanceConfig, load_match_importance_config
from app.db.models import Competition
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.match_importance import (
    FeaturedMatchCandidateView,
    MatchImportanceGenerationResult,
    MatchImportanceResult,
    MatchImportanceRowView,
)
from app.schemas.team_form import TeamFormEntryView
from app.services.competition_queries import CompetitionQueryService
from app.services.team_form import DEFAULT_FORM_WINDOW, TeamFormService
from app.utils.hashing import stable_hash
from app.utils.time import utcnow

DEFAULT_GENERATION_LIMIT = 3
MIN_GENERATION_SCORE = 20


def _excerpt(text: str, limit: int = 110) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


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


def _priority_from_score(score: int, *, offset: int = 0) -> int:
    return max(60, min(95, 60 + score + offset))


def _near_zone(position: int | None, positions: list[int], margin: int) -> bool:
    if position is None or not positions:
        return False
    return any(abs(position - configured) <= margin for configured in positions)


class MatchImportanceService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        config_map: dict[str, MatchImportanceConfig] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = CompetitionQueryService(session)
        self.team_form = TeamFormService(session, settings=self.settings)
        self.repository = ContentCandidateRepository(session)
        self.catalog = load_competition_catalog()
        self.config_map = config_map or load_match_importance_config()

    def show_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
        limit: int | None = None,
    ) -> MatchImportanceResult:
        return self._result_for_competition(
            competition_code,
            reference_date=reference_date,
            limit=limit,
        )

    def top_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
        limit: int = 5,
    ) -> MatchImportanceResult:
        return self._result_for_competition(
            competition_code,
            reference_date=reference_date,
            limit=limit,
        )

    def generate_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
        limit: int = DEFAULT_GENERATION_LIMIT,
    ) -> MatchImportanceGenerationResult:
        result = self._result_for_competition(
            competition_code,
            reference_date=reference_date,
            limit=limit,
        )
        candidates = self.build_candidate_drafts(
            competition_code,
            reference_date=result.reference_date,
            limit=limit,
        )
        stats = self.store_candidates(candidates)
        return MatchImportanceGenerationResult(
            competition_slug=result.competition_slug,
            competition_name=result.competition_name,
            reference_date=result.reference_date,
            generated_at=result.generated_at,
            rows=result.rows,
            stats=stats,
            generated_candidates=[
                FeaturedMatchCandidateView(
                    competition_slug=candidate.competition_slug,
                    competition_name=result.competition_name,
                    content_type=ContentType(candidate.content_type),
                    priority=candidate.priority,
                    home_team=str(candidate.payload_json["source_payload"]["home_team"]),
                    away_team=str(candidate.payload_json["source_payload"]["away_team"]),
                    importance_score=int(candidate.payload_json["source_payload"]["importance_score"]),
                    tags=list(candidate.payload_json["source_payload"].get("tags", [])),
                    excerpt=_excerpt(candidate.text_draft),
                    text_draft=candidate.text_draft,
                    source_summary_hash=candidate.source_summary_hash,
                )
                for candidate in candidates
            ],
        )

    def build_candidate_drafts(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
        limit: int = DEFAULT_GENERATION_LIMIT,
    ) -> list[ContentCandidateDraft]:
        result = self._result_for_competition(
            competition_code,
            reference_date=reference_date,
            limit=limit,
        )
        candidates: list[ContentCandidateDraft] = []
        for row in result.rows:
            if row.importance_score < MIN_GENERATION_SCORE:
                continue
            preview_payload = self._source_payload(row, result.reference_date)
            preview_content_key = (
                f"featured_match_preview:{row.home_team}:{row.away_team}:{result.reference_date.isoformat()}"
            )
            preview_text = self._preview_text(row)
            candidates.append(
                ContentCandidateDraft(
                    competition_slug=result.competition_slug,
                    content_type=ContentType.FEATURED_MATCH_PREVIEW,
                    priority=_priority_from_score(row.importance_score, offset=0),
                    text_draft=preview_text,
                    payload_json={
                        "content_key": preview_content_key,
                        "template_name": "featured_match_preview_v1",
                        "competition_name": result.competition_name,
                        "reference_date": result.reference_date.isoformat(),
                        "source_payload": preview_payload,
                    },
                    source_summary_hash=_candidate_hash(
                        result.competition_slug,
                        ContentType.FEATURED_MATCH_PREVIEW,
                        preview_content_key,
                        preview_payload,
                    ),
                    status=ContentCandidateStatus.DRAFT,
                )
            )
            event_text = self._event_text(row)
            if event_text is not None:
                event_content_key = (
                    f"featured_match_event:{row.home_team}:{row.away_team}:{result.reference_date.isoformat()}"
                )
                candidates.append(
                    ContentCandidateDraft(
                        competition_slug=result.competition_slug,
                        content_type=ContentType.FEATURED_MATCH_EVENT,
                        priority=_priority_from_score(row.importance_score, offset=-1),
                        text_draft=event_text,
                        payload_json={
                            "content_key": event_content_key,
                            "template_name": "featured_match_event_v1",
                            "competition_name": result.competition_name,
                            "reference_date": result.reference_date.isoformat(),
                            "source_payload": preview_payload,
                        },
                        source_summary_hash=_candidate_hash(
                            result.competition_slug,
                            ContentType.FEATURED_MATCH_EVENT,
                            event_content_key,
                            preview_payload,
                        ),
                        status=ContentCandidateStatus.DRAFT,
                    )
                )
        return sorted(candidates, key=lambda item: (-item.priority, item.source_summary_hash))

    def store_candidates(self, candidates: list[ContentCandidateDraft]) -> IngestStats:
        stats = IngestStats(found=len(candidates))
        for candidate in candidates:
            _, inserted, updated = self.repository.upsert(candidate.model_dump(mode="python"))
            stats.inserted += int(inserted)
            stats.updated += int(updated)
        return stats

    def _result_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None,
        limit: int | None,
    ) -> MatchImportanceResult:
        competition = self._competition(competition_code)
        config = self._config(competition_code)
        selected_date = self._reference_date(reference_date)
        standings = self.queries.current_standings(competition_code)
        positions = {row.team: row.position for row in standings}
        form_rows = self.team_form.build_form_rows(
            competition_code,
            window_size=DEFAULT_FORM_WINDOW,
            reference_date=selected_date,
            respect_tracking=False,
        )
        form_map = {row.team: row for row in form_rows}
        upcoming_matches = [
            match
            for match in self.queries.upcoming_matches(
                competition_code,
                limit=200,
                relevant_only=True,
            )
            if match.match_date is None or match.match_date >= selected_date
        ]

        rows = [
            self._score_match(
                competition_slug=competition_code,
                competition_name=self._competition_name(competition),
                match=match,
                positions=positions,
                form_map=form_map,
                config=config,
            )
            for match in upcoming_matches
        ]
        rows = sorted(
            rows,
            key=lambda row: (
                -row.importance_score,
                row.match_date or selected_date,
                row.home_team,
                row.away_team,
            ),
        )
        if limit is not None:
            rows = rows[:limit]
        return MatchImportanceResult(
            competition_slug=competition_code,
            competition_name=self._competition_name(competition),
            reference_date=selected_date,
            generated_at=utcnow(),
            rows=rows,
        )

    def _score_match(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        match,
        positions: dict[str, int],
        form_map: dict[str, TeamFormEntryView],
        config: MatchImportanceConfig,
    ) -> MatchImportanceRowView:
        score = 0
        tags: list[str] = []
        reasoning: list[str] = []
        home_position = positions.get(match.home_team)
        away_position = positions.get(match.away_team)
        position_gap = (
            abs(home_position - away_position)
            if home_position is not None and away_position is not None
            else None
        )
        home_form = form_map.get(match.home_team)
        away_form = form_map.get(match.away_team)
        home_recent_points = home_form.points if home_form is not None else None
        away_recent_points = away_form.points if away_form is not None else None
        weights = config.weights

        if (
            home_position is not None
            and away_position is not None
            and home_position <= 2
            and away_position <= 2
        ):
            score += weights.title_race
            tags.append("title_race")
            reasoning.append(f"title_race:+{weights.title_race}")

        if (
            home_position in config.top_zone_positions
            and away_position in config.top_zone_positions
        ):
            score += weights.top_table_match
            tags.append("top_table_match")
            reasoning.append(f"top_table_match:+{weights.top_table_match}")

        if (
            _near_zone(home_position, config.playoff_positions, config.near_playoff_margin)
            and _near_zone(away_position, config.playoff_positions, config.near_playoff_margin)
        ):
            score += weights.playoff_clash
            tags.append("playoff_clash")
            reasoning.append(f"playoff_clash:+{weights.playoff_clash}")

        if (
            _near_zone(home_position, config.bottom_zone_positions, config.near_bottom_margin)
            and _near_zone(away_position, config.bottom_zone_positions, config.near_bottom_margin)
        ):
            score += weights.relegation_clash
            tags.append("relegation_clash")
            reasoning.append(f"relegation_clash:+{weights.relegation_clash}")

        if position_gap is not None and position_gap <= config.direct_rival_gap_max:
            score += weights.direct_rivalry
            tags.append("direct_rivalry")
            reasoning.append(f"direct_rivalry:+{weights.direct_rivalry}")

        if (
            home_recent_points is not None
            and away_recent_points is not None
            and home_recent_points >= config.hot_form_points_threshold
            and away_recent_points >= config.hot_form_points_threshold
        ):
            score += weights.hot_form_match
            tags.append("hot_form_match")
            reasoning.append(f"hot_form_match:+{weights.hot_form_match}")

        if (
            home_recent_points is not None
            and away_recent_points is not None
            and home_recent_points <= config.cold_form_points_threshold
            and away_recent_points <= config.cold_form_points_threshold
        ):
            score += weights.cold_form_match
            tags.append("cold_form_match")
            reasoning.append(f"cold_form_match:+{weights.cold_form_match}")

        return MatchImportanceRowView(
            competition_slug=competition_slug,
            competition_name=competition_name,
            round_name=match.round_name,
            match_date=match.match_date,
            source_url=match.source_url,
            home_team=match.home_team,
            away_team=match.away_team,
            home_position=home_position,
            away_position=away_position,
            home_recent_points=home_recent_points,
            away_recent_points=away_recent_points,
            importance_score=score,
            tags=tags,
            score_reasoning=reasoning,
        )

    def _preview_text(self, row: MatchImportanceRowView) -> str:
        descriptor = {
            "title_race": "duelo directo por el liderato",
            "playoff_clash": "duelo directo por la zona de playoff",
            "relegation_clash": "cruce directo por la permanencia",
            "top_table_match": "duelo directo en la zona alta",
            "hot_form_match": "choque entre equipos en buena dinamica",
            "direct_rivalry": "partido entre rivales directos",
            "cold_form_match": "partido con urgencias en la zona baja",
        }.get(self._primary_tag(row), "partido con foco editorial")
        return (
            f"Partido destacado del fin de semana en {row.competition_name}: "
            f"{row.home_team} vs {row.away_team}, {descriptor}."
        )

    def _event_text(self, row: MatchImportanceRowView) -> str | None:
        primary_tag = self._primary_tag(row)
        if primary_tag == "hot_form_match" and row.home_recent_points is not None and row.away_recent_points is not None:
            return (
                f"Choque de equipos en forma en {row.competition_name}: {row.home_team} y {row.away_team} "
                f"llegan con {row.home_recent_points} y {row.away_recent_points} puntos en los ultimos 5 partidos."
            )
        if primary_tag == "title_race":
            return (
                f"Pulso por el liderato en {row.competition_name}: {row.home_team} y {row.away_team} "
                f"arrancan la jornada en los puestos {row.home_position} y {row.away_position}."
            )
        if primary_tag == "playoff_clash":
            return (
                f"Duelo directo por el playoff en {row.competition_name}: {row.home_team} y {row.away_team} "
                f"se miden con la zona alta en juego."
            )
        if primary_tag == "relegation_clash":
            return (
                f"Cruce directo por la permanencia en {row.competition_name}: {row.home_team} y {row.away_team} "
                f"se juegan aire en la zona baja."
            )
        if primary_tag == "top_table_match":
            return (
                f"Choque en la zona alta de {row.competition_name}: {row.home_team} y {row.away_team} "
                f"llegan desde los puestos {row.home_position} y {row.away_position}."
            )
        if primary_tag == "direct_rivalry" and row.home_position is not None and row.away_position is not None:
            gap = abs(row.home_position - row.away_position)
            return (
                f"Partido entre rivales directos en {row.competition_name}: {row.home_team} y {row.away_team} "
                f"llegan separados por {gap} puestos."
            )
        return None

    def _primary_tag(self, row: MatchImportanceRowView) -> str:
        priority = [
            "title_race",
            "playoff_clash",
            "relegation_clash",
            "hot_form_match",
            "top_table_match",
            "direct_rivalry",
            "cold_form_match",
        ]
        for tag in priority:
            if tag in row.tags:
                return tag
        return row.tags[0] if row.tags else "featured_match"

    def _source_payload(
        self,
        row: MatchImportanceRowView,
        reference_date: date,
    ) -> dict[str, Any]:
        return {
            "home_team": row.home_team,
            "away_team": row.away_team,
            "round_name": row.round_name,
            "match_date": row.match_date.isoformat() if row.match_date is not None else None,
            "source_url": row.source_url,
            "home_position": row.home_position,
            "away_position": row.away_position,
            "home_recent_points": row.home_recent_points,
            "away_recent_points": row.away_recent_points,
            "importance_score": row.importance_score,
            "tags": list(row.tags),
            "score_reasoning": list(row.score_reasoning),
            "reference_date": reference_date.isoformat(),
        }

    def _config(self, competition_code: str) -> MatchImportanceConfig:
        default_config = self.config_map.get("default", MatchImportanceConfig())
        override = self.config_map.get(competition_code)
        if override is None:
            return default_config
        payload = default_config.model_dump()
        override_payload = override.model_dump(exclude_unset=True)
        for key, value in override_payload.items():
            payload[key] = value
        return MatchImportanceConfig.model_validate(payload)

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(
            select(Competition).where(Competition.code == competition_code)
        )
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _competition_name(self, competition: Competition) -> str:
        definition = self.catalog.get(competition.code)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        return competition.name

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.settings.timezone)).date()
