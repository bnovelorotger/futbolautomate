from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentType
from app.db.models import ContentCandidate
from app.normalizers.text import normalize_token
from app.schemas.editorial_content import ContentCandidateDraft
from app.services.editorial_title_builder import (
    COMPETITION_HASHTAGS,
    RANKING_TITLE_BY_KEY,
    build_competition_title,
    build_group_title,
    build_narrative_label,
    build_narrative_title,
    build_part_suffix,
    build_ranking_title,
    build_round_title,
    build_roundup_title,
    build_standard_title,
    get_competition_name,
)
from app.services.social_enricher import SocialEnricherService
from app.services.social_identity_service import SocialIdentityService
from app.services.team_name_normalizer import load_team_name_aliases, normalize_team_name

MAX_FORMATTED_CHARACTERS = 240
MAX_PREVIEW_MATCHES = 3
MAX_RANKING_ROWS = 3
IDEAL_MENTION_LIMIT = 2
CLUB_PREFIXES = {"cd", "cf", "ce", "ue", "ud", "rcd", "scr", "atletico", "atl", "fc"}
CURATED_MENTION_TYPES = {
    ContentType.MATCH_RESULT,
    ContentType.RESULTS_ROUNDUP,
    ContentType.STANDINGS,
    ContentType.STANDINGS_ROUNDUP,
    ContentType.PREVIEW,
    ContentType.RANKING,
    ContentType.FORM_RANKING,
    ContentType.FEATURED_MATCH_PREVIEW,
}
NARRATIVE_TYPES = {
    ContentType.STAT_NARRATIVE,
    ContentType.METRIC_NARRATIVE,
    ContentType.RACE_NARRATIVE,
    ContentType.MILESTONE_STORY,
    ContentType.VIRAL_STORY,
    ContentType.FORM_EVENT,
    ContentType.STANDINGS_EVENT,
    ContentType.FEATURED_MATCH_EVENT,
    ContentType.MATCH_IMPACT_SCENARIO,
}


def normalize_team_identity_value(team_name: str) -> str:
    normalized = normalize_token(team_name)
    tokens = [token for token in normalized.split() if token and token not in CLUB_PREFIXES]
    return " ".join(tokens) or normalized


@dataclass(slots=True)
class MatchdayThreadPart:
    slot: str
    text: str


@dataclass(slots=True)
class EditorialTextLayers:
    formatted_text: str | None
    enriched_text: str | None
    viral_formatted_text: str | None


class EditorialFormatterService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        max_characters: int = MAX_FORMATTED_CHARACTERS,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.max_characters = max_characters
        self.catalog = load_competition_catalog()
        self.identity_service = SocialIdentityService(session)
        self.social_enricher = SocialEnricherService(
            session,
            settings=self.settings,
            identity_service=self.identity_service,
            max_characters=max_characters,
        )

    def apply_to_drafts(self, candidates: list[ContentCandidateDraft]) -> list[ContentCandidateDraft]:
        return [self.apply_to_draft(candidate) for candidate in candidates]

    def apply_to_draft(self, candidate: ContentCandidateDraft) -> ContentCandidateDraft:
        return candidate.model_copy(update={"formatted_text": self.format_draft(candidate)})

    def format_draft(self, candidate: ContentCandidateDraft) -> str | None:
        layers = self.build_text_layers_for_draft(candidate)
        return layers.enriched_text or layers.formatted_text

    def build_text_layers_for_draft(self, candidate: ContentCandidateDraft) -> EditorialTextLayers:
        content_type = ContentType(candidate.content_type)
        normalized_text_draft, normalized_payload_json = self._normalized_editorial_inputs(
            content_type=content_type,
            text_draft=candidate.text_draft,
            payload_json=candidate.payload_json,
        )
        text = self._format_content(
            competition_slug=candidate.competition_slug,
            content_type=content_type,
            text_draft=normalized_text_draft,
            payload_json=normalized_payload_json,
        )
        enriched_text = self._enrich_text(
            competition_slug=candidate.competition_slug,
            content_type=content_type,
            text=text,
            payload_json=normalized_payload_json,
        )
        viral_formatted_text = self._viral_format_text(
            competition_slug=candidate.competition_slug,
            content_type=content_type,
            text=text,
            enriched_text=enriched_text,
            payload_json=normalized_payload_json,
        )
        return EditorialTextLayers(text, enriched_text, viral_formatted_text)

    def format_candidate(self, candidate: ContentCandidate) -> str | None:
        layers = self.build_text_layers_for_candidate(candidate)
        return layers.enriched_text or layers.formatted_text

    def build_text_layers_for_candidate(self, candidate: ContentCandidate) -> EditorialTextLayers:
        content_type = ContentType(candidate.content_type)
        payload_json = candidate.payload_json or {}
        normalized_text_draft, normalized_payload_json = self._normalized_editorial_inputs(
            content_type=content_type,
            text_draft=candidate.text_draft,
            payload_json=payload_json,
        )
        text = self._format_content(
            competition_slug=candidate.competition_slug,
            content_type=content_type,
            text_draft=normalized_text_draft,
            payload_json=normalized_payload_json,
        )
        enriched_text = self._enrich_text(
            competition_slug=candidate.competition_slug,
            content_type=content_type,
            text=text,
            payload_json=normalized_payload_json,
        )
        viral_formatted_text = self._viral_format_text(
            competition_slug=candidate.competition_slug,
            content_type=content_type,
            text=text,
            enriched_text=enriched_text,
            payload_json=normalized_payload_json,
        )
        return EditorialTextLayers(text, enriched_text, viral_formatted_text)

    def _normalized_editorial_inputs(
        self,
        *,
        content_type: ContentType,
        text_draft: str,
        payload_json: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        normalized_text_draft = self._normalize_alias_text(text_draft)
        if not isinstance(payload_json, dict):
            return normalized_text_draft, {}
        normalized_payload_json = dict(payload_json)
        source_payload = payload_json.get("source_payload")
        if not isinstance(source_payload, dict):
            return normalized_text_draft, normalized_payload_json

        normalized_source_payload = dict(source_payload)
        if content_type in {ContentType.RESULTS_ROUNDUP, ContentType.PREVIEW, ContentType.FEATURED_MATCH_PREVIEW}:
            normalized_source_payload["matches"] = self._normalize_matches(source_payload.get("matches"))
            normalized_source_payload["featured_match"] = self._normalize_match(source_payload.get("featured_match"))
        elif content_type in {ContentType.STANDINGS, ContentType.STANDINGS_ROUNDUP}:
            normalized_source_payload["rows"] = self._normalize_standings_rows(source_payload.get("rows"))
        elif content_type == ContentType.RANKING:
            for key in RANKING_TITLE_BY_KEY:
                normalized_source_payload[key] = self._normalize_ranking_entry(source_payload.get(key))
        elif content_type == ContentType.FORM_RANKING and isinstance(source_payload.get("ranking"), list):
            normalized_source_payload["ranking"] = [
                self._normalize_ranking_entry(row) if isinstance(row, dict) else row
                for row in source_payload["ranking"]
            ]
        elif content_type == ContentType.MATCH_RESULT:
            normalized_source_payload = self._normalize_match(source_payload) if source_payload else normalized_source_payload

        normalized_payload_json["source_payload"] = normalized_source_payload
        return normalized_text_draft, normalized_payload_json

    def _format_content(
        self,
        *,
        competition_slug: str,
        content_type: ContentType,
        text_draft: str,
        payload_json: dict[str, Any],
    ) -> str | None:
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        competition_name = str(payload_json.get("competition_name") or self._competition_name(competition_slug))
        if content_type == ContentType.RESULTS_ROUNDUP:
            return self.format_results_summary(competition_slug=competition_slug, competition_name=competition_name, source_payload=source_payload)
        if content_type in {ContentType.STANDINGS, ContentType.STANDINGS_ROUNDUP}:
            return self.format_standings_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                content_type=content_type,
            )
        if content_type in {ContentType.PREVIEW, ContentType.FEATURED_MATCH_PREVIEW}:
            return self.format_preview_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                content_type=content_type,
            )
        if content_type == ContentType.RANKING:
            return self.format_ranking_summary(competition_slug=competition_slug, competition_name=competition_name, source_payload=source_payload)
        if content_type == ContentType.FORM_RANKING:
            return self.format_form_ranking(competition_slug=competition_slug, competition_name=competition_name, source_payload=source_payload)
        if content_type in NARRATIVE_TYPES:
            return self.format_narrative(
                competition_slug=competition_slug,
                competition_name=competition_name,
                content_type=content_type,
                source_payload=source_payload,
                base_text=text_draft,
            )
        if content_type == ContentType.MATCH_RESULT:
            return self.format_match_result(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                base_text=text_draft,
            )
        return None

    def format_results_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
    ) -> str | None:
        matches = [match for match in list(source_payload.get("matches") or []) if isinstance(match, dict)]
        if not matches:
            return None
        allow_hashtag_drop = self._allow_roundup_hashtag_drop(
            competition_slug=competition_slug,
            content_type=ContentType.RESULTS_ROUNDUP,
        )
        for selected_count in range(len(matches), 0, -1):
            text = self._render_results_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                matches=matches[:selected_count],
                mention_limit=0,
                include_hashtags=True,
                compact_title=False,
            )
            if len(text) <= self.max_characters:
                return text
            if allow_hashtag_drop:
                text_without_hashtags = self._render_results_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    source_payload=source_payload,
                    matches=matches[:selected_count],
                    mention_limit=0,
                    include_hashtags=False,
                    compact_title=False,
                )
                if len(text_without_hashtags) <= self.max_characters:
                    return text_without_hashtags
                compact_text = self._render_results_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    source_payload=source_payload,
                    matches=matches[:selected_count],
                    mention_limit=0,
                    include_hashtags=False,
                    compact_title=True,
                )
                if len(compact_text) <= self.max_characters:
                    return compact_text
        return self._render_results_summary(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            matches=matches[:1],
            mention_limit=0,
            include_hashtags=False,
            compact_title=True,
        )

    def _render_results_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        matches: list[dict[str, Any]],
        mention_limit: int,
        include_hashtags: bool,
        compact_title: bool,
    ) -> str:
        team_names = self._unique(
            team_name
            for match in matches
            for team_name in (self._string(match.get("home_team")), self._string(match.get("away_team")))
            if team_name
        )
        mention_map = self._mention_map(team_names, competition_slug, limit=mention_limit)
        lines = [
            self._roundup_title(
                content_type=ContentType.RESULTS_ROUNDUP,
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                compact=compact_title,
            )
        ]
        if not compact_title:
            lines.append("")
        for match in matches:
            home_team = self._string(match.get("home_team")) or "-"
            away_team = self._string(match.get("away_team")) or "-"
            lines.append(
                f"{self._render_team_label(home_team, mention_map)} {int(match.get('home_score') or 0)}-"
                f"{int(match.get('away_score') or 0)} {self._render_team_label(away_team, mention_map)}"
            )
        if include_hashtags:
            if compact_title:
                lines.append(self._hashtags_line(competition_slug))
            else:
                lines.extend(["", self._hashtags_line(competition_slug)])
        return self._compact_blank_lines("\n".join(lines))

    def format_standings_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        content_type: ContentType,
    ) -> str | None:
        rows = [row for row in list(source_payload.get("rows") or []) if isinstance(row, dict)]
        if not rows:
            return None
        ordered_rows = sorted(rows, key=lambda row: int(row.get("position") or 999))
        allow_hashtag_drop = self._allow_roundup_hashtag_drop(
            competition_slug=competition_slug,
            content_type=content_type,
        )
        for selected_count in range(len(ordered_rows), 0, -1):
            text = self._render_standings_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                rows=ordered_rows[:selected_count],
                content_type=content_type,
                mention_limit=0,
                include_hashtags=True,
                compact_title=False,
            )
            if len(text) <= self.max_characters:
                return text
            if allow_hashtag_drop:
                text_without_hashtags = self._render_standings_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    source_payload=source_payload,
                    rows=ordered_rows[:selected_count],
                    content_type=content_type,
                    mention_limit=0,
                    include_hashtags=False,
                    compact_title=False,
                )
                if len(text_without_hashtags) <= self.max_characters:
                    return text_without_hashtags
                compact_text = self._render_standings_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    source_payload=source_payload,
                    rows=ordered_rows[:selected_count],
                    content_type=content_type,
                    mention_limit=0,
                    include_hashtags=False,
                    compact_title=True,
                )
                if len(compact_text) <= self.max_characters:
                    return compact_text
        return self._render_standings_summary(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            rows=ordered_rows[:1],
            content_type=content_type,
            mention_limit=0,
            include_hashtags=False,
            compact_title=True,
        )

    def _render_standings_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        rows: list[dict[str, Any]],
        content_type: ContentType,
        mention_limit: int,
        include_hashtags: bool,
        compact_title: bool,
    ) -> str:
        ordered_rows = sorted(rows, key=lambda row: int(row.get("position") or 999))
        mention_map = self._mention_map(
            [self._string(row.get("team")) or "-" for row in ordered_rows],
            competition_slug,
            limit=mention_limit,
        )
        lines = [
            self._roundup_title(
                content_type=content_type,
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                compact=compact_title,
            )
        ]
        if not compact_title:
            lines.append("")
        for row in ordered_rows:
            position = int(row.get("position") or 0)
            team_name = self._string(row.get("team")) or "-"
            points = row.get("points")
            lines.append(
                f"{position}. {self._render_team_label(team_name, mention_map)} - {points} pts"
                f"{self._zone_suffix(self._string(row.get('zone_tag')))}"
            )
        if include_hashtags:
            if compact_title:
                lines.append(self._hashtags_line(competition_slug))
            else:
                lines.extend(["", self._hashtags_line(competition_slug)])
        return self._compact_blank_lines("\n".join(lines))

    def format_preview_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        content_type: ContentType,
    ) -> str | None:
        matches = self._preview_matches(source_payload, limit=MAX_PREVIEW_MATCHES)
        featured_match = self._featured_match(source_payload, matches)
        if not matches or featured_match is None:
            return None
        return self._render_preview_summary(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            matches=matches,
            featured_match=featured_match,
            content_type=content_type,
            mention_limit=0,
        )

    def _render_preview_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        matches: list[dict[str, Any]],
        featured_match: dict[str, Any],
        content_type: ContentType,
        mention_limit: int,
    ) -> str:
        mention_map = self._mention_map(
            [
                team_name
                for team_name in (
                    self._string(featured_match.get("home_team")),
                    self._string(featured_match.get("away_team")),
                )
                if team_name
            ],
            competition_slug,
            limit=mention_limit,
        )
        lines = [
            self._standard_title(
                content_type=content_type,
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
            ),
            "",
            "Partidos:",
        ]
        for match in matches:
            lines.append(f"{self._string(match.get('home_team')) or '-'} vs {self._string(match.get('away_team')) or '-'}")
        lines.extend(
            [
                "",
                "Partido clave:",
                (
                    f"{self._render_team_label(self._string(featured_match.get('home_team')) or '-', mention_map)} vs "
                    f"{self._render_team_label(self._string(featured_match.get('away_team')) or '-', mention_map)}"
                ),
            ]
        )
        insight_line = self._preview_insight_line(source_payload)
        if insight_line:
            lines.append(insight_line)
        lines.extend(["", self._hashtags_line(competition_slug)])
        return self._compact_blank_lines("\n".join(lines))

    def format_ranking_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
    ) -> str | None:
        ranking_rows = self._ranking_rows(source_payload, unique_teams=True)
        if not ranking_rows:
            return None
        return self._render_ranking_summary(
            competition_slug=competition_slug,
            competition_name=competition_name,
            ranking_rows=ranking_rows[:MAX_RANKING_ROWS],
            mention_limit=0,
        )

    def _render_ranking_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        ranking_rows: list[dict[str, Any]],
        mention_limit: int,
    ) -> str:
        mention_map = self._mention_map([row["team"] for row in ranking_rows], competition_slug, limit=mention_limit)
        lines = [self._ranking_title(competition_slug=competition_slug, competition_name=competition_name, ranking_rows=ranking_rows), ""]
        for row in ranking_rows:
            team_label = self._render_team_label(row["team"], mention_map)
            value = row.get("value")
            lines.append(f"{row['title']}: {team_label}" if value is None else f"{row['title']}: {team_label} - {value}")
        lines.extend(["", self._hashtags_line(competition_slug)])
        return self._compact_blank_lines("\n".join(lines))

    def format_form_ranking(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
    ) -> str | None:
        ranking_rows = [
            row
            for row in list(source_payload.get("ranking") or [])
            if isinstance(row, dict) and self._string(row.get("team"))
        ][:MAX_RANKING_ROWS]
        if not ranking_rows:
            return None
        return self._render_form_ranking(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            ranking_rows=ranking_rows,
            mention_limit=0,
        )

    def _render_form_ranking(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        ranking_rows: list[dict[str, Any]],
        mention_limit: int,
    ) -> str:
        mention_map = self._mention_map(
            [self._string(row.get("team")) or "-" for row in ranking_rows],
            competition_slug,
            limit=mention_limit,
        )
        lines = [
            self._standard_title(
                content_type=ContentType.FORM_RANKING,
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                title_override="🏆 Forma",
                include_round=False,
            ),
            "",
        ]
        for index, row in enumerate(ranking_rows, start=1):
            lines.append(
                f"{index}. {self._render_team_label(self._string(row.get('team')) or '-', mention_map)} - "
                f"{row.get('points')} pts ({self._string(row.get('sequence')) or '-'})"
            )
        lines.extend(["", self._hashtags_line(competition_slug)])
        return self._compact_blank_lines("\n".join(lines))

    def format_narrative(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        content_type: ContentType,
        source_payload: dict[str, Any],
        base_text: str,
    ) -> str | None:
        del competition_name
        normalized_base = " ".join(base_text.split())
        if not normalized_base:
            return None
        hashtags = self._hashtags_line(competition_slug)
        narrative_title = self._narrative_title(content_type, source_payload)
        for separator in ("\n\n", "\n", " "):
            text = separator.join((narrative_title, normalized_base, hashtags))
            if len(text) <= self.max_characters:
                return text
        return f"{narrative_title}\n{normalized_base}\n{hashtags}"

    def format_match_result(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        base_text: str,
    ) -> str | None:
        if not self._string(source_payload.get("home_team")) or not self._string(source_payload.get("away_team")):
            compact = " ".join(base_text.split())
            return compact or None
        return self._render_match_result(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            mention_limit=0,
        )

    def _enrich_text(
        self,
        *,
        competition_slug: str,
        content_type: ContentType,
        text: str | None,
        payload_json: dict[str, Any],
    ) -> str | None:
        if text is None:
            return None
        if content_type in CURATED_MENTION_TYPES:
            return text
        return self.social_enricher.enrich_text_with_mentions(
            text,
            payload_json,
            str(content_type),
            competition_slug=competition_slug,
        )

    def _viral_format_text(
        self,
        *,
        competition_slug: str,
        content_type: ContentType,
        text: str | None,
        enriched_text: str | None,
        payload_json: dict[str, Any],
    ) -> str | None:
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        competition_name = str(payload_json.get("competition_name") or self._competition_name(competition_slug))
        fallback_text = enriched_text or text
        if content_type == ContentType.RESULTS_ROUNDUP:
            return self._viral_results_summary(competition_slug, competition_name, source_payload, fallback_text)
        if content_type in {ContentType.STANDINGS, ContentType.STANDINGS_ROUNDUP}:
            return self._viral_standings_summary(competition_slug, competition_name, source_payload, fallback_text, content_type)
        if content_type in {ContentType.PREVIEW, ContentType.FEATURED_MATCH_PREVIEW}:
            return self._viral_preview_summary(competition_slug, competition_name, source_payload, fallback_text, content_type)
        if content_type == ContentType.RANKING:
            return self._viral_ranking_summary(competition_slug, competition_name, source_payload, fallback_text)
        if content_type == ContentType.FORM_RANKING:
            return self._viral_form_ranking(competition_slug, competition_name, source_payload, fallback_text)
        if content_type == ContentType.MATCH_RESULT:
            return self._viral_match_result(competition_slug, competition_name, source_payload, fallback_text)
        return None

    def _viral_results_summary(
        self,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
    ) -> str | None:
        matches = [match for match in list(source_payload.get("matches") or []) if isinstance(match, dict)]
        if not matches:
            return fallback_text
        allow_hashtag_drop = self._allow_roundup_hashtag_drop(
            competition_slug=competition_slug,
            content_type=ContentType.RESULTS_ROUNDUP,
        )
        for selected_count in range(len(matches), 0, -1):
            for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
                text = self._render_viral_results_insight_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    source_payload=source_payload,
                    matches=matches[:selected_count],
                    mention_limit=mention_limit,
                    include_hashtags=True,
                    compact_title=False,
                )
                if len(text) <= self.max_characters:
                    return text
                if allow_hashtag_drop:
                    text_without_hashtags = self._render_viral_results_insight_summary(
                        competition_slug=competition_slug,
                        competition_name=competition_name,
                        source_payload=source_payload,
                        matches=matches[:selected_count],
                        mention_limit=mention_limit,
                        include_hashtags=False,
                        compact_title=False,
                    )
                    if len(text_without_hashtags) <= self.max_characters:
                        return text_without_hashtags
                    compact_text = self._render_viral_results_insight_summary(
                        competition_slug=competition_slug,
                        competition_name=competition_name,
                        source_payload=source_payload,
                        matches=matches[:selected_count],
                        mention_limit=mention_limit,
                        include_hashtags=False,
                        compact_title=True,
                    )
                    if len(compact_text) <= self.max_characters:
                        return compact_text
        return fallback_text

    def _render_viral_results_insight_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        matches: list[dict[str, Any]],
        mention_limit: int,
        include_hashtags: bool,
        compact_title: bool,
    ) -> str:
        base_text = self._render_results_summary(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            matches=matches,
            mention_limit=mention_limit,
            include_hashtags=include_hashtags,
            compact_title=compact_title,
        )
        insight_lines = self._results_insight_lines(
            source_payload=source_payload,
            matches=matches,
            competition_slug=competition_slug,
            mention_limit=mention_limit,
        )
        if not insight_lines:
            return base_text

        lines = [
            self._roundup_title(
                content_type=ContentType.RESULTS_ROUNDUP,
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                compact=compact_title,
            )
        ]
        if not compact_title:
            lines.append("")
        lines.extend(insight_lines)
        if not compact_title:
            lines.append("")
        for match in matches:
            home_team = self._string(match.get("home_team")) or "-"
            away_team = self._string(match.get("away_team")) or "-"
            mention_map = self._mention_map([home_team, away_team], competition_slug, limit=mention_limit)
            lines.append(
                f"{self._render_team_label(home_team, mention_map)} {int(match.get('home_score') or 0)}-"
                f"{int(match.get('away_score') or 0)} {self._render_team_label(away_team, mention_map)}"
            )
        if include_hashtags:
            if compact_title:
                lines.append(self._hashtags_line(competition_slug))
            else:
                lines.extend(["", self._hashtags_line(competition_slug)])
        return self._compact_blank_lines("\n".join(lines))

    def _viral_standings_summary(
        self,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
        content_type: ContentType,
    ) -> str | None:
        rows = sorted(
            [row for row in list(source_payload.get("rows") or []) if isinstance(row, dict)],
            key=lambda row: int(row.get("position") or 999),
        )
        if not rows:
            return fallback_text
        insight_text = self._render_viral_standings_insight_summary(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
        )
        if insight_text is not None and len(insight_text) <= self.max_characters:
            return insight_text
        allow_hashtag_drop = self._allow_roundup_hashtag_drop(
            competition_slug=competition_slug,
            content_type=content_type,
        )
        for selected_count in range(len(rows), 0, -1):
            for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
                text = self._render_standings_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    source_payload=source_payload,
                    rows=rows[:selected_count],
                    content_type=content_type,
                    mention_limit=mention_limit,
                    include_hashtags=True,
                    compact_title=False,
                )
                if len(text) <= self.max_characters:
                    return text
                if allow_hashtag_drop:
                    text_without_hashtags = self._render_standings_summary(
                        competition_slug=competition_slug,
                        competition_name=competition_name,
                        source_payload=source_payload,
                        rows=rows[:selected_count],
                        content_type=content_type,
                        mention_limit=mention_limit,
                        include_hashtags=False,
                        compact_title=False,
                    )
                    if len(text_without_hashtags) <= self.max_characters:
                        return text_without_hashtags
                    compact_text = self._render_standings_summary(
                        competition_slug=competition_slug,
                        competition_name=competition_name,
                        source_payload=source_payload,
                        rows=rows[:selected_count],
                        content_type=content_type,
                        mention_limit=mention_limit,
                        include_hashtags=False,
                        compact_title=True,
                    )
                    if len(compact_text) <= self.max_characters:
                        return compact_text
        return fallback_text

    def _viral_preview_summary(
        self,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
        content_type: ContentType,
    ) -> str | None:
        matches = self._preview_matches(source_payload, limit=MAX_PREVIEW_MATCHES)
        featured_match = self._featured_match(source_payload, matches)
        if not matches or featured_match is None:
            return fallback_text
        for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
            text = self._render_viral_preview_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                matches=matches,
                featured_match=featured_match,
                content_type=content_type,
                mention_limit=mention_limit,
            )
            if len(text) <= self.max_characters:
                return text
        return fallback_text

    def _render_viral_standings_insight_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
    ) -> str | None:
        table_insights = source_payload.get("table_insights")
        if not isinstance(table_insights, dict) or not table_insights:
            return None

        mention_names = [
            self._string(table_insights.get("leader_team")),
            self._string(table_insights.get("second_team")),
            self._string(table_insights.get("playoff_cutoff_team")),
            self._string(table_insights.get("playoff_outside_team")),
            self._string(table_insights.get("safe_team")),
            self._string(table_insights.get("relegation_team")),
        ]
        mention_map = self._mention_map(
            [team_name for team_name in mention_names if team_name],
            competition_slug,
            limit=min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post),
        )
        lines = [
            self._roundup_title(
                content_type=ContentType.STANDINGS_ROUNDUP,
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                compact=False,
            ),
            "",
        ]
        insight_lines = [line for line in (
            self._leader_insight_line(table_insights, mention_map),
            self._playoff_insight_line(table_insights, mention_map),
            self._relegation_insight_line(table_insights, mention_map),
        ) if line]
        if not insight_lines:
            return None

        best_text: str | None = None
        selected_insights: list[str] = []
        for insight_line in insight_lines:
            trial_lines = [*lines, *selected_insights, insight_line, "", self._hashtags_line(competition_slug)]
            trial_text = self._compact_blank_lines("\n".join(trial_lines))
            if len(trial_text) <= self.max_characters:
                selected_insights.append(insight_line)
                best_text = trial_text
            else:
                break
        return best_text

    def _render_viral_preview_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        matches: list[dict[str, Any]],
        featured_match: dict[str, Any],
        content_type: ContentType,
        mention_limit: int,
    ) -> str:
        base_text = self._render_preview_summary(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            matches=matches,
            featured_match=featured_match,
            content_type=content_type,
            mention_limit=mention_limit,
        )
        insight_line = self._preview_insight_line(source_payload)
        if not insight_line:
            return base_text

        mention_map = self._mention_map(
            [
                team_name
                for team_name in (
                    self._string(featured_match.get("home_team")),
                    self._string(featured_match.get("away_team")),
                )
                if team_name
            ],
            competition_slug,
            limit=mention_limit,
        )
        lines = [
            self._standard_title(
                content_type=content_type,
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
            ),
            "",
            "Partidos:",
        ]
        for match in matches:
            lines.append(f"{self._string(match.get('home_team')) or '-'} vs {self._string(match.get('away_team')) or '-'}")
        lines.extend(
            [
                "",
                "Partido clave:",
                (
                    f"{self._render_team_label(self._string(featured_match.get('home_team')) or '-', mention_map)} vs "
                    f"{self._render_team_label(self._string(featured_match.get('away_team')) or '-', mention_map)}"
                ),
                insight_line,
                "",
                self._hashtags_line(competition_slug),
            ]
        )
        enriched_text = self._compact_blank_lines("\n".join(lines))
        return enriched_text if len(enriched_text) <= self.max_characters else base_text

    def _viral_ranking_summary(
        self,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
    ) -> str | None:
        ranking_rows = self._ranking_rows(source_payload, unique_teams=True)[:MAX_RANKING_ROWS]
        if not ranking_rows:
            return fallback_text
        for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
            text = self._render_ranking_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                ranking_rows=ranking_rows,
                mention_limit=mention_limit,
            )
            if len(text) <= self.max_characters:
                return text
        return fallback_text

    def _viral_form_ranking(
        self,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
    ) -> str | None:
        ranking_rows = [
            row
            for row in list(source_payload.get("ranking") or [])
            if isinstance(row, dict) and self._string(row.get("team"))
        ][:MAX_RANKING_ROWS]
        if not ranking_rows:
            return fallback_text
        for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
            text = self._render_form_ranking(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                ranking_rows=ranking_rows,
                mention_limit=mention_limit,
            )
            if len(text) <= self.max_characters:
                return text
        return fallback_text

    def _viral_match_result(
        self,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
    ) -> str | None:
        for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
            text = self._render_match_result(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                mention_limit=mention_limit,
            )
            if text is not None and len(text) <= self.max_characters:
                return text
        return fallback_text

    def _render_match_result(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        mention_limit: int,
    ) -> str | None:
        home_team = self._string(source_payload.get("home_team"))
        away_team = self._string(source_payload.get("away_team"))
        if not home_team or not away_team:
            return None
        mention_map = self._mention_map([home_team, away_team], competition_slug, limit=mention_limit)
        lines = [
            self._standard_title(
                content_type=ContentType.MATCH_RESULT,
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
            ),
            "",
            (
                f"{self._render_team_label(home_team, mention_map)} {source_payload.get('home_score')}-"
                f"{source_payload.get('away_score')} {self._render_team_label(away_team, mention_map)}"
            ),
            "",
            self._hashtags_line(competition_slug),
        ]
        return self._compact_blank_lines("\n".join(lines))

    def _leader_insight_line(self, table_insights: dict[str, Any], mention_map: dict[str, str]) -> str | None:
        leader_team = self._string(table_insights.get("leader_team"))
        leader_points = table_insights.get("leader_points")
        if leader_team is None or leader_points is None:
            return None
        leader_label = self._render_team_label(leader_team, mention_map)
        second_team = self._string(table_insights.get("second_team"))
        title_gap = table_insights.get("title_gap")
        if second_team is not None and title_gap is not None:
            second_label = self._render_team_label(second_team, mention_map)
            return f"Liderato: {leader_label} {leader_points} pts | +{title_gap} sobre {second_label}"
        return f"Liderato: {leader_label} {leader_points} pts"

    def _playoff_insight_line(self, table_insights: dict[str, Any], mention_map: dict[str, str]) -> str | None:
        cutoff_team = self._string(table_insights.get("playoff_cutoff_team"))
        cutoff_points = table_insights.get("playoff_cutoff_points")
        outside_team = self._string(table_insights.get("playoff_outside_team"))
        playoff_gap = table_insights.get("playoff_gap")
        if cutoff_team is None or cutoff_points is None or outside_team is None or playoff_gap is None:
            return None
        cutoff_label = self._render_team_label(cutoff_team, mention_map)
        outside_label = self._render_team_label(outside_team, mention_map)
        return f"Corte PO: {cutoff_label} {cutoff_points} pts | +{playoff_gap} sobre {outside_label}"

    def _relegation_insight_line(self, table_insights: dict[str, Any], mention_map: dict[str, str]) -> str | None:
        safe_team = self._string(table_insights.get("safe_team"))
        relegation_team = self._string(table_insights.get("relegation_team"))
        relegation_gap = table_insights.get("relegation_gap")
        if safe_team is None or relegation_team is None or relegation_gap is None:
            return None
        safe_label = self._render_team_label(safe_team, mention_map)
        relegation_label = self._render_team_label(relegation_team, mention_map)
        return f"Salvacion: {safe_label} | +{relegation_gap} sobre {relegation_label}"

    def _preview_insight_line(self, source_payload: dict[str, Any]) -> str | None:
        hooks = source_payload.get("editorial_hooks")
        if isinstance(hooks, list):
            for hook in hooks:
                normalized_hook = self._string(hook)
                if normalized_hook:
                    return normalized_hook
        primary_tag = self._string(source_payload.get("primary_tag"))
        if primary_tag is None:
            tags = source_payload.get("tags")
            if isinstance(tags, list):
                primary_tag = next((self._string(tag) for tag in tags if self._string(tag)), None)
        descriptor = {
            "title_race": "duelo por el liderato",
            "playoff_clash": "duelo directo por playoff",
            "relegation_clash": "cruce por la permanencia",
            "top_table_match": "pulso en la zona alta",
            "hot_form_match": "choque entre equipos en forma",
            "direct_rivalry": "partido entre rivales directos",
            "cold_form_match": "partido con urgencias",
        }.get(primary_tag or "")

        parts: list[str] = []
        home_position = source_payload.get("home_position")
        away_position = source_payload.get("away_position")
        if home_position is not None and away_position is not None:
            parts.append(f"{home_position}o vs {away_position}o")
        if descriptor:
            parts.append(descriptor)
        home_recent_points = source_payload.get("home_recent_points")
        away_recent_points = source_payload.get("away_recent_points")
        if home_recent_points is not None and away_recent_points is not None:
            parts.append(f"{home_recent_points} y {away_recent_points} pts de 15")
        return " | ".join(parts) if parts else None

    def _results_insight_lines(
        self,
        *,
        source_payload: dict[str, Any],
        matches: list[dict[str, Any]],
        competition_slug: str,
        mention_limit: int,
    ) -> list[str]:
        results_insights = source_payload.get("results_insights")
        if not isinstance(results_insights, dict) or not results_insights:
            return []

        available_signatures = {self._result_match_signature(match) for match in matches}
        insight_rows: list[tuple[str, str, str]] = []
        for key, builder in (
            ("table_events", None),
            ("leader_match", self._leader_result_line),
            ("top_match", self._top_match_result_line),
            ("biggest_margin_match", self._biggest_margin_result_line),
            ("highest_scoring_match", self._highest_scoring_result_line),
        ):
            if key == "table_events":
                payload = results_insights.get(key)
                if not isinstance(payload, list):
                    continue
                for event_payload in payload:
                    if not isinstance(event_payload, dict):
                        continue
                    signature = f"event:{self._string(event_payload.get('team')) or '-'}:{self._string(event_payload.get('event_type')) or '-'}"
                    insight_rows.append((key, signature, self._table_event_result_line(event_payload, competition_slug, mention_limit)))
                continue
            payload = results_insights.get(key)
            if not isinstance(payload, dict):
                continue
            signature = self._result_match_signature(payload)
            if signature not in available_signatures:
                continue
            insight_rows.append((key, signature, builder(payload, competition_slug, mention_limit)))

        lines: list[str] = []
        seen_signatures: set[str] = set()
        for _, signature, line in insight_rows:
            if not line or signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            lines.append(line)
        return lines[:2]

    def _leader_result_line(self, payload: dict[str, Any], competition_slug: str, mention_limit: int) -> str | None:
        leader_team = self._string(payload.get("leader_team"))
        home_team = self._string(payload.get("home_team"))
        away_team = self._string(payload.get("away_team"))
        if home_team is None or away_team is None:
            return None
        mention_map = self._mention_map([home_team, away_team], competition_slug, limit=mention_limit)
        score = f"{payload.get('home_score')}-{payload.get('away_score')}"
        result = self._string(payload.get("result"))
        context_suffix = self._team_table_context_suffix(payload)
        if result == "draw":
            line = (
                f"Liderato: {self._render_team_label(home_team, mention_map)} y "
                f"{self._render_team_label(away_team, mention_map)} empatan {score}"
            )
            if context_suffix:
                line = f"{line} | {context_suffix}"
            return line
        if leader_team is None:
            leader_team = home_team if payload.get("home_position") == 1 else away_team if payload.get("away_position") == 1 else None
        if leader_team is None:
            return None
        opponent = away_team if leader_team == home_team else home_team
        leader_label = self._render_team_label(leader_team, mention_map)
        opponent_label = self._render_team_label(opponent, mention_map)
        if payload.get("winner_team") == leader_team:
            line = f"Liderato: {leader_label} gana {score} a {opponent_label}"
        else:
            line = f"Liderato: {leader_label} cae {score} ante {opponent_label}"
        if context_suffix:
            line = f"{line} | {context_suffix}"
        return line

    def _top_match_result_line(self, payload: dict[str, Any], competition_slug: str, mention_limit: int) -> str | None:
        home_team = self._string(payload.get("home_team"))
        away_team = self._string(payload.get("away_team"))
        if home_team is None or away_team is None:
            return None
        mention_map = self._mention_map([home_team, away_team], competition_slug, limit=mention_limit)
        score = f"{payload.get('home_score')}-{payload.get('away_score')}"
        return (
            f"Zona alta: {self._render_team_label(home_team, mention_map)} "
            f"{score} {self._render_team_label(away_team, mention_map)}"
        )

    def _biggest_margin_result_line(self, payload: dict[str, Any], competition_slug: str, mention_limit: int) -> str | None:
        margin = payload.get("goal_margin")
        if not isinstance(margin, int) or margin <= 1:
            return None
        home_team = self._string(payload.get("home_team"))
        away_team = self._string(payload.get("away_team"))
        if home_team is None or away_team is None:
            return None
        mention_map = self._mention_map([home_team, away_team], competition_slug, limit=mention_limit)
        score = f"{payload.get('home_score')}-{payload.get('away_score')}"
        return (
            f"Mayor margen: {self._render_team_label(home_team, mention_map)} "
            f"{score} {self._render_team_label(away_team, mention_map)}"
        )

    def _highest_scoring_result_line(self, payload: dict[str, Any], competition_slug: str, mention_limit: int) -> str | None:
        total_goals = payload.get("total_goals")
        if not isinstance(total_goals, int) or total_goals < 3:
            return None
        home_team = self._string(payload.get("home_team"))
        away_team = self._string(payload.get("away_team"))
        if home_team is None or away_team is None:
            return None
        mention_map = self._mention_map([home_team, away_team], competition_slug, limit=mention_limit)
        score = f"{payload.get('home_score')}-{payload.get('away_score')}"
        return (
            f"Partido con mas goles: {self._render_team_label(home_team, mention_map)} "
            f"{score} {self._render_team_label(away_team, mention_map)}"
        )

    def _table_event_result_line(self, payload: dict[str, Any], competition_slug: str, mention_limit: int) -> str | None:
        team = self._string(payload.get("team"))
        event_type = self._string(payload.get("event_type"))
        if team is None or event_type is None:
            return None
        mention_map = self._mention_map([team], competition_slug, limit=mention_limit)
        team_label = self._render_team_label(team, mention_map)
        current_position = payload.get("current_position")
        position_delta = payload.get("position_delta")
        context_suffix = self._team_table_context_suffix(payload)

        if event_type == "new_leader":
            line = f"Impacto tabla: {team_label} es nuevo lider"
            return f"{line} | {context_suffix}" if context_suffix else line
        if event_type == "entered_playoff":
            line = f"Impacto tabla: {team_label} entra en playoff"
            return f"{line} | {context_suffix}" if context_suffix else line
        if event_type == "left_playoff":
            line = f"Impacto tabla: {team_label} sale del playoff"
            return f"{line} | {context_suffix}" if context_suffix else line
        if event_type == "entered_relegation":
            line = f"Impacto tabla: {team_label} cae a descenso"
            return f"{line} | {context_suffix}" if context_suffix else line
        if event_type == "left_relegation":
            line = f"Impacto tabla: {team_label} sale del descenso"
            return f"{line} | {context_suffix}" if context_suffix else line
        if event_type == "biggest_position_rise" and isinstance(position_delta, int) and position_delta > 0:
            if current_position is not None:
                line = f"Impacto tabla: {team_label} sube {position_delta} puestos hasta el {current_position}o"
            else:
                line = f"Impacto tabla: {team_label} sube {position_delta} puestos"
            return f"{line} | {context_suffix}" if context_suffix else line
        if event_type == "biggest_position_drop" and isinstance(position_delta, int) and position_delta < 0:
            if current_position is not None:
                line = f"Impacto tabla: {team_label} cae {abs(position_delta)} puestos hasta el {current_position}o"
            else:
                line = f"Impacto tabla: {team_label} cae {abs(position_delta)} puestos"
            return f"{line} | {context_suffix}" if context_suffix else line
        return self._string(payload.get("title"))

    def _team_table_context_suffix(self, payload: dict[str, Any]) -> str | None:
        current_position = payload.get("current_position")
        leader_gap = payload.get("leader_gap")
        if current_position == 1 and isinstance(leader_gap, int):
            chaser_team = self._string(payload.get("leader_chaser_team"))
            if chaser_team is not None:
                return f"manda con +{leader_gap} sobre {chaser_team}"
            return f"manda con +{leader_gap}"
        if current_position != 1 and isinstance(leader_gap, int):
            return f"queda a {leader_gap} pts del lider"

        playoff_cutoff_position = payload.get("playoff_cutoff_position")
        playoff_margin = payload.get("playoff_margin")
        if (
            isinstance(playoff_cutoff_position, int)
            and current_position == playoff_cutoff_position
            and isinstance(playoff_margin, int)
        ):
            return f"protege el playoff con +{playoff_margin}"

        playoff_gap_to_cutoff = payload.get("playoff_gap_to_cutoff")
        if isinstance(playoff_gap_to_cutoff, int):
            return f"queda a {playoff_gap_to_cutoff} pt{'s' if playoff_gap_to_cutoff != 1 else ''} del playoff"

        relegation_line = payload.get("relegation_line")
        safe_margin = payload.get("safe_margin")
        if (
            isinstance(relegation_line, int)
            and current_position == relegation_line - 1
            and isinstance(safe_margin, int)
        ):
            return f"deja el descenso a {safe_margin} pt{'s' if safe_margin != 1 else ''}"

        safety_gap = payload.get("safety_gap")
        if isinstance(safety_gap, int):
            return f"queda a {safety_gap} pt{'s' if safety_gap != 1 else ''} de la salvacion"

        return None

    def _result_match_signature(self, payload: dict[str, Any]) -> str:
        return "|".join(
            [
                self._string(payload.get("home_team")) or "-",
                self._string(payload.get("away_team")) or "-",
                str(payload.get("home_score")),
                str(payload.get("away_score")),
            ]
        )

    def resolve_hashtag(self, competition_slug: str, content_type: ContentType) -> str | None:
        del content_type
        return COMPETITION_HASHTAGS.get(competition_slug, "#FutbolBalear")

    def resolve_hashtags(self, competition_slug: str) -> list[str]:
        hashtags = ["#FutbolBalear"]
        competition_hashtag = COMPETITION_HASHTAGS.get(competition_slug)
        if competition_hashtag and competition_hashtag not in hashtags:
            hashtags.append(competition_hashtag)
        return hashtags[:2]

    def _allow_roundup_hashtag_drop(
        self,
        *,
        competition_slug: str,
        content_type: ContentType,
    ) -> bool:
        del competition_slug
        return content_type in {ContentType.RESULTS_ROUNDUP, ContentType.STANDINGS_ROUNDUP}

    def resolve_team_mention(self, team_name: str | None, competition_slug: str | None) -> str:
        if not team_name:
            return ""
        handle = self.identity_service.get_team_handle(team_name, competition_slug)
        return f" {handle}" if handle else ""

    def build_matchday_thread(
        self,
        *,
        competition_name: str,
        group_label: str | None,
        results_text: str | None,
        standings_text: str | None,
        narrative_text: str | None,
    ) -> list[MatchdayThreadPart]:
        parts = [MatchdayThreadPart(slot="header", text="\n".join([part for part in (competition_name, group_label) if part]))]
        if results_text:
            parts.append(MatchdayThreadPart(slot="results", text=results_text))
        if standings_text:
            parts.append(MatchdayThreadPart(slot="standings", text=standings_text))
        if narrative_text:
            parts.append(MatchdayThreadPart(slot="narrative", text=narrative_text))
        return parts

    # ---------------------------------------------------------------------------
    # Title / header building — delegate to editorial_title_builder
    # ---------------------------------------------------------------------------

    def _competition_name(self, competition_slug: str) -> str:
        return get_competition_name(competition_slug)

    def _competition_title(self, competition_slug: str, competition_name: str) -> str:
        return build_competition_title(competition_slug, competition_name)

    def _group_title(self, competition_slug: str, competition_name: str, source_payload: dict[str, Any]) -> str | None:
        return build_group_title(competition_slug, competition_name, source_payload)

    def _round_title(self, source_payload: dict[str, Any]) -> str | None:
        return build_round_title(source_payload)

    def _part_suffix(self, source_payload: dict[str, Any]) -> str | None:
        return build_part_suffix(source_payload)

    def _standard_title(
        self,
        *,
        content_type: ContentType,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        title_override: str | None = None,
        include_round: bool = True,
    ) -> str:
        return build_standard_title(
            content_type=content_type,
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            title_override=title_override,
            include_round=include_round,
        )

    def _roundup_title(
        self,
        *,
        content_type: ContentType,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        compact: bool,
    ) -> str:
        return build_roundup_title(
            content_type=content_type,
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            compact=compact,
        )

    def _ranking_title(self, *, competition_slug: str, competition_name: str, ranking_rows: list[dict[str, Any]]) -> str:
        return build_ranking_title(
            competition_slug=competition_slug,
            competition_name=competition_name,
            ranking_rows=ranking_rows,
        )

    def _narrative_label(self, content_type: ContentType, source_payload: dict[str, Any]) -> str:
        return build_narrative_label(content_type, source_payload)

    def _narrative_title(self, content_type: ContentType, source_payload: dict[str, Any]) -> str:
        return build_narrative_title(content_type, source_payload)

    # ---------------------------------------------------------------------------
    # Mention helpers
    # ---------------------------------------------------------------------------

    def _hashtags_line(self, competition_slug: str) -> str:
        return " ".join(self.resolve_hashtags(competition_slug))

    def _zone_suffix(self, zone_tag: str | None) -> str:
        if zone_tag == "playoff":
            return " [PO]"
        if zone_tag == "relegation":
            return " [DESC]"
        return ""

    def _render_team_label(self, team_name: str, mention_map: dict[str, str]) -> str:
        return mention_map.get(team_name, team_name)

    def _mention_map(self, team_names: list[str], competition_slug: str, *, limit: int) -> dict[str, str]:
        if limit <= 0:
            return {}
        rows: list[tuple[int, int, int, str, str]] = []
        activity_rank_map = {"muy_alta": 5, "alta": 4, "media": 3, "baja_media": 2, "baja": 1}
        for index, team_name in enumerate(team_names):
            social_info = self.identity_service.get_team_social_info(team_name, competition_slug=competition_slug)
            handle = self._string(social_info.get("x_handle"))
            if not handle:
                continue
            rows.append(
                (
                    index,
                    -activity_rank_map.get(str(social_info.get("activity_level") or ""), 0),
                    -int(social_info.get("followers_approx") or 0),
                    team_name,
                    handle,
                )
            )
        rows.sort()
        selected: dict[str, str] = {}
        seen_handles: set[str] = set()
        for _, _, _, team_name, handle in rows:
            if team_name in selected or handle.lower() in seen_handles:
                continue
            selected[team_name] = handle
            seen_handles.add(handle.lower())
            if len(selected) >= limit:
                break
        return selected

    # ---------------------------------------------------------------------------
    # Normalisation helpers
    # ---------------------------------------------------------------------------

    def _normalize_alias_text(self, text: str) -> str:
        normalized_text = text
        for raw_name, editorial_name in load_team_name_aliases().items():
            normalized_text = normalized_text.replace(raw_name, editorial_name)
        return normalized_text

    def _normalize_match(self, value: Any) -> dict[str, Any] | Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for field in ("home_team", "away_team", "team"):
            team_name = self._string(normalized.get(field))
            if team_name:
                normalized[field] = normalize_team_name(team_name)
        if isinstance(normalized.get("teams"), list):
            normalized["teams"] = [normalize_team_name(item) if isinstance(item, str) else item for item in normalized["teams"]]
        return normalized

    def _normalize_matches(self, value: Any) -> list[dict[str, Any]] | Any:
        return [self._normalize_match(match) for match in value] if isinstance(value, list) else value

    def _normalize_standings_rows(self, value: Any) -> list[dict[str, Any]] | Any:
        if not isinstance(value, list):
            return value
        normalized_rows: list[dict[str, Any]] = []
        for row in value:
            if not isinstance(row, dict):
                normalized_rows.append(row)
                continue
            normalized_row = dict(row)
            team_name = self._string(normalized_row.get("team"))
            if team_name:
                normalized_row["team"] = normalize_team_name(team_name)
            normalized_rows.append(normalized_row)
        return normalized_rows

    def _normalize_ranking_entry(self, value: Any) -> dict[str, Any] | Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        team_name = self._string(normalized.get("team"))
        if team_name:
            normalized["team"] = normalize_team_name(team_name)
        return normalized

    def _preview_matches(self, source_payload: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
        matches = [match for match in list(source_payload.get("matches") or []) if isinstance(match, dict)]
        if matches:
            return matches[:limit]
        featured_match = source_payload.get("featured_match")
        if isinstance(featured_match, dict):
            return [featured_match]
        if self._string(source_payload.get("home_team")) and self._string(source_payload.get("away_team")):
            return [{"home_team": source_payload.get("home_team"), "away_team": source_payload.get("away_team"), "round_name": source_payload.get("round_name")}]
        return []

    def _featured_match(self, source_payload: dict[str, Any], matches: list[dict[str, Any]]) -> dict[str, Any] | None:
        featured_match = source_payload.get("featured_match")
        if isinstance(featured_match, dict):
            return featured_match
        return matches[0] if matches else None

    def _ranking_rows(self, source_payload: dict[str, Any], *, unique_teams: bool) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen_teams: set[str] = set()
        for key, title in RANKING_TITLE_BY_KEY.items():
            value = source_payload.get(key)
            if not isinstance(value, dict):
                continue
            team_name = self._string(value.get("team"))
            if not team_name:
                continue
            normalized_team = normalize_team_identity_value(team_name)
            if unique_teams and normalized_team in seen_teams:
                continue
            seen_teams.add(normalized_team)
            rows.append({"key": key, "title": title, "team": team_name, "value": value.get("value")})
        return rows

    def _unique(self, values) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    def _string(self, value: Any) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return None

    def _compact_blank_lines(self, text: str) -> str:
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text.strip()

    def normalize_team_identity(self, team_name: str) -> str:
        return normalize_team_identity_value(team_name)
