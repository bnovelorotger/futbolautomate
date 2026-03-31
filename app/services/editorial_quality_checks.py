from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType, NarrativeMetricType, ViralStoryType
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import Competition, ContentCandidate, Match, Standing
from app.schemas.editorial_export import EditorialExportPolicy
from app.schemas.editorial_quality_checks import (
    EditorialQualityCheckBatchResult,
    EditorialQualityCheckCandidateDetail,
    EditorialQualityCheckCandidateView,
    EditorialQualityCheckResult,
)
from app.services.editorial_narratives import METRIC_NARRATIVE_THRESHOLDS
from app.services.editorial_formatter import normalize_team_identity_value
from app.services.editorial_text_selector import EditorialTextSelectorService
from app.services.editorial_viral_stories import VIRAL_STORY_THRESHOLDS
from app.normalizers.text import normalize_token
from app.utils.time import utcnow

_TEAM_KEYS = {"team", "teams", "home_team", "away_team", "runner_up_team"}
_METRIC_VALUE_KEYS = {"metric_value", "recent_points", "recent_goals_for", "delta"}
_MIN_STAT_NARRATIVE_MATCHES = 4
_HANDLE_PATTERN = re.compile(r"(?<!\w)@[A-Za-z0-9_]{1,15}")
_HASHTAG_PATTERN = re.compile(r"(?<!\w)#[A-Za-z0-9_]+")
_MAX_EDITORIAL_TEXT_LENGTH = 240
_RESULTS_TITLE_PATTERN = re.compile(r"^📋 Resultados - .+ - J\d+(?: \(\d+/\d+\))?$")
_STANDINGS_TITLE_PATTERN = re.compile(r"^📊 Clasificación - .+ - J\d+(?: \(\d+/\d+\))?$")
_PREVIEW_TITLE_PATTERN = re.compile(r"^🔎 Previa - .+ - J\d+$")
_RANKING_TITLE_PATTERN = re.compile(r"^🏆 .+ - .+")
_MATCH_RESULT_TITLE_PATTERN = re.compile(r"^📋 Resultado - .+ - J\d+$")


def _excerpt(text: str, limit: int = 110) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _normalized_text(text: str) -> str:
    return " ".join(text.split()).strip().lower()


class EditorialQualityChecksService:
    def __init__(
        self,
        session: Session,
        *,
        text_selector: EditorialTextSelectorService | None = None,
        settings: Settings | None = None,
        policy: EditorialExportPolicy | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.policy = policy or EditorialExportPolicy()
        self.text_selector = text_selector or EditorialTextSelectorService(session)
        self._competition_team_cache: dict[str, set[str]] = {}

    def check_candidate(
        self,
        candidate_id: int,
        *,
        dry_run: bool = False,
        prefer_rewrite: bool | None = None,
    ) -> EditorialQualityCheckResult:
        candidate = self._candidate(candidate_id)
        rewrite_preference = self.policy.use_rewrite_by_default if prefer_rewrite is None else prefer_rewrite
        detail = self._check_candidate(candidate, prefer_rewrite=rewrite_preference, persist=not dry_run)
        return EditorialQualityCheckResult(dry_run=dry_run, candidate=detail)

    def check_pending(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 20,
        dry_run: bool = False,
        prefer_rewrite: bool | None = None,
    ) -> EditorialQualityCheckBatchResult:
        rewrite_preference = self.policy.use_rewrite_by_default if prefer_rewrite is None else prefer_rewrite
        rows = self._pending_candidates(reference_date=reference_date, limit=limit)
        result_rows: list[EditorialQualityCheckCandidateView] = []
        passed_count = 0
        failed_count = 0
        for row in rows:
            detail = self._check_candidate(row, prefer_rewrite=rewrite_preference, persist=not dry_run)
            result_rows.append(self._detail_to_view(detail))
            if detail.passed:
                passed_count += 1
            else:
                failed_count += 1
        return EditorialQualityCheckBatchResult(
            dry_run=dry_run,
            reference_date=reference_date,
            checked_count=len(rows),
            passed_count=passed_count,
            failed_count=failed_count,
            rows=result_rows,
        )

    def check_candidates(
        self,
        candidate_ids: Iterable[int],
        *,
        dry_run: bool = False,
        prefer_rewrite: bool | None = None,
        require_published: bool = True,
    ) -> EditorialQualityCheckBatchResult:
        rewrite_preference = self.policy.use_rewrite_by_default if prefer_rewrite is None else prefer_rewrite
        ids = [candidate_id for candidate_id in candidate_ids]
        if not ids:
            return EditorialQualityCheckBatchResult(
                dry_run=dry_run,
                reference_date=None,
                checked_count=0,
                passed_count=0,
                failed_count=0,
                rows=[],
            )
        rows = self.session.execute(
            select(ContentCandidate)
            .where(ContentCandidate.id.in_(ids))
            .order_by(ContentCandidate.priority.desc(), ContentCandidate.created_at.asc())
        ).scalars().all()
        row_by_id = {row.id: row for row in rows}
        result_rows: list[EditorialQualityCheckCandidateView] = []
        passed_count = 0
        failed_count = 0
        for candidate_id in ids:
            row = row_by_id.get(candidate_id)
            if row is None:
                raise ConfigurationError(f"Content candidate desconocido: {candidate_id}")
            if require_published and row.status != str(ContentCandidateStatus.PUBLISHED):
                raise InvalidStateTransitionError(
                    "Los quality checks de exportacion solo aplican a candidatos en estado published. "
                    f"Estado actual: {row.status}"
                )
            detail = self._check_candidate(row, prefer_rewrite=rewrite_preference, persist=not dry_run)
            result_rows.append(self._detail_to_view(detail))
            if detail.passed:
                passed_count += 1
            else:
                failed_count += 1
        return EditorialQualityCheckBatchResult(
            dry_run=dry_run,
            reference_date=None,
            checked_count=len(ids),
            passed_count=passed_count,
            failed_count=failed_count,
            rows=result_rows,
        )

    def _candidate(self, candidate_id: int) -> ContentCandidate:
        candidate = self.session.get(ContentCandidate, candidate_id)
        if candidate is None:
            raise ConfigurationError(f"Content candidate desconocido: {candidate_id}")
        if candidate.status != str(ContentCandidateStatus.PUBLISHED):
            raise InvalidStateTransitionError(
                "Los quality checks de exportacion solo aplican a candidatos en estado published. "
                f"Estado actual: {candidate.status}"
            )
        return candidate

    def _check_candidate(
        self,
        candidate: ContentCandidate,
        *,
        prefer_rewrite: bool,
        persist: bool,
    ) -> EditorialQualityCheckCandidateDetail:
        selection = self.text_selector.select_text(
            candidate,
            prefer_rewrite=prefer_rewrite,
        )
        selected_text = selection.text
        errors, warnings = self._evaluate(candidate, selected_text, prefer_rewrite=prefer_rewrite)
        checked_at = utcnow()
        if persist:
            candidate.quality_check_passed = not errors
            candidate.quality_check_errors = list(errors)
            candidate.quality_checked_at = checked_at
            self.session.add(candidate)
            self.session.flush()
        return EditorialQualityCheckCandidateDetail(
            id=candidate.id,
            competition_slug=candidate.competition_slug,
            content_type=ContentType(candidate.content_type),
            priority=candidate.priority,
            status=ContentCandidateStatus(candidate.status),
            text_source=selection.source,
            selected_text=selected_text,
            payload_json=candidate.payload_json or {},
            passed=not errors,
            errors=errors,
            warnings=warnings,
            quality_checked_at=checked_at if persist else checked_at,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
        )

    def _detail_to_view(
        self,
        detail: EditorialQualityCheckCandidateDetail,
    ) -> EditorialQualityCheckCandidateView:
        return EditorialQualityCheckCandidateView(
            id=detail.id,
            competition_slug=detail.competition_slug,
            content_type=detail.content_type,
            priority=detail.priority,
            status=detail.status,
            text_source=detail.text_source,
            passed=detail.passed,
            errors=detail.errors,
            warnings=detail.warnings,
            quality_checked_at=detail.quality_checked_at,
            excerpt=_excerpt(detail.selected_text),
        )

    def _evaluate(
        self,
        candidate: ContentCandidate,
        selected_text: str,
        *,
        prefer_rewrite: bool,
    ) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        payload_json = candidate.payload_json or {}
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        content_type = ContentType(candidate.content_type)

        if not selected_text.strip():
            errors.append("selected_text_empty")
            return errors, warnings

        max_text_length = min(self.policy.max_text_length, _MAX_EDITORIAL_TEXT_LENGTH)
        if len(selected_text) > max_text_length:
            errors.append(f"text_too_long>{max_text_length}")
        elif len(selected_text) >= int(max_text_length * 0.9):
            warnings.append("text_near_limit")

        if "\x00" in selected_text:
            errors.append("text_contains_null_byte")
        if "\n\n\n" in selected_text:
            errors.append("text_excessive_blank_lines")
        max_line_breaks = self.policy.max_line_breaks
        if content_type == ContentType.RESULTS_ROUNDUP:
            selected_matches_count = source_payload.get("selected_matches_count") if isinstance(source_payload, dict) else None
            if isinstance(selected_matches_count, int) and selected_matches_count > 0:
                max_line_breaks = max(max_line_breaks, selected_matches_count + 9)
        if content_type in {ContentType.STANDINGS, ContentType.STANDINGS_ROUNDUP}:
            rows = source_payload.get("rows") if isinstance(source_payload, dict) else None
            if isinstance(rows, list) and rows:
                max_line_breaks = max(max_line_breaks, len(rows) + 6)
        if content_type in {
            ContentType.STAT_NARRATIVE,
            ContentType.METRIC_NARRATIVE,
            ContentType.VIRAL_STORY,
            ContentType.FORM_EVENT,
            ContentType.STANDINGS_EVENT,
            ContentType.FEATURED_MATCH_EVENT,
        }:
            max_line_breaks = max(max_line_breaks, 8)
        if content_type in {
            ContentType.PREVIEW,
            ContentType.FEATURED_MATCH_PREVIEW,
            ContentType.RANKING,
            ContentType.FORM_RANKING,
        }:
            max_line_breaks = max(max_line_breaks, 10)
        if selected_text.count("\n") > max_line_breaks:
            errors.append(f"text_excessive_line_breaks>{max_line_breaks}")

        handles = _HANDLE_PATTERN.findall(selected_text)
        if len(handles) > self.settings.max_mentions_per_post:
            errors.append(f"text_mentions_exceed_max>{self.settings.max_mentions_per_post}")
        normalized_handles = [handle.lower() for handle in handles]
        if len(set(normalized_handles)) != len(normalized_handles):
            errors.append("text_mentions_duplicated")
        hashtags = _HASHTAG_PATTERN.findall(selected_text)
        if len(hashtags) > 2:
            errors.append("text_hashtags_exceed_max>2")
        normalized_hashtags = [hashtag.lower() for hashtag in hashtags]
        if len(set(normalized_hashtags)) != len(normalized_hashtags):
            errors.append("text_hashtags_duplicated")

        competition = self.session.scalar(
            select(Competition).where(Competition.code == candidate.competition_slug)
        )
        if competition is None:
            errors.append("competition_missing")
            return sorted(set(errors)), warnings

        if not isinstance(payload_json, dict):
            errors.append("payload_json_invalid")
            return sorted(set(errors)), warnings

        if source_payload and not isinstance(source_payload, dict):
            errors.append("source_payload_invalid")
            return sorted(set(errors)), warnings

        errors.extend(self._coherence_errors(candidate, source_payload))
        errors.extend(self._structure_errors(candidate, selected_text, source_payload))
        errors.extend(self._duplicate_errors(candidate, selected_text, prefer_rewrite=prefer_rewrite))
        errors.extend(self._significance_errors(candidate, source_payload))

        return sorted(set(errors)), sorted(set(warnings))

    def _coherence_errors(
        self,
        candidate: ContentCandidate,
        source_payload: dict[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        content_type = ContentType(candidate.content_type)
        team_names = self._extract_team_names(source_payload)
        competition_teams = self._competition_team_names(candidate.competition_slug)
        normalized_competition_teams = {normalize_token(team) for team in competition_teams if team}
        normalized_identity_teams = {normalize_team_identity_value(team) for team in competition_teams if team}
        missing_teams = sorted(
            team
            for team in team_names
            if normalize_token(team) not in normalized_competition_teams
            and normalize_team_identity_value(team) not in normalized_identity_teams
        )
        if missing_teams:
            errors.append(f"teams_missing_in_competition:{','.join(missing_teams)}")

        numeric_errors = [
            key
            for key in _METRIC_VALUE_KEYS
            if key in source_payload and not isinstance(source_payload.get(key), (int, float))
        ]
        if numeric_errors:
            errors.append(f"metric_values_invalid:{','.join(sorted(numeric_errors))}")

        if content_type == ContentType.STAT_NARRATIVE:
            if "played_matches" not in source_payload or "average_goals_per_played_match" not in source_payload:
                errors.append("stat_narrative_payload_incomplete")
        if content_type == ContentType.RESULTS_ROUNDUP:
            matches = source_payload.get("matches")
            if not isinstance(matches, list) or not matches:
                errors.append("results_roundup_matches_missing")
            if source_payload.get("selected_matches_count") is None:
                errors.append("results_roundup_selected_matches_count_missing")
        if content_type == ContentType.STANDINGS_ROUNDUP:
            rows = source_payload.get("rows")
            if not isinstance(rows, list) or not rows:
                errors.append("standings_roundup_rows_missing")
            if source_payload.get("selected_rows_count") is None:
                errors.append("standings_roundup_selected_rows_count_missing")
        if content_type == ContentType.METRIC_NARRATIVE and "narrative_type" not in source_payload:
            errors.append("metric_narrative_type_missing")
        if content_type == ContentType.VIRAL_STORY and "story_type" not in source_payload:
            errors.append("viral_story_type_missing")
        return errors

    def _structure_errors(
        self,
        candidate: ContentCandidate,
        selected_text: str,
        source_payload: dict[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        content_type = ContentType(candidate.content_type)
        first_line = selected_text.splitlines()[0].strip() if selected_text.splitlines() else ""

        if content_type == ContentType.RESULTS_ROUNDUP:
            if not _RESULTS_TITLE_PATTERN.match(first_line):
                errors.append("results_roundup_title_invalid")
            matches = source_payload.get("matches")
            if isinstance(matches, list):
                if source_payload.get("selected_matches_count") != len(matches):
                    errors.append("results_roundup_selected_matches_count_mismatch")
            part_total = source_payload.get("part_total")
            part_index = source_payload.get("part_index")
            if isinstance(part_total, int) and part_total > 1:
                if not isinstance(part_index, int) or part_index < 1 or part_index > part_total:
                    errors.append("results_roundup_partition_invalid")
                if f"({part_index}/{part_total})" not in first_line:
                    errors.append("results_roundup_partition_title_missing")

        if content_type in {ContentType.STANDINGS, ContentType.STANDINGS_ROUNDUP}:
            if not _STANDINGS_TITLE_PATTERN.match(first_line):
                errors.append("standings_title_invalid")
            rows = source_payload.get("rows")
            if isinstance(rows, list) and source_payload.get("selected_rows_count") is not None:
                if source_payload.get("selected_rows_count") != len(rows):
                    errors.append("standings_selected_rows_count_mismatch")
            if content_type == ContentType.STANDINGS_ROUNDUP:
                part_total = source_payload.get("part_total")
                part_index = source_payload.get("part_index")
                split_focus = source_payload.get("split_focus")
                if isinstance(part_total, int) and part_total > 1:
                    if part_total != 2:
                        errors.append("standings_roundup_partition_total_invalid")
                    if split_focus not in {"top", "relegation"}:
                        errors.append("standings_roundup_split_focus_invalid")
                    if not isinstance(part_index, int) or part_index < 1 or part_index > part_total:
                        errors.append("standings_roundup_partition_invalid")
                    if isinstance(part_index, int) and f"({part_index}/{part_total})" not in first_line:
                        errors.append("standings_roundup_partition_title_missing")

        if content_type in {ContentType.PREVIEW, ContentType.FEATURED_MATCH_PREVIEW}:
            if not _PREVIEW_TITLE_PATTERN.match(first_line):
                errors.append("preview_title_invalid")

        if content_type in {ContentType.RANKING, ContentType.FORM_RANKING}:
            if not _RANKING_TITLE_PATTERN.match(first_line):
                errors.append("ranking_title_invalid")
            if content_type == ContentType.RANKING:
                ranking_teams: list[str] = []
                for key in ("best_attack", "best_defense", "most_wins"):
                    value = source_payload.get(key)
                    if isinstance(value, dict) and isinstance(value.get("team"), str):
                        ranking_teams.append(normalize_team_identity_value(value["team"]))
                if len(set(ranking_teams)) != len(ranking_teams):
                    errors.append("ranking_duplicate_teams")

        if content_type == ContentType.MATCH_RESULT and not _MATCH_RESULT_TITLE_PATTERN.match(first_line):
            errors.append("match_result_title_invalid")

        return errors

    def _duplicate_errors(
        self,
        candidate: ContentCandidate,
        selected_text: str,
        *,
        prefer_rewrite: bool,
    ) -> list[str]:
        candidate_timestamp = self._candidate_timestamp(candidate)
        cutoff = candidate_timestamp - timedelta(hours=self.policy.duplicate_window_hours)
        recent_rows = self.session.execute(
            select(ContentCandidate)
            .where(
                ContentCandidate.id != candidate.id,
                ContentCandidate.competition_slug == candidate.competition_slug,
                ContentCandidate.content_type == candidate.content_type,
                ContentCandidate.status != str(ContentCandidateStatus.REJECTED),
            )
            .order_by(ContentCandidate.created_at.asc(), ContentCandidate.id.asc())
        ).scalars().all()

        candidate_marker = self._candidate_marker(candidate)
        normalized_candidate_text = _normalized_text(selected_text)
        for row in recent_rows:
            row_timestamp = self._candidate_timestamp(row)
            if row_timestamp < cutoff:
                continue
            if row_timestamp > candidate_timestamp:
                continue
            if row_timestamp == candidate_timestamp and row.id > candidate.id:
                continue
            try:
                other_text = self.text_selector.select_text(
                    row,
                    prefer_rewrite=prefer_rewrite,
                ).text
            except InvalidStateTransitionError:
                continue
            if row.source_summary_hash == candidate.source_summary_hash:
                return ["duplicate_recent_source_summary_hash"]
            if _normalized_text(other_text) == normalized_candidate_text:
                return ["duplicate_recent_text"]
            other_marker = self._candidate_marker(row)
            if (
                candidate_marker["content_key"]
                and candidate_marker["content_key"] == other_marker["content_key"]
            ):
                return ["duplicate_recent_content_key"]
            if (
                candidate_marker["kind"]
                and candidate_marker["kind"] == other_marker["kind"]
                and candidate_marker["teams"]
                and candidate_marker["teams"] == other_marker["teams"]
            ):
                return [f"duplicate_recent_kind:{candidate_marker['kind']}"]
        return []

    def _candidate_timestamp(self, candidate: ContentCandidate) -> datetime:
        value = (
            candidate.created_at
            or candidate.published_at
            or candidate.approved_at
            or candidate.reviewed_at
            or utcnow()
        )
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _significance_errors(
        self,
        candidate: ContentCandidate,
        source_payload: dict[str, Any],
    ) -> list[str]:
        content_type = ContentType(candidate.content_type)
        if content_type == ContentType.STAT_NARRATIVE:
            played_matches = source_payload.get("played_matches")
            if isinstance(played_matches, int) and played_matches < _MIN_STAT_NARRATIVE_MATCHES:
                return [f"stat_narrative_played_matches<{_MIN_STAT_NARRATIVE_MATCHES}"]
            return []

        if content_type == ContentType.METRIC_NARRATIVE:
            narrative_type = source_payload.get("narrative_type")
            metric_value = source_payload.get("metric_value")
            return self._metric_narrative_threshold_errors(narrative_type, metric_value, source_payload)

        if content_type == ContentType.VIRAL_STORY:
            story_type = source_payload.get("story_type")
            return self._viral_story_threshold_errors(story_type, source_payload)

        return []

    def _metric_narrative_threshold_errors(
        self,
        narrative_type: str | None,
        metric_value: Any,
        source_payload: dict[str, Any],
    ) -> list[str]:
        if narrative_type is None:
            return ["metric_narrative_type_missing"]
        try:
            metric_kind = NarrativeMetricType(narrative_type)
        except ValueError:
            return [f"metric_narrative_type_invalid:{narrative_type}"]
        threshold = METRIC_NARRATIVE_THRESHOLDS.get(metric_kind)
        if threshold is None:
            return []
        if not isinstance(metric_value, (int, float)):
            return ["metric_narrative_value_invalid"]
        if metric_value < threshold:
            return [f"metric_narrative_below_threshold:{metric_kind}<{threshold}"]
        return []

    def _viral_story_threshold_errors(
        self,
        story_type: str | None,
        source_payload: dict[str, Any],
    ) -> list[str]:
        if story_type is None:
            return ["viral_story_type_missing"]
        try:
            story_kind = ViralStoryType(story_type)
        except ValueError:
            return [f"viral_story_type_invalid:{story_type}"]
        threshold = VIRAL_STORY_THRESHOLDS.get(story_kind)
        if story_kind in {ViralStoryType.WIN_STREAK, ViralStoryType.UNBEATEN_STREAK, ViralStoryType.LOSING_STREAK}:
            streak_length = source_payload.get("streak_length")
            if not isinstance(streak_length, int):
                return ["viral_story_streak_length_invalid"]
            if streak_length < int(threshold):
                return [f"viral_story_below_threshold:{story_kind}<{threshold}"]
            return []
        if story_kind == ViralStoryType.RECENT_TOP_SCORER:
            goals = source_payload.get("recent_goals_for")
            margin = source_payload.get("margin_vs_second")
            errors: list[str] = []
            if not isinstance(goals, int) or goals < threshold["min_goals"]:
                errors.append(f"viral_story_recent_goals<{threshold['min_goals']}")
            if not isinstance(margin, int) or margin < threshold["min_margin"]:
                errors.append(f"viral_story_recent_margin<{threshold['min_margin']}")
            return errors
        if story_kind == ViralStoryType.HOT_FORM:
            points = source_payload.get("recent_points")
            if not isinstance(points, int) or points < threshold["min_points"]:
                return [f"viral_story_hot_form_points<{threshold['min_points']}"]
            return []
        if story_kind == ViralStoryType.COLD_FORM:
            points = source_payload.get("recent_points")
            losses = source_payload.get("recent_losses")
            errors: list[str] = []
            if not isinstance(points, int) or points > threshold["max_points"]:
                errors.append(f"viral_story_cold_form_points>{threshold['max_points']}")
            if not isinstance(losses, int) or losses < threshold["min_losses"]:
                errors.append(f"viral_story_cold_form_losses<{threshold['min_losses']}")
            return errors
        if story_kind in {ViralStoryType.BEST_ATTACK, ViralStoryType.BEST_DEFENSE}:
            margin = source_payload.get("margin_vs_second")
            if not isinstance(margin, int) or margin < threshold["min_margin"]:
                return [f"viral_story_margin<{threshold['min_margin']}"]
            return []
        if story_kind == ViralStoryType.GOALS_TREND:
            recent_matches = source_payload.get("recent_matches")
            delta = source_payload.get("delta")
            errors: list[str] = []
            if not isinstance(recent_matches, int) or recent_matches < threshold["min_matches"]:
                errors.append(f"viral_story_recent_matches<{threshold['min_matches']}")
            if not isinstance(delta, (int, float)) or abs(float(delta)) < threshold["min_delta"]:
                errors.append(f"viral_story_delta<{threshold['min_delta']}")
            return errors
        return []

    def _candidate_marker(self, candidate: ContentCandidate) -> dict[str, Any]:
        payload_json = candidate.payload_json or {}
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        return {
            "content_key": payload_json.get("content_key"),
            "kind": source_payload.get("narrative_type") or source_payload.get("story_type"),
            "teams": tuple(sorted(self._extract_team_names(source_payload))),
        }

    def _extract_team_names(self, payload: Any) -> list[str]:
        names: set[str] = set()

        def walk(value: Any, key: str | None = None) -> None:
            if isinstance(value, dict):
                for inner_key, inner_value in value.items():
                    walk(inner_value, key=inner_key)
                return
            if isinstance(value, list):
                for item in value:
                    walk(item, key=key)
                return
            if key in _TEAM_KEYS:
                if isinstance(value, str) and value.strip():
                    names.add(value.strip())

        walk(payload)
        return sorted(names)

    def _competition_team_names(self, competition_slug: str) -> set[str]:
        cached = self._competition_team_cache.get(competition_slug)
        if cached is not None:
            return cached

        competition = self.session.scalar(select(Competition).where(Competition.code == competition_slug))
        if competition is None:
            self._competition_team_cache[competition_slug] = set()
            return set()

        names: set[str] = set()
        match_rows = self.session.execute(
            select(Match.home_team_raw, Match.away_team_raw).where(Match.competition_id == competition.id)
        ).all()
        for row in match_rows:
            if row.home_team_raw:
                names.add(row.home_team_raw)
            if row.away_team_raw:
                names.add(row.away_team_raw)

        standing_rows = self.session.execute(
            select(Standing.team_raw).where(Standing.competition_id == competition.id)
        ).all()
        for row in standing_rows:
            if row.team_raw:
                names.add(row.team_raw)

        self._competition_team_cache[competition_slug] = names
        return names

    def _pending_candidates(
        self,
        *,
        reference_date: date | None,
        limit: int,
    ) -> list[ContentCandidate]:
        query = select(ContentCandidate).where(
            ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
            ContentCandidate.external_publication_ref.is_(None),
            func.length(func.trim(ContentCandidate.text_draft)) > 0,
        )
        if reference_date is not None:
            start_utc, end_utc = self._day_bounds(reference_date)
            query = query.where(
                ContentCandidate.published_at.is_not(None),
                ContentCandidate.published_at >= start_utc,
                ContentCandidate.published_at < end_utc,
            )
        query = query.order_by(
            case((ContentCandidate.published_at.is_(None), 1), else_=0),
            ContentCandidate.published_at.asc(),
            ContentCandidate.priority.desc(),
            ContentCandidate.created_at.asc(),
        ).limit(limit)
        return self.session.execute(query).scalars().all()

    def _day_bounds(self, target_date: date) -> tuple[datetime, datetime]:
        start_local = datetime.combine(target_date, time.min, tzinfo=ZoneInfo(self.settings.timezone))
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(timezone.utc),
            end_local.astimezone(timezone.utc),
        )
