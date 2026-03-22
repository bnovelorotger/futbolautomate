from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.story_importance import StoryImportanceConfig, load_story_importance_config
from app.db.models import ContentCandidate
from app.normalizers.text import normalize_token
from app.schemas.story_importance import (
    StoryImportanceAutomationDecision,
    StoryImportanceCandidateView,
    StoryImportanceListResult,
    StoryImportanceScoreResult,
)
from app.utils.time import utcnow

_TEAM_KEYS = {"team", "teams", "home_team", "away_team", "runner_up_team"}
AUTOMATIC_NARRATIVE_CONTENT_TYPES = frozenset(
    {
        ContentType.STANDINGS_EVENT,
        ContentType.FORM_EVENT,
        ContentType.FEATURED_MATCH_EVENT,
        ContentType.VIRAL_STORY,
    }
)


def _excerpt(text: str, limit: int = 110) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _usable_text(candidate: ContentCandidate) -> str:
    rewritten = (candidate.rewritten_text or "").strip()
    if rewritten:
        return rewritten
    return candidate.text_draft.strip()


class StoryImportanceService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        config: StoryImportanceConfig | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.config = config or load_story_importance_config()

    def show_for_date(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 50,
    ) -> StoryImportanceListResult:
        rows = self._candidates_for_date(reference_date=reference_date, limit=limit)
        return StoryImportanceListResult(
            reference_date=reference_date,
            generated_at=utcnow(),
            rows=[self._score_candidate_row(row) for row in rows],
        )

    def top_for_date(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 10,
    ) -> StoryImportanceListResult:
        rows = self._candidates_for_date(reference_date=reference_date, limit=None)
        scored = sorted(
            (self._score_candidate_row(row) for row in rows),
            key=lambda item: (-item.importance_score, -item.current_priority, item.candidate_id),
        )[:limit]
        return StoryImportanceListResult(
            reference_date=reference_date,
            generated_at=utcnow(),
            rows=scored,
        )

    def rank_pending(self, *, limit: int = 25) -> StoryImportanceListResult:
        rows = self._pending_candidates(limit=limit)
        scored = sorted(
            (self._score_candidate_row(row) for row in rows),
            key=lambda item: (-item.importance_score, -item.current_priority, item.candidate_id),
        )
        return StoryImportanceListResult(
            reference_date=None,
            generated_at=utcnow(),
            rows=scored,
        )

    def score_candidate(self, candidate_id: int) -> StoryImportanceScoreResult:
        candidate = self.session.get(ContentCandidate, candidate_id)
        if candidate is None:
            raise ValueError(f"Content candidate desconocido: {candidate_id}")
        return StoryImportanceScoreResult(
            generated_at=utcnow(),
            candidate=self._score_candidate_row(candidate),
        )

    def score_row(self, candidate: ContentCandidate) -> StoryImportanceCandidateView:
        return self._score_candidate_row(candidate)

    def automatic_narrative_threshold(self) -> int:
        return int(self.config.buckets.critical)

    def is_automatic_narrative_content_type(self, content_type: ContentType) -> bool:
        return content_type in AUTOMATIC_NARRATIVE_CONTENT_TYPES

    def select_automatic_narratives(
        self,
        candidates: list[ContentCandidate],
    ) -> dict[int, StoryImportanceAutomationDecision]:
        if not candidates:
            return {}

        scored_rows: list[tuple[ContentCandidate, StoryImportanceCandidateView, tuple[str, ...]]] = []
        for candidate in candidates:
            content_type = ContentType(candidate.content_type)
            if not self.is_automatic_narrative_content_type(content_type):
                continue
            payload_json = candidate.payload_json or {}
            source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
            team_keys = tuple(
                sorted(
                    {
                        normalize_token(team)
                        for team in self._extract_team_names(source_payload)
                        if team
                    }
                )
            )
            scored_rows.append((candidate, self._score_candidate_row(candidate), team_keys))

        ranked_rows = sorted(
            scored_rows,
            key=lambda item: (
                -item[1].importance_score,
                -item[0].priority,
                item[0].created_at,
                item[0].id,
            ),
        )

        threshold = self.automatic_narrative_threshold()
        selected_competitions: set[str] = set()
        selected_teams: set[str] = set()
        decisions: dict[int, StoryImportanceAutomationDecision] = {}
        for candidate, scored, team_keys in ranked_rows:
            allowed = False
            reason = "manual_review_policy"
            if scored.importance_score < threshold:
                reason = f"below_threshold:{scored.importance_score}<{threshold}"
            elif scored.priority_bucket != "critical":
                reason = f"below_threshold_bucket:{scored.priority_bucket}"
            elif candidate.competition_slug in selected_competitions:
                reason = "anti_spam_competition_limit"
            elif team_keys and any(team_key in selected_teams for team_key in team_keys):
                reason = "anti_spam_same_team_limit"
            else:
                allowed = True
                reason = "story_importance_critical"
                selected_competitions.add(candidate.competition_slug)
                selected_teams.update(team_keys)

            decisions[candidate.id] = StoryImportanceAutomationDecision(
                candidate_id=candidate.id,
                competition_slug=candidate.competition_slug,
                content_type=ContentType(candidate.content_type),
                importance_score=scored.importance_score,
                priority_bucket=scored.priority_bucket,
                importance_reasoning=list(scored.importance_reasoning),
                team_keys=list(team_keys),
                allowed=allowed,
                reason=reason,
            )
        return decisions

    def _score_candidate_row(self, candidate: ContentCandidate) -> StoryImportanceCandidateView:
        content_type = ContentType(candidate.content_type)
        payload_json = candidate.payload_json or {}
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        reasons: list[str] = []
        tags: list[str] = [f"type:{content_type.value}"]

        score = self._content_type_weight(content_type)
        reasons.append(f"content_type:{content_type.value}:+{score}")

        competition_multiplier = self.config.competition_weights.get(
            candidate.competition_slug,
            self.config.competition_weights.get("default", 1.0),
        )

        score += self._content_intensity_score(content_type, source_payload, reasons, tags)
        score += self._table_context_score(content_type, source_payload, reasons, tags)
        score += self._team_form_score(content_type, source_payload, reasons, tags)

        match_importance_bonus = self._match_importance_score(source_payload, reasons, tags)
        score += match_importance_bonus

        if competition_multiplier != 1.0:
            adjusted = round(score * competition_multiplier)
            reasons.append(f"competition_weight:{candidate.competition_slug}:x{competition_multiplier}")
            score = adjusted

        repetition_penalty = self._repetition_penalty(candidate, payload_json, source_payload, tags, reasons)
        score = max(0, score - repetition_penalty)

        return StoryImportanceCandidateView(
            candidate_id=candidate.id,
            competition_slug=candidate.competition_slug,
            content_type=content_type,
            status=ContentCandidateStatus(candidate.status),
            current_priority=candidate.priority,
            importance_score=score,
            importance_reasoning=reasons,
            tags=sorted(set(tags)),
            priority_bucket=self._priority_bucket(score),
            excerpt=_excerpt(_usable_text(candidate)),
            created_at=candidate.created_at,
            published_at=candidate.published_at,
        )

    def _content_type_weight(self, content_type: ContentType) -> int:
        return int(self.config.content_type_weights.get(content_type.value, 30))

    def _content_intensity_score(
        self,
        content_type: ContentType,
        source_payload: dict[str, Any],
        reasons: list[str],
        tags: list[str],
    ) -> int:
        if content_type == ContentType.STANDINGS_EVENT:
            return self._standings_event_intensity(source_payload, reasons, tags)
        if content_type == ContentType.VIRAL_STORY:
            return self._viral_story_intensity(source_payload, reasons, tags)
        if content_type == ContentType.FORM_EVENT:
            return self._form_event_intensity(source_payload, reasons, tags)
        if content_type in {ContentType.FEATURED_MATCH_PREVIEW, ContentType.FEATURED_MATCH_EVENT}:
            return self._featured_match_tag_bonus(source_payload, reasons, tags)
        if content_type == ContentType.RESULTS_ROUNDUP:
            return self._results_roundup_intensity(source_payload, reasons, tags)
        return 0

    def _standings_event_intensity(
        self,
        source_payload: dict[str, Any],
        reasons: list[str],
        tags: list[str],
    ) -> int:
        event_type = str(source_payload.get("event_type") or "")
        base = int(self.config.intensity.standings_event_weights.get(event_type, 0))
        if base:
            reasons.append(f"standings_event:{event_type}:+{base}")
            tags.append(f"event:{event_type}")
        delta = abs(int(source_payload.get("position_delta") or 0))
        if event_type in {"biggest_position_rise", "biggest_position_drop"} and delta > 1:
            bonus = min((delta - 1) * 3, 12)
            reasons.append(f"position_delta:{delta}:+{bonus}")
            tags.append("table_movement")
            return base + bonus
        return base

    def _viral_story_intensity(
        self,
        source_payload: dict[str, Any],
        reasons: list[str],
        tags: list[str],
    ) -> int:
        story_type = str(source_payload.get("story_type") or "")
        base = int(self.config.intensity.viral_story_base_weights.get(story_type, 0))
        per_unit = float(self.config.intensity.viral_story_per_unit_weights.get(story_type, 0.0))
        metric_value = source_payload.get("metric_value")
        score = base
        if base:
            reasons.append(f"viral_story:{story_type}:+{base}")
            tags.append(f"story:{story_type}")
        if isinstance(metric_value, (int, float)) and per_unit:
            bonus = int(round(metric_value * per_unit))
            score += bonus
            reasons.append(f"viral_metric:{metric_value}:+{bonus}")
        return score

    def _form_event_intensity(
        self,
        source_payload: dict[str, Any],
        reasons: list[str],
        tags: list[str],
    ) -> int:
        event_type = str(source_payload.get("event_type") or "")
        base = int(self.config.intensity.form_event_weights.get(event_type, 0))
        if base:
            reasons.append(f"form_event:{event_type}:+{base}")
            tags.append(f"form:{event_type}")
        return base

    def _featured_match_tag_bonus(
        self,
        source_payload: dict[str, Any],
        reasons: list[str],
        tags: list[str],
    ) -> int:
        score = 0
        for tag in source_payload.get("tags", []) or []:
            tag_value = int(self.config.intensity.featured_match_tag_weights.get(str(tag), 0))
            if tag_value:
                score += tag_value
                reasons.append(f"featured_tag:{tag}:+{tag_value}")
                tags.append(str(tag))
        return score

    def _results_roundup_intensity(
        self,
        source_payload: dict[str, Any],
        reasons: list[str],
        tags: list[str],
    ) -> int:
        selected_matches = int(source_payload.get("selected_matches_count") or 0)
        omitted_matches = int(source_payload.get("omitted_matches_count") or 0)
        per_match = self.config.intensity.results_roundup_per_match
        score = min(selected_matches * per_match, self.config.intensity.results_roundup_max_match_bonus)
        if score:
            reasons.append(f"results_roundup_matches:{selected_matches}:+{score}")
            tags.append("roundup")
        if selected_matches > 0 and omitted_matches == 0:
            bonus = self.config.intensity.results_roundup_complete_bonus
            score += bonus
            reasons.append(f"results_roundup_complete:+{bonus}")
            tags.append("complete_roundup")
        elif omitted_matches > 0:
            penalty = omitted_matches * self.config.intensity.results_roundup_omitted_penalty
            score -= penalty
            reasons.append(f"results_roundup_omitted:{omitted_matches}:-{penalty}")
        return score

    def _table_context_score(
        self,
        content_type: ContentType,
        source_payload: dict[str, Any],
        reasons: list[str],
        tags: list[str],
    ) -> int:
        score = 0
        if content_type == ContentType.STANDINGS_EVENT:
            event_type = str(source_payload.get("event_type") or "")
            if event_type == "new_leader":
                score += self.config.table_context.leader
                reasons.append(f"table_context:leader:+{self.config.table_context.leader}")
                tags.append("leader")
            if "playoff" in event_type:
                score += self.config.table_context.playoff
                reasons.append(f"table_context:playoff:+{self.config.table_context.playoff}")
                tags.append("playoff")
            if "relegation" in event_type:
                score += self.config.table_context.relegation
                reasons.append(f"table_context:relegation:+{self.config.table_context.relegation}")
                tags.append("relegation")
            return score

        source_tags = {str(item) for item in (source_payload.get("tags") or [])}
        if "title_race" in source_tags:
            score += self.config.table_context.leader
            reasons.append(f"table_context:leader:+{self.config.table_context.leader}")
            tags.append("leader")
        if "playoff_clash" in source_tags:
            score += self.config.table_context.playoff
            reasons.append(f"table_context:playoff:+{self.config.table_context.playoff}")
            tags.append("playoff")
        if "relegation_clash" in source_tags:
            score += self.config.table_context.relegation
            reasons.append(f"table_context:relegation:+{self.config.table_context.relegation}")
            tags.append("relegation")
        return score

    def _team_form_score(
        self,
        content_type: ContentType,
        source_payload: dict[str, Any],
        reasons: list[str],
        tags: list[str],
    ) -> int:
        score = 0
        recent_points_values = [
            source_payload.get("recent_points"),
            source_payload.get("home_recent_points"),
            source_payload.get("away_recent_points"),
        ]
        for recent_points in recent_points_values:
            if not isinstance(recent_points, (int, float)):
                continue
            if recent_points >= self.config.team_form.elite_recent_points_threshold:
                score += self.config.team_form.elite_recent_points_bonus
                reasons.append(
                    f"team_form:elite_points_{int(recent_points)}:+{self.config.team_form.elite_recent_points_bonus}"
                )
                tags.append("elite_form")
            elif recent_points >= self.config.team_form.strong_recent_points_threshold:
                score += self.config.team_form.strong_recent_points_bonus
                reasons.append(
                    f"team_form:strong_points_{int(recent_points)}:+{self.config.team_form.strong_recent_points_bonus}"
                )
                tags.append("strong_form")

        streak_length = source_payload.get("streak_length") or source_payload.get("metric_value")
        if content_type in {ContentType.VIRAL_STORY, ContentType.FORM_EVENT} and isinstance(streak_length, (int, float)):
            if streak_length >= 5:
                score += self.config.team_form.streak_5_plus_bonus
                reasons.append(f"team_form:streak_{int(streak_length)}:+{self.config.team_form.streak_5_plus_bonus}")
                tags.append("streak_5_plus")
            elif streak_length >= 3:
                score += self.config.team_form.streak_3_plus_bonus
                reasons.append(f"team_form:streak_{int(streak_length)}:+{self.config.team_form.streak_3_plus_bonus}")
                tags.append("streak_3_plus")
        return score

    def _match_importance_score(
        self,
        source_payload: dict[str, Any],
        reasons: list[str],
        tags: list[str],
    ) -> int:
        importance_score = source_payload.get("importance_score")
        if not isinstance(importance_score, (int, float)):
            return 0
        bonus = int(round(float(importance_score) * self.config.intensity.featured_match_importance_multiplier))
        if bonus:
            reasons.append(f"match_importance:{int(importance_score)}:+{bonus}")
            tags.append("match_importance")
        return bonus

    def _repetition_penalty(
        self,
        candidate: ContentCandidate,
        payload_json: dict[str, Any],
        source_payload: dict[str, Any],
        tags: list[str],
        reasons: list[str],
    ) -> int:
        marker = self._candidate_marker(candidate, payload_json, source_payload)
        recent_rows = self._recent_candidates(candidate)
        penalty = 0
        for row in recent_rows:
            other_payload = row.payload_json or {}
            other_source_payload = other_payload.get("source_payload", {}) if isinstance(other_payload, dict) else {}
            other_marker = self._candidate_marker(row, other_payload, other_source_payload)
            if marker["content_key"] and marker["content_key"] == other_marker["content_key"]:
                penalty = max(penalty, self.config.repetition.same_content_key_penalty)
                tags.append("repeat_content_key")
            elif marker["kind"] and marker["kind"] == other_marker["kind"] and marker["teams"] == other_marker["teams"]:
                penalty = max(penalty, self.config.repetition.same_kind_penalty)
                tags.append("repeat_kind")
            elif marker["teams"] and marker["teams"] == other_marker["teams"]:
                penalty = max(penalty, self.config.repetition.same_team_penalty)
                tags.append("repeat_teams")
            elif candidate.content_type == row.content_type:
                penalty = max(penalty, self.config.repetition.same_content_type_penalty)
                tags.append("repeat_type")
        if penalty:
            reasons.append(f"repetition_penalty:-{penalty}")
        return penalty

    def _candidate_marker(
        self,
        candidate: ContentCandidate,
        payload_json: dict[str, Any],
        source_payload: dict[str, Any],
    ) -> dict[str, Any]:
        teams = tuple(sorted({normalize_token(team) for team in self._extract_team_names(source_payload) if team}))
        return {
            "content_key": str(payload_json.get("content_key") or ""),
            "kind": str(
                source_payload.get("event_type")
                or source_payload.get("story_type")
                or source_payload.get("narrative_type")
                or ""
            ),
            "teams": teams,
            "content_type": candidate.content_type,
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
            if key in _TEAM_KEYS and isinstance(value, str) and value.strip():
                names.add(value.strip())

        walk(payload)
        return sorted(names)

    def _recent_candidates(self, candidate: ContentCandidate) -> list[ContentCandidate]:
        reference_timestamp = candidate.published_at or candidate.created_at or utcnow()
        if reference_timestamp.tzinfo is None:
            reference_timestamp = reference_timestamp.replace(tzinfo=timezone.utc)
        else:
            reference_timestamp = reference_timestamp.astimezone(timezone.utc)
        cutoff = reference_timestamp - timedelta(hours=self.config.repetition.window_hours)
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.id != candidate.id,
                ContentCandidate.competition_slug == candidate.competition_slug,
                ContentCandidate.status.in_(
                    [
                        str(ContentCandidateStatus.DRAFT),
                        str(ContentCandidateStatus.APPROVED),
                        str(ContentCandidateStatus.PUBLISHED),
                    ]
                ),
                or_(
                    ContentCandidate.published_at.between(cutoff, reference_timestamp),
                    ContentCandidate.created_at.between(cutoff, reference_timestamp),
                ),
            )
            .order_by(ContentCandidate.created_at.desc())
        )
        return self.session.execute(query).scalars().all()

    def _candidates_for_date(
        self,
        *,
        reference_date: date | None,
        limit: int | None,
    ) -> list[ContentCandidate]:
        query = select(ContentCandidate).where(
            ContentCandidate.status.in_(
                [
                    str(ContentCandidateStatus.DRAFT),
                    str(ContentCandidateStatus.APPROVED),
                    str(ContentCandidateStatus.PUBLISHED),
                ]
            )
        )
        if reference_date is not None:
            start_utc, end_utc = self._day_bounds(reference_date)
            query = query.where(
                or_(
                    ContentCandidate.created_at.between(start_utc, end_utc - timedelta(microseconds=1)),
                    ContentCandidate.published_at.between(start_utc, end_utc - timedelta(microseconds=1)),
                )
            )
        query = query.order_by(ContentCandidate.created_at.desc(), ContentCandidate.priority.desc())
        if limit is not None:
            query = query.limit(limit)
        return self.session.execute(query).scalars().all()

    def _pending_candidates(self, *, limit: int) -> list[ContentCandidate]:
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                func.length(func.trim(ContentCandidate.text_draft)) > 0,
            )
            .order_by(ContentCandidate.priority.desc(), ContentCandidate.created_at.asc())
            .limit(limit)
        )
        return self.session.execute(query).scalars().all()

    def _priority_bucket(self, score: int) -> str:
        if score >= self.config.buckets.critical:
            return "critical"
        if score >= self.config.buckets.high:
            return "high"
        if score >= self.config.buckets.medium:
            return "medium"
        return "low"

    def _day_bounds(self, target_date: date) -> tuple[datetime, datetime]:
        start_local = datetime.combine(target_date, time.min, tzinfo=ZoneInfo(self.settings.timezone))
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(timezone.utc),
            end_local.astimezone(timezone.utc),
        )
