from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError
from app.core.standings_zones import load_standings_zones
from app.db.models import Competition, ContentCandidate
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.reporting import StandingView
from app.schemas.standings_roundup import (
    StandingsRoundupCandidateView,
    StandingsRoundupGenerationResult,
    StandingsRoundupPreviewResult,
    StandingsRoundupRowView,
)
from app.services.competition_queries import CompetitionQueryService
from app.services.competition_relevance import CompetitionRelevanceService
from app.services.editorial_formatter import EditorialFormatterService
from app.utils.hashing import stable_hash
from app.utils.time import utcnow

DEFAULT_MAX_CHARACTERS = 280
DEFAULT_TOP_ROWS = 5


def _excerpt(text: str, limit: int = 120) -> str:
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


class StandingsRoundupService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        max_characters: int = DEFAULT_MAX_CHARACTERS,
        top_rows: int = DEFAULT_TOP_ROWS,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = CompetitionQueryService(session)
        self.repository = ContentCandidateRepository(session)
        self.catalog = load_competition_catalog()
        self.zones = load_standings_zones()
        self.relevance = CompetitionRelevanceService()
        self.max_characters = max_characters
        self.top_rows = top_rows

    def show_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> StandingsRoundupPreviewResult:
        return self._preview(competition_code, reference_date=reference_date)

    def generate_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> StandingsRoundupGenerationResult:
        preview = self._preview(competition_code, reference_date=reference_date)
        candidates = self.build_candidate_drafts(competition_code, reference_date=reference_date)
        stats = self.store_candidates(candidates)
        return StandingsRoundupGenerationResult(
            **preview.model_dump(),
            stats=stats,
            generated_candidates=[
                StandingsRoundupCandidateView(
                    competition_slug=candidate.competition_slug,
                    competition_name=preview.competition_name,
                    content_type=ContentType(candidate.content_type),
                    priority=candidate.priority,
                    group_label=str(candidate.payload_json["source_payload"].get("group_label") or "-"),
                    selected_rows_count=len(candidate.payload_json["source_payload"]["rows"]),
                    omitted_rows_count=int(candidate.payload_json["source_payload"]["omitted_rows_count"]),
                    excerpt=_excerpt(candidate.text_draft),
                    text_draft=candidate.text_draft,
                )
                for candidate in candidates
            ],
        )

    def build_candidate_drafts(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> list[ContentCandidateDraft]:
        preview = self._preview(competition_code, reference_date=reference_date)
        if not preview.rows:
            return []
        row_groups: list[tuple[str, list[StandingsRoundupRowView]]] = [("full", preview.rows)]

        candidates: list[ContentCandidateDraft] = []
        part_total = len(row_groups)
        for part_index, (split_focus, row_group) in enumerate(row_groups, start=1):
            payload_rows = [row.model_dump(mode="json") for row in row_group]
            block_signature = stable_hash(payload_rows)[:12]
            content_key = f"standings_roundup:{preview.group_label or 'standings'}:{split_focus}:{block_signature}:p{part_index}of{part_total}"
            source_payload = {
                "group_label": preview.group_label,
                "round_name": preview.group_label,
                "reference_date": preview.reference_date.isoformat(),
                "selected_rows_count": len(payload_rows),
                "omitted_rows_count": max(0, len(preview.rows) - len(payload_rows)),
                "rows": payload_rows,
                "max_characters": preview.max_characters,
                "part_index": part_index,
                "part_total": part_total,
                "split_focus": split_focus,
            }
            stable_source_payload = {key: value for key, value in source_payload.items() if key != "reference_date"}
            candidate = ContentCandidateDraft(
                competition_slug=preview.competition_slug,
                content_type=ContentType.STANDINGS_ROUNDUP,
                priority=82,
                text_draft=self._build_part_text(
                    competition_name=preview.competition_name,
                    group_label=preview.group_label,
                    rows=row_group,
                    part_index=part_index,
                    part_total=part_total,
                ),
                payload_json={
                    "content_key": content_key,
                    "template_name": "standings_roundup_v1",
                    "competition_name": preview.competition_name,
                    "reference_date": preview.reference_date.isoformat(),
                    "source_payload": source_payload,
                },
                source_summary_hash=_candidate_hash(
                    preview.competition_slug,
                    ContentType.STANDINGS_ROUNDUP,
                    content_key,
                    stable_source_payload,
                ),
                scheduled_at=None,
                status=ContentCandidateStatus.DRAFT,
            )
            candidates.append(self._reuse_existing_candidate_hash(candidate))
        return candidates

    def store_candidates(self, candidates: list[ContentCandidateDraft]) -> IngestStats:
        candidates = EditorialFormatterService(self.session).apply_to_drafts(candidates)
        stats = IngestStats(found=len(candidates))
        for candidate in candidates:
            _, inserted, updated = self.repository.upsert(candidate.model_dump(mode="python"))
            stats.inserted += int(inserted)
            stats.updated += int(updated)
        return stats

    def _reuse_existing_candidate_hash(self, candidate: ContentCandidateDraft) -> ContentCandidateDraft:
        row = self.session.execute(
            select(ContentCandidate)
            .where(
                ContentCandidate.competition_slug == candidate.competition_slug,
                ContentCandidate.content_type == str(candidate.content_type),
                ContentCandidate.text_draft == candidate.text_draft,
                ContentCandidate.status != str(ContentCandidateStatus.REJECTED),
            )
            .order_by(ContentCandidate.created_at.asc(), ContentCandidate.id.asc())
        ).scalars().first()
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

    def _preview(
        self,
        competition_code: str,
        *,
        reference_date: date | None,
    ) -> StandingsRoundupPreviewResult:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        standings = self._current_standings(competition_code)
        group_label = self._group_label(
            competition_code,
            standings,
            reference_date=selected_date,
        )
        selected_rows, omitted_count, text_draft = self._build_text(
            competition_code=competition_code,
            competition_name=self._competition_name(competition),
            group_label=group_label,
            standings=standings,
        )
        return StandingsRoundupPreviewResult(
            competition_slug=competition_code,
            competition_name=self._competition_name(competition),
            reference_date=selected_date,
            generated_at=utcnow(),
            group_label=group_label,
            selected_rows_count=len(selected_rows),
            omitted_rows_count=omitted_count,
            max_characters=self.max_characters,
            text_draft=text_draft,
            rows=selected_rows,
        )

    def _build_text(
        self,
        *,
        competition_code: str,
        competition_name: str,
        group_label: str | None,
        standings: list[StandingView],
    ) -> tuple[list[StandingsRoundupRowView], int, str | None]:
        if not standings:
            return [], 0, None
        title_parts = ["CLASIFICACION", competition_name]
        if group_label:
            title_parts.append(group_label)
        header = " | ".join(title_parts)

        preferred_rows = self._preferred_rows(competition_code, standings)
        selected: list[StandingsRoundupRowView] = []
        for row in preferred_rows:
            trial_selected = selected + [row]
            trial_text = self._render_text(header, trial_selected, total_rows=len(standings))
            if len(trial_text) <= self.max_characters or not selected:
                selected = trial_selected
            else:
                break

        text_draft = self._render_text(header, selected, total_rows=len(standings))
        omitted_count = len(standings) - len(selected)
        return sorted(selected, key=lambda row: row.position), omitted_count, text_draft

    def _render_text(self, header: str, rows: list[StandingsRoundupRowView], *, total_rows: int) -> str:
        ordered_rows = sorted(rows, key=lambda row: row.position)
        lines = [header, ""]
        previous_position: int | None = None
        for row in ordered_rows:
            if previous_position is not None and row.position > previous_position + 1:
                lines.append("...")
            lines.append(self._row_line(row))
            previous_position = row.position
        omitted_count = total_rows - len(ordered_rows)
        text = "\n".join(lines)
        if omitted_count > 0:
            suffix = f"\n\n+{omitted_count} equipos mas"
            if len(text) + len(suffix) <= self.max_characters:
                text += suffix
        return text

    def _build_part_text(
        self,
        *,
        competition_name: str,
        group_label: str | None,
        rows: list[StandingsRoundupRowView],
        part_index: int,
        part_total: int,
    ) -> str:
        header = f"CLASIFICACION | {competition_name}"
        if group_label:
            header = f"{header} | {group_label}"
        if part_total > 1:
            header = f"{header} ({part_index}/{part_total})"
        return self._render_text(header, rows, total_rows=len(rows))

    def _row_line(self, row: StandingsRoundupRowView) -> str:
        points = "-" if row.points is None else row.points
        suffix = ""
        if row.zone_tag == "playoff":
            suffix = " [PO]"
        elif row.zone_tag == "relegation":
            suffix = " [DESC]"
        return f"{row.position}. {row.team} - {points} pts{suffix}"

    def _preferred_rows(
        self,
        competition_code: str,
        standings: list[StandingView],
    ) -> list[StandingsRoundupRowView]:
        zones = self.zones.get(competition_code)
        playoff_positions = set(zones.playoff_positions if zones is not None else [])
        relegation_positions = set(zones.relegation_positions if zones is not None else [])
        top_block_end = max(self.top_rows, max(playoff_positions, default=0))

        rows_by_position = {row.position: row for row in standings}
        preferred_positions: list[int] = []
        if len(standings) <= self.top_rows:
            preferred_positions = [row.position for row in standings]
        else:
            for position in range(1, top_block_end + 1):
                if position in rows_by_position:
                    preferred_positions.append(position)
            for position in sorted(relegation_positions):
                if position in rows_by_position and position not in preferred_positions:
                    preferred_positions.append(position)
        if not preferred_positions:
            preferred_positions = [row.position for row in standings[: self.top_rows]]

        return [
            StandingsRoundupRowView(
                position=row.position,
                team=row.team,
                points=row.points,
                played=row.played,
                zone_tag=(
                    "playoff"
                    if row.position in playoff_positions
                    else "relegation"
                    if row.position in relegation_positions
                    else None
                ),
            )
            for position in preferred_positions
            for row in [rows_by_position[position]]
        ]

    def _group_label(
        self,
        competition_code: str,
        standings: list[StandingView],
        *,
        reference_date: date,
    ) -> str | None:
        latest_finished_round = self._latest_finished_round_label(
            competition_code,
            reference_date=reference_date,
        )
        latest_finished_round_number = self._round_number(latest_finished_round)
        played_round_label = self._played_group_label(standings)
        played_round_number = self._round_number(played_round_label)
        if latest_finished_round_number is not None and (
            played_round_number is None or latest_finished_round_number >= played_round_number
        ):
            return latest_finished_round
        if played_round_label is not None:
            return played_round_label
        return latest_finished_round

    def _latest_finished_round_label(
        self,
        competition_code: str,
        *,
        reference_date: date,
    ) -> str | None:
        matches = self.queries.finished_matches(
            competition_code,
            limit=None,
            relevant_only=False,
            reference_date=reference_date,
        )
        if not matches:
            return None
        numbered_rounds = [
            (round_number, str(match.round_name))
            for match in matches
            if match.round_name
            for round_number in [self._round_number(match.round_name)]
            if round_number is not None
        ]
        if numbered_rounds:
            return max(numbered_rounds, key=lambda row: row[0])[1]
        first_match = matches[0]
        if first_match.round_name:
            return str(first_match.round_name)
        if first_match.match_date is not None:
            return first_match.match_date.isoformat()
        return None

    def _played_group_label(self, standings: list[StandingView]) -> str | None:
        played_values = {
            row.played
            for row in standings
            if row.played is not None and row.played > 0
        }
        if played_values:
            return f"Jornada {max(played_values)}"
        return None

    def _round_number(self, round_label: str | None) -> int | None:
        if not round_label:
            return None
        match = re.search(r"(\d+)(?!.*\d)", round_label)
        if match is None:
            return None
        return int(match.group(1))

    def _current_standings(self, competition_code: str) -> list[StandingView]:
        try:
            standings = self.queries.current_standings(competition_code)
            return self.relevance.filter_standing_views(competition_code, standings)
        except ConfigurationError as exc:
            if "No hay clasificacion disponible" in str(exc):
                return []
            raise

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(select(Competition).where(Competition.code == competition_code))
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
