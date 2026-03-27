from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentType, FormEventType, NarrativeMetricType, StandingsEventType, ViralStoryType
from app.db.models import ContentCandidate
from app.normalizers.text import normalize_token
from app.schemas.editorial_content import ContentCandidateDraft
from app.services.social_enricher import SocialEnricherService
from app.services.social_identity_service import SocialIdentityService
from app.services.team_name_normalizer import load_team_name_aliases, normalize_team_name

MAX_FORMATTED_CHARACTERS = 240
MAX_RESULTS_MATCHES = 4
MAX_PREVIEW_MATCHES = 3
MAX_RANKING_ROWS = 3
IDEAL_MENTION_LIMIT = 2
GROUP_PATTERN = re.compile(r"(?:^|[\s_-])g(?:rupo)?\s*0*(\d+)(?:$|[\s_-])", re.IGNORECASE)
ROUND_PATTERN = re.compile(r"(?:j(?:ornada)?\.?\s*)0*(\d+)", re.IGNORECASE)
CLUB_PREFIXES = {"cd", "cf", "ce", "ue", "ud", "rcd", "scr", "atletico", "atl", "fc"}
COMPETITION_HASHTAGS = {
    "tercera_rfef_g11": "#3aRFEF",
    "segunda_rfef_g3_baleares": "#2aRFEF",
    "division_honor_mallorca": "#DH",
}
COMPETITION_SHORT_NAMES = {
    "tercera_rfef_g11": "3ª RFEF",
    "segunda_rfef_g3_baleares": "2ª RFEF",
    "division_honor_mallorca": "DH Mallorca",
}
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
    ContentType.VIRAL_STORY,
    ContentType.FORM_EVENT,
    ContentType.STANDINGS_EVENT,
    ContentType.FEATURED_MATCH_EVENT,
}
TITLE_SPECS = {
    ContentType.MATCH_RESULT: ("📋", "Resultado"),
    ContentType.RESULTS_ROUNDUP: ("📋", "Resultados"),
    ContentType.STANDINGS: ("📊", "Clasificación"),
    ContentType.STANDINGS_ROUNDUP: ("📊", "Clasificación"),
    ContentType.PREVIEW: ("🔎", "Previa"),
    ContentType.FEATURED_MATCH_PREVIEW: ("🔎", "Previa"),
}
RANKING_TITLE_BY_KEY = {
    "best_attack": "Mejor ataque",
    "best_defense": "Más sólida atrás",
    "most_wins": "Más victorias",
}
NARRATIVE_EMOJIS = {
    "Forma": "💪🏼",
    "Tendencia": "📈",
    "Dato": "🔥",
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
        matches = [match for match in list(source_payload.get("matches") or []) if isinstance(match, dict)][:MAX_RESULTS_MATCHES]
        if not matches:
            return None
        for selected_count in range(len(matches), 0, -1):
            text = self._render_results_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                matches=matches[:selected_count],
                mention_limit=0,
            )
            if len(text) <= self.max_characters:
                return text
        return self._render_results_summary(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            matches=matches[:1],
            mention_limit=0,
        )

    def _render_results_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        matches: list[dict[str, Any]],
        mention_limit: int,
    ) -> str:
        team_names = self._unique(
            team_name
            for match in matches
            for team_name in (self._string(match.get("home_team")), self._string(match.get("away_team")))
            if team_name
        )
        mention_map = self._mention_map(team_names, competition_slug, limit=mention_limit)
        lines = [
            self._standard_title(
                content_type=ContentType.RESULTS_ROUNDUP,
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
            ),
            "",
        ]
        for match in matches:
            home_team = self._string(match.get("home_team")) or "-"
            away_team = self._string(match.get("away_team")) or "-"
            lines.append(
                f"{self._render_team_label(home_team, mention_map)} {int(match.get('home_score') or 0)}-"
                f"{int(match.get('away_score') or 0)} {self._render_team_label(away_team, mention_map)}"
            )
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
        for selected_count in range(len(ordered_rows), 0, -1):
            text = self._render_standings_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                rows=ordered_rows[:selected_count],
                content_type=content_type,
                mention_limit=0,
            )
            if len(text) <= self.max_characters:
                return text
        return self._render_standings_summary(
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
            rows=ordered_rows[:1],
            content_type=content_type,
            mention_limit=0,
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
    ) -> str:
        ordered_rows = sorted(rows, key=lambda row: int(row.get("position") or 999))
        mention_map = self._mention_map(
            [self._string(row.get("team")) or "-" for row in ordered_rows],
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
        ]
        for row in ordered_rows:
            position = int(row.get("position") or 0)
            team_name = self._string(row.get("team")) or "-"
            points = row.get("points")
            lines.append(
                f"{position}. {self._render_team_label(team_name, mention_map)} - {points} pts"
                f"{self._zone_suffix(self._string(row.get('zone_tag')))}"
            )
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
                "",
                self._hashtags_line(competition_slug),
            ]
        )
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
        matches = [match for match in list(source_payload.get("matches") or []) if isinstance(match, dict)][:MAX_RESULTS_MATCHES]
        if not matches:
            return fallback_text
        for selected_count in range(len(matches), 0, -1):
            for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
                text = self._render_results_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    source_payload=source_payload,
                    matches=matches[:selected_count],
                    mention_limit=mention_limit,
                )
                if len(text) <= self.max_characters:
                    return text
        return fallback_text

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
        for selected_count in range(len(rows), 0, -1):
            for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
                text = self._render_standings_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    source_payload=source_payload,
                    rows=rows[:selected_count],
                    content_type=content_type,
                    mention_limit=mention_limit,
                )
                if len(text) <= self.max_characters:
                    return text
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
            text = self._render_preview_summary(
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

    def resolve_hashtag(self, competition_slug: str, content_type: ContentType) -> str | None:
        del content_type
        return COMPETITION_HASHTAGS.get(competition_slug, "#FutbolBalear")

    def resolve_hashtags(self, competition_slug: str) -> list[str]:
        hashtags = ["#FutbolBalear"]
        competition_hashtag = COMPETITION_HASHTAGS.get(competition_slug)
        if competition_hashtag and competition_hashtag not in hashtags:
            hashtags.append(competition_hashtag)
        return hashtags[:2]

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

    def _competition_name(self, competition_slug: str) -> str:
        definition = self.catalog.get(competition_slug)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        return competition_slug

    def _competition_title(self, competition_slug: str, competition_name: str) -> str:
        if competition_slug in COMPETITION_SHORT_NAMES:
            return COMPETITION_SHORT_NAMES[competition_slug]
        lowered_name = competition_name.lower()
        if "tercera" in lowered_name or "3a rfef" in lowered_name or "3ª rfef" in lowered_name:
            return "3ª RFEF"
        if "segunda" in lowered_name or "2a rfef" in lowered_name or "2ª rfef" in lowered_name:
            return "2ª RFEF"
        if "division" in lowered_name and "honor" in lowered_name:
            return "DH Mallorca"
        return competition_name.strip()

    def _group_title(self, competition_slug: str, competition_name: str, source_payload: dict[str, Any]) -> str | None:
        for raw_value in (
            source_payload.get("group_code"),
            source_payload.get("group_label"),
            competition_slug.replace("_", " "),
            competition_name,
        ):
            value = self._string(raw_value)
            if not value:
                continue
            match = GROUP_PATTERN.search(f" {value} ")
            if match:
                return f"G{int(match.group(1))}"
        return None

    def _round_title(self, source_payload: dict[str, Any]) -> str | None:
        for raw_value in (source_payload.get("round_name"), source_payload.get("group_label")):
            round_label = self._round_from_value(raw_value)
            if round_label:
                return round_label
        featured_match = source_payload.get("featured_match")
        if isinstance(featured_match, dict):
            round_label = self._round_from_value(featured_match.get("round_name"))
            if round_label:
                return round_label
        matches = source_payload.get("matches")
        if isinstance(matches, list):
            for match in matches:
                if isinstance(match, dict):
                    round_label = self._round_from_value(match.get("round_name"))
                    if round_label:
                        return round_label
        rows = source_payload.get("rows")
        if isinstance(rows, list) and rows:
            played_values = {
                int(row.get("played"))
                for row in rows
                if isinstance(row, dict) and isinstance(row.get("played"), int) and int(row.get("played")) > 0
            }
            if played_values:
                return f"J{max(played_values)}"
        return None

    def _round_from_value(self, value: Any) -> str | None:
        raw_value = self._string(value)
        if not raw_value:
            return None
        match = ROUND_PATTERN.search(raw_value)
        if match:
            return f"J{int(match.group(1))}"
        return f"J{int(raw_value)}" if raw_value.isdigit() else None

    def _part_suffix(self, source_payload: dict[str, Any]) -> str | None:
        part_index = source_payload.get("part_index")
        part_total = source_payload.get("part_total")
        if isinstance(part_index, int) and isinstance(part_total, int) and part_total > 1:
            return f"({part_index}/{part_total})"
        return None

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
        if title_override is None:
            emoji, label = TITLE_SPECS.get(content_type, ("📝", "Contenido"))
            title_override = f"{emoji} {label}"
        parts = [title_override, self._competition_title(competition_slug, competition_name)]
        group_title = self._group_title(competition_slug, competition_name, source_payload)
        if group_title:
            parts.append(group_title)
        if include_round:
            round_title = self._round_title(source_payload)
            if round_title:
                parts.append(round_title)
        title = " - ".join(parts)
        part_suffix = self._part_suffix(source_payload)
        if part_suffix:
            title = f"{title} {part_suffix}"
        return title

    def _hashtags_line(self, competition_slug: str) -> str:
        return " ".join(self.resolve_hashtags(competition_slug))

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

    def _ranking_title(self, *, competition_slug: str, competition_name: str, ranking_rows: list[dict[str, Any]]) -> str:
        labels = [str(row.get("title") or "Ranking") for row in ranking_rows]
        title_label = labels[0] if len(labels) == 1 else " / ".join(labels)
        if len(title_label) > 40:
            title_label = labels[0]
        return self._standard_title(
            content_type=ContentType.RANKING,
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload={},
            title_override=f"🏆 {title_label}",
            include_round=False,
        )

    def _narrative_label(self, content_type: ContentType, source_payload: dict[str, Any]) -> str:
        if content_type == ContentType.STANDINGS_EVENT:
            event_type = self._string(source_payload.get("event_type"))
            if event_type == str(StandingsEventType.NEW_LEADER):
                return "Nuevo líder"
            if event_type in {str(StandingsEventType.ENTERED_PLAYOFF), str(StandingsEventType.LEFT_PLAYOFF)}:
                return "Playoff"
            if event_type in {str(StandingsEventType.ENTERED_RELEGATION), str(StandingsEventType.LEFT_RELEGATION)}:
                return "Descenso"
            return "Dato"
        if content_type == ContentType.FORM_EVENT:
            return "Forma"
        if content_type == ContentType.METRIC_NARRATIVE:
            narrative_type = self._string(source_payload.get("narrative_type"))
            if narrative_type in {str(NarrativeMetricType.WIN_STREAK), str(NarrativeMetricType.UNBEATEN_STREAK)}:
                return "Forma"
            return "Dato"
        if content_type == ContentType.VIRAL_STORY:
            story_type = self._string(source_payload.get("story_type"))
            if story_type in {str(ViralStoryType.WIN_STREAK), str(ViralStoryType.UNBEATEN_STREAK), str(ViralStoryType.LOSING_STREAK)}:
                return "Forma"
            if story_type in {str(ViralStoryType.HOT_FORM), str(ViralStoryType.COLD_FORM), str(ViralStoryType.GOALS_TREND)}:
                return "Tendencia"
            return "Dato"
        if content_type == ContentType.FEATURED_MATCH_EVENT:
            tags = source_payload.get("tags")
            if isinstance(tags, list):
                if "playoff_clash" in tags:
                    return "Playoff"
                if "relegation_clash" in tags:
                    return "Descenso"
                if "hot_form_match" in tags or "cold_form_match" in tags:
                    return "Forma"
            return "Dato"
        return "Dato"

    def _narrative_title(self, content_type: ContentType, source_payload: dict[str, Any]) -> str:
        label = self._narrative_label(content_type, source_payload)
        emoji = NARRATIVE_EMOJIS.get(label, "🔥")
        return f"{emoji} {label}"

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
