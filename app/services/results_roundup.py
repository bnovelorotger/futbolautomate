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
from app.core.standings_zones import load_standings_zones
from app.db.models import Competition, ContentCandidate
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.results_roundup import (
    ResultsRoundupCandidateView,
    ResultsRoundupGenerationResult,
    ResultsRoundupMatchView,
    ResultsRoundupPreviewResult,
)
from app.db.repositories.match_events import MatchEventRepository
from app.services.competition_queries import CompetitionQueryService
from app.services.editorial_formatter import EditorialFormatterService
from app.services.standings_events import StandingsEventsService
from app.utils.hashing import stable_hash
from app.utils.time import utcnow

DEFAULT_RESULTS_QUERY_LIMIT = 40
DEFAULT_MAX_CHARACTERS = 280


def _score_line(match: ResultsRoundupMatchView) -> str:
    return f"{match.home_team} {match.home_score}-{match.away_score} {match.away_team}"


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


class ResultsRoundupService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        max_characters: int = DEFAULT_MAX_CHARACTERS,
        results_query_limit: int = DEFAULT_RESULTS_QUERY_LIMIT,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = CompetitionQueryService(session)
        self.repository = ContentCandidateRepository(session)
        self.match_event_repository = MatchEventRepository(session)
        self.catalog = load_competition_catalog()
        self.zones = load_standings_zones()
        self.max_characters = max_characters
        self.results_query_limit = results_query_limit

    def show_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> ResultsRoundupPreviewResult:
        return self._preview(competition_code, reference_date=reference_date)

    def generate_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> ResultsRoundupGenerationResult:
        preview = self._preview(competition_code, reference_date=reference_date)
        candidates = self.build_candidate_drafts(competition_code, reference_date=reference_date)
        stats = self.store_candidates(candidates)
        return ResultsRoundupGenerationResult(
            **preview.model_dump(),
            stats=stats,
            generated_candidates=[
                ResultsRoundupCandidateView(
                    competition_slug=candidate.competition_slug,
                    competition_name=preview.competition_name,
                    content_type=ContentType(candidate.content_type),
                    priority=candidate.priority,
                    group_label=str(candidate.payload_json["source_payload"]["group_label"]),
                    selected_matches_count=len(candidate.payload_json["source_payload"]["matches"]),
                    omitted_matches_count=int(candidate.payload_json["source_payload"]["omitted_matches_count"]),
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
        if not preview.matches:
            return []
        latest_match_date = max((match.match_date for match in preview.matches if match.match_date is not None), default=None)
        scheduled_at = None
        if latest_match_date is not None:
            scheduled_at = datetime.combine(latest_match_date, datetime.min.time(), tzinfo=ZoneInfo(self.settings.timezone))
        candidates: list[ContentCandidateDraft] = []
        match_chunks = [preview.matches]
        part_total = len(match_chunks)
        for part_index, match_chunk in enumerate(match_chunks, start=1):
            payload_matches = [match.model_dump(mode="json") for match in match_chunk]
            chunk_signature = stable_hash(payload_matches)[:12]
            content_key = f"results_roundup:{preview.group_label or 'results'}:{chunk_signature}:p{part_index}of{part_total}"
            goals_by_half = self.match_event_repository.goals_by_half_for_competition(
                preview.competition_slug,
            )
            source_payload = {
                "group_label": preview.group_label,
                "reference_date": preview.reference_date.isoformat(),
                "selected_matches_count": len(payload_matches),
                "omitted_matches_count": max(0, len(preview.matches) - len(payload_matches)),
                "results_insights": preview.results_insights,
                "matches": payload_matches,
                "max_characters": preview.max_characters,
                "part_index": part_index,
                "part_total": part_total,
                "first_half_goals": goals_by_half["first_half"],
                "second_half_goals": goals_by_half["second_half"],
            }
            stable_source_payload = {key: value for key, value in source_payload.items() if key != "reference_date"}
            candidate = ContentCandidateDraft(
                competition_slug=preview.competition_slug,
                content_type=ContentType.RESULTS_ROUNDUP,
                priority=99,
                text_draft=self._build_part_text(
                    competition_name=preview.competition_name,
                    group_label=preview.group_label,
                    matches=match_chunk,
                    part_index=part_index,
                    part_total=part_total,
                ),
                payload_json={
                    "content_key": content_key,
                    "template_name": "results_roundup_v1",
                    "competition_name": preview.competition_name,
                    "reference_date": preview.reference_date.isoformat(),
                    "source_payload": source_payload,
                },
                source_summary_hash=_candidate_hash(
                    preview.competition_slug,
                    ContentType.RESULTS_ROUNDUP,
                    content_key,
                    stable_source_payload,
                ),
                scheduled_at=scheduled_at,
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
    ) -> ResultsRoundupPreviewResult:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        matches = self.queries.finished_matches(
            competition_code,
            limit=self.results_query_limit,
            relevant_only=True,
            reference_date=selected_date,
        )
        grouped_matches, group_label = self._group_matches(matches)
        selected_matches, omitted_count, text_draft = self._build_text(
            competition_name=self._competition_name(competition),
            group_label=group_label,
            matches=grouped_matches,
        )
        full_standings = self._all_standings(competition_code)
        return ResultsRoundupPreviewResult(
            competition_slug=competition_code,
            competition_name=self._competition_name(competition),
            reference_date=selected_date,
            generated_at=utcnow(),
            group_label=group_label,
            selected_matches_count=len(selected_matches),
            omitted_matches_count=omitted_count,
            max_characters=self.max_characters,
            text_draft=text_draft,
            results_insights=self._results_insights(competition_code, selected_matches, full_standings),
            matches=selected_matches,
        )

    def _build_text(
        self,
        *,
        competition_name: str,
        group_label: str | None,
        matches: list[ResultsRoundupMatchView],
    ) -> tuple[list[ResultsRoundupMatchView], int, str | None]:
        if not matches:
            return [], 0, None
        title_parts = ["RESULTADOS", competition_name]
        if group_label:
            title_parts.append(group_label)
        header = " | ".join(title_parts)

        selected: list[ResultsRoundupMatchView] = []
        lines = [header, ""]
        base_text = "\n".join(lines)
        for match in matches:
            trial_selected = selected + [match]
            trial_lines = lines + [_score_line(match)]
            trial_text = "\n".join(trial_lines)
            omitted_after = len(matches) - len(trial_selected)
            if omitted_after > 0:
                suffix = f"\n\n+{omitted_after} resultados mas"
                if len(trial_text) + len(suffix) <= self.max_characters:
                    trial_text_with_suffix = trial_text + suffix
                else:
                    trial_text_with_suffix = trial_text
            else:
                trial_text_with_suffix = trial_text

            if len(trial_text_with_suffix) <= self.max_characters or not selected:
                selected = trial_selected
                lines = trial_lines
            else:
                break

        omitted_count = len(matches) - len(selected)
        text_draft = "\n".join(lines)
        if omitted_count > 0:
            suffix = f"\n\n+{omitted_count} resultados mas"
            if len(text_draft) + len(suffix) <= self.max_characters:
                text_draft += suffix
        return selected, omitted_count, text_draft

    def _group_matches(
        self,
        matches,
    ) -> tuple[list[ResultsRoundupMatchView], str | None]:
        if not matches:
            return [], None
        first_match = matches[0]
        if first_match.round_name:
            selected = [match for match in matches if match.round_name == first_match.round_name]
            group_label = first_match.round_name
        elif first_match.match_date:
            selected = [match for match in matches if match.match_date == first_match.match_date]
            group_label = first_match.match_date.isoformat()
        else:
            selected = [first_match]
            group_label = None
        selected_views = [
            ResultsRoundupMatchView(
                round_name=match.round_name,
                match_date=match.match_date,
                match_time=match.match_time,
                home_team=match.home_team,
                away_team=match.away_team,
                home_score=int(match.home_score),
                away_score=int(match.away_score),
                source_url=match.source_url,
            )
            for match in selected
            if match.home_score is not None and match.away_score is not None
        ]
        selected_views.sort(
            key=lambda match: (
                match.match_date or date.min,
                match.match_time or datetime.min.time(),
                match.round_name or "",
                match.home_team,
                match.away_team,
            )
        )
        return selected_views, group_label

    def _partition_matches(
        self,
        matches: list[ResultsRoundupMatchView],
    ) -> list[list[ResultsRoundupMatchView]]:
        chunks = [
            matches[index : index + 4]
            for index in range(0, len(matches), 4)
        ]
        if len(chunks) > 1 and len(chunks[-1]) == 1 and len(chunks[-2]) > 1:
            chunks[-1] = [chunks[-2].pop(), *chunks[-1]]
        return [chunk for chunk in chunks if chunk]

    def _build_part_text(
        self,
        *,
        competition_name: str,
        group_label: str | None,
        matches: list[ResultsRoundupMatchView],
        part_index: int,
        part_total: int,
    ) -> str:
        title = f"RESULTADOS | {competition_name}"
        if group_label:
            title = f"{title} | {group_label}"
        if part_total > 1:
            title = f"{title} ({part_index}/{part_total})"
        lines = [title, ""]
        for match in matches:
            lines.append(_score_line(match))
        return "\n".join(lines)

    def _all_standings(self, competition_code: str):
        try:
            return self.queries.current_standings(competition_code)
        except ConfigurationError as exc:
            if "No hay clasificacion disponible" in str(exc):
                return []
            raise

    def _results_insights(
        self,
        competition_code: str,
        matches: list[ResultsRoundupMatchView],
        standings,
    ) -> dict[str, Any]:
        if not matches:
            return {}

        positions = {
            row.team: row.position
            for row in standings
        }
        team_contexts = self._team_table_contexts(competition_code, standings)
        insights: dict[str, Any] = {}

        leader_team = next((row.team for row in standings if row.position == 1), None)
        if leader_team is not None:
            leader_match = next(
                (
                    match
                    for match in matches
                    if match.home_team == leader_team or match.away_team == leader_team
                ),
                None,
            )
            if leader_match is not None:
                leader_payload = self._match_insight_payload(leader_match, positions)
                leader_payload["leader_team"] = leader_team
                leader_payload.update(team_contexts.get(leader_team, {}))
                insights["leader_match"] = leader_payload
                insights["leader_team"] = leader_team

        top_match = next(
            (
                match
                for match in matches
                if positions.get(match.home_team) is not None
                and positions.get(match.away_team) is not None
                and max(positions[match.home_team], positions[match.away_team]) <= 4
            ),
            None,
        )
        if top_match is not None:
            insights["top_match"] = self._match_insight_payload(top_match, positions)

        biggest_margin_match = max(
            matches,
            key=lambda match: (abs(match.home_score - match.away_score), match.home_score + match.away_score, match.home_team, match.away_team),
        )
        if abs(biggest_margin_match.home_score - biggest_margin_match.away_score) > 0:
            insights["biggest_margin_match"] = self._match_insight_payload(biggest_margin_match, positions)

        highest_scoring_match = max(
            matches,
            key=lambda match: (match.home_score + match.away_score, abs(match.home_score - match.away_score), match.home_team, match.away_team),
        )
        if highest_scoring_match.home_score + highest_scoring_match.away_score >= 3:
            insights["highest_scoring_match"] = self._match_insight_payload(highest_scoring_match, positions)

        table_events = self._table_event_insights(competition_code, matches, team_contexts)
        if table_events:
            insights["table_events"] = table_events

        return insights

    def _match_insight_payload(
        self,
        match: ResultsRoundupMatchView,
        positions: dict[str, int],
    ) -> dict[str, Any]:
        winner_team = None
        loser_team = None
        result = "draw"
        if match.home_score > match.away_score:
            winner_team = match.home_team
            loser_team = match.away_team
            result = "home_win"
        elif match.away_score > match.home_score:
            winner_team = match.away_team
            loser_team = match.home_team
            result = "away_win"
        return {
            "home_team": match.home_team,
            "away_team": match.away_team,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "home_position": positions.get(match.home_team),
            "away_position": positions.get(match.away_team),
            "winner_team": winner_team,
            "loser_team": loser_team,
            "result": result,
            "goal_margin": abs(match.home_score - match.away_score),
            "total_goals": match.home_score + match.away_score,
        }

    def _table_event_insights(
        self,
        competition_code: str,
        matches: list[ResultsRoundupMatchView],
        team_contexts: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        try:
            preview = StandingsEventsService(self.session).preview_for_competition(competition_code)
        except ConfigurationError:
            return []

        match_teams = {
            team_name
            for match in matches
            for team_name in (match.home_team, match.away_team)
        }
        rows: list[dict[str, Any]] = []
        seen_teams: set[str] = set()
        for row in preview.rows:
            if row.team not in match_teams or row.team in seen_teams:
                continue
            seen_teams.add(row.team)
            rows.append(
                {
                    "event_type": str(row.event_type),
                    "team": row.team,
                    "previous_position": row.previous_position,
                    "current_position": row.current_position,
                    "position_delta": row.position_delta,
                    "priority": row.priority,
                    "title": row.title,
                    **team_contexts.get(row.team, {}),
                }
            )
        return rows[:2]

    def _team_table_contexts(
        self,
        competition_code: str,
        standings,
    ) -> dict[str, dict[str, Any]]:
        if not standings:
            return {}

        ordered_rows = sorted(standings, key=lambda row: row.position)
        rows_by_position = {row.position: row for row in ordered_rows}
        zone_config = self.zones.get(competition_code)
        playoff_positions = sorted(zone_config.playoff_positions if zone_config is not None else [])
        relegation_positions = sorted(zone_config.relegation_positions if zone_config is not None else [])

        leader = rows_by_position.get(1)
        challenger = rows_by_position.get(2)
        leader_points = leader.points if leader is not None else None
        challenger_points = challenger.points if challenger is not None else None

        playoff_cutoff_position = max(playoff_positions) if playoff_positions else None
        playoff_cutoff = rows_by_position.get(playoff_cutoff_position) if playoff_cutoff_position is not None else None
        playoff_outside_position = playoff_cutoff_position + 1 if playoff_cutoff_position is not None else None
        playoff_outside = rows_by_position.get(playoff_outside_position) if playoff_outside_position is not None else None

        relegation_line = min(relegation_positions) if relegation_positions else None
        safe_position = relegation_line - 1 if relegation_line is not None and relegation_line > 1 else None
        safe_row = rows_by_position.get(safe_position) if safe_position is not None else None
        relegation_row = rows_by_position.get(relegation_line) if relegation_line is not None else None

        contexts: dict[str, dict[str, Any]] = {}
        for row in ordered_rows:
            context: dict[str, Any] = {
                "current_position": row.position,
                "current_points": row.points,
            }
            if (
                leader is not None
                and leader_points is not None
                and row.points is not None
            ):
                if row.position == 1 and challenger is not None and challenger_points is not None:
                    context["leader_gap"] = leader_points - challenger_points
                    context["leader_chaser_team"] = challenger.team
                elif row.position != 1:
                    context["leader_gap"] = leader_points - row.points
                    context["leader_team"] = leader.team

            if (
                playoff_cutoff_position is not None
                and playoff_cutoff is not None
                and playoff_outside is not None
                and playoff_cutoff.points is not None
                and playoff_outside.points is not None
                and row.points is not None
            ):
                if row.position == playoff_cutoff_position:
                    context["playoff_margin"] = row.points - playoff_outside.points
                    context["playoff_cutoff_position"] = playoff_cutoff_position
                elif row.position == playoff_outside_position:
                    context["playoff_gap_to_cutoff"] = playoff_cutoff.points - row.points
                    context["playoff_cutoff_position"] = playoff_cutoff_position

            if (
                relegation_line is not None
                and safe_row is not None
                and relegation_row is not None
                and safe_row.points is not None
                and relegation_row.points is not None
                and row.points is not None
            ):
                if row.position == safe_position:
                    context["safe_margin"] = row.points - relegation_row.points
                    context["relegation_line"] = relegation_line
                elif row.position == relegation_line:
                    context["safety_gap"] = safe_row.points - row.points
                    context["relegation_line"] = relegation_line

            contexts[row.team] = context
        return contexts

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
