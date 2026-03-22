from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentType
from app.db.models import ContentCandidate, TeamMention
from app.normalizers.text import normalize_token
from app.schemas.editorial_content import ContentCandidateDraft
from app.services.social_enricher import SocialEnricherService
from app.services.social_identity_service import SocialIdentityService
from app.services.team_name_normalizer import load_team_name_aliases, normalize_team_name

MAX_FORMATTED_CHARACTERS = 240
MAX_RESULTS_MATCHES = 8
MAX_PREVIEW_MATCHES = 2
MAX_VIRAL_RESULTS_MATCHES = 5
MAX_VIRAL_STANDINGS_ROWS = 4
MAX_VIRAL_RANKING_ROWS = 3
IDEAL_MENTION_LIMIT = 2
NUMBER_EMOJIS = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
}
VIRAL_TITLE_BY_CONTENT_TYPE = {
    ContentType.RESULTS_ROUNDUP: "📋 Resultados",
    ContentType.STANDINGS: "📊 Clasificación",
    ContentType.STANDINGS_ROUNDUP: "📊 Clasificación",
    ContentType.PREVIEW: "🔎 Previa",
    ContentType.RANKING: "🏆 Ranking",
}
ACTIVITY_RANK = {
    "muy_alta": 5,
    "alta": 4,
    "media": 3,
    "baja_media": 2,
    "baja": 1,
}
HASHTAG_BY_COMPETITION = {
    "tercera_rfef_g11": "#TerceraRFEF",
    "segunda_rfef_g3_baleares": "#SegundaRFEF",
    "division_honor_mallorca": "#FutbolBalear",
}
NARRATIVE_TYPES = {
    ContentType.STAT_NARRATIVE,
    ContentType.METRIC_NARRATIVE,
    ContentType.VIRAL_STORY,
    ContentType.FORM_EVENT,
    ContentType.STANDINGS_EVENT,
    ContentType.FEATURED_MATCH_EVENT,
}
CLUB_PREFIXES = {
    "cd",
    "cf",
    "ce",
    "ue",
    "ud",
    "rcd",
    "scr",
    "atletico",
    "atl",
    "fc",
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
        self._mentions_cache: list[TeamMention] | None = None

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
        if text is None and content_type == ContentType.RANKING:
            text = normalized_text_draft
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
        return EditorialTextLayers(
            formatted_text=text,
            enriched_text=enriched_text,
            viral_formatted_text=viral_formatted_text,
        )

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
        if text is None and content_type == ContentType.RANKING:
            text = normalized_text_draft
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
        return EditorialTextLayers(
            formatted_text=text,
            enriched_text=enriched_text,
            viral_formatted_text=viral_formatted_text,
        )

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
        if content_type not in {
            ContentType.RESULTS_ROUNDUP,
            ContentType.STANDINGS,
            ContentType.STANDINGS_ROUNDUP,
            ContentType.PREVIEW,
            ContentType.RANKING,
        }:
            return normalized_text_draft, payload_json

        normalized_payload_json = dict(payload_json)
        source_payload = payload_json.get("source_payload")
        if not isinstance(source_payload, dict):
            return normalized_text_draft, normalized_payload_json

        normalized_source_payload = dict(source_payload)
        if content_type == ContentType.RESULTS_ROUNDUP:
            normalized_source_payload["matches"] = self._normalize_matches(source_payload.get("matches"))
        elif content_type in {ContentType.STANDINGS, ContentType.STANDINGS_ROUNDUP}:
            normalized_source_payload["rows"] = self._normalize_standings_rows(source_payload.get("rows"))
        elif content_type == ContentType.PREVIEW:
            normalized_source_payload["featured_match"] = self._normalize_match(source_payload.get("featured_match"))
            normalized_source_payload["matches"] = self._normalize_matches(source_payload.get("matches"))
        elif content_type == ContentType.RANKING:
            for key in ("best_attack", "best_defense", "most_wins"):
                normalized_source_payload[key] = self._normalize_ranking_entry(source_payload.get(key))

        normalized_payload_json["source_payload"] = normalized_source_payload
        return normalized_text_draft, normalized_payload_json

    def enrich_text(
        self,
        *,
        competition_slug: str,
        content_type: ContentType,
        text: str | None,
        payload_json: dict[str, Any],
    ) -> str | None:
        return self._enrich_text(
            competition_slug=competition_slug,
            content_type=content_type,
            text=text,
            payload_json=payload_json,
        )

    def viral_format_text(
        self,
        *,
        competition_slug: str,
        content_type: ContentType,
        text: str | None,
        enriched_text: str | None,
        payload_json: dict[str, Any],
    ) -> str | None:
        return self._viral_format_text(
            competition_slug=competition_slug,
            content_type=content_type,
            text=text,
            enriched_text=enriched_text,
            payload_json=payload_json,
        )

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
            return self.format_results_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
            )
        if content_type in {ContentType.STANDINGS, ContentType.STANDINGS_ROUNDUP}:
            return self.format_standings_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
            )
        if content_type == ContentType.PREVIEW:
            return self.format_preview_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
            )
        if content_type == ContentType.RANKING:
            return self.format_ranking_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
            )
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
        matches = list(source_payload.get("matches") or [])[:MAX_RESULTS_MATCHES]
        if not matches:
            return None
        group_label = self._group_label(source_payload.get("group_label"))
        hashtag = self.resolve_hashtag(competition_slug, ContentType.RESULTS_ROUNDUP)
        include_goals = True
        include_mentions = True
        include_hashtag = bool(hashtag)
        selected_count = len(matches)

        while selected_count >= 1:
            text = self._render_results_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                group_label=group_label,
                matches=matches[:selected_count],
                include_goals=include_goals,
                include_mentions=include_mentions,
                hashtag=hashtag if include_hashtag else None,
            )
            if len(text) <= self.max_characters:
                return text
            if include_goals:
                include_goals = False
                continue
            if include_mentions:
                include_mentions = False
                continue
            if selected_count > 1:
                selected_count -= 1
                continue
            if include_hashtag:
                include_hashtag = False
                continue
            return text
        return None

    def _render_results_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        group_label: str | None,
        matches: list[dict[str, Any]],
        include_goals: bool,
        include_mentions: bool,
        hashtag: str | None,
    ) -> str:
        lines = ["📋 RESULTADOS", "", competition_name]
        if group_label:
            lines.append(group_label)
        lines.append("")
        total_goals = 0
        for match in matches:
            home_score = int(match.get("home_score") or 0)
            away_score = int(match.get("away_score") or 0)
            total_goals += home_score + away_score
            lines.append(
                (
                    f"{match.get('home_team', '').strip()}"
                    f"{self.resolve_team_mention(match.get('home_team'), competition_slug) if include_mentions else ''} "
                    f"{home_score}-{away_score} "
                    f"{match.get('away_team', '').strip()}"
                    f"{self.resolve_team_mention(match.get('away_team'), competition_slug) if include_mentions else ''}"
                ).strip()
            )
        if include_goals:
            lines.extend(["", f"⚽ {total_goals} goles en la jornada"])
        if hashtag:
            lines.extend(["", hashtag])
        return "\n".join(lines)

    def format_standings_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
    ) -> str | None:
        rows = list(source_payload.get("rows") or [])
        if not rows:
            return None
        group_label = self._group_label(source_payload.get("group_label"))
        hashtag = self.resolve_hashtag(competition_slug, ContentType.STANDINGS_ROUNDUP)
        include_mentions = True
        include_hashtag = bool(hashtag)
        selected_count = len(rows)

        while selected_count >= 1:
            text = self._render_standings_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                group_label=group_label,
                rows=rows[:selected_count],
                include_mentions=include_mentions,
                hashtag=hashtag if include_hashtag else None,
            )
            if len(text) <= self.max_characters:
                return text
            if include_mentions:
                include_mentions = False
                continue
            if include_hashtag:
                include_hashtag = False
                continue
            if selected_count > 1:
                selected_count -= 1
                continue
            return text
        return None

    def _render_standings_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        group_label: str | None,
        rows: list[dict[str, Any]],
        include_mentions: bool,
        hashtag: str | None,
    ) -> str:
        ordered_rows = sorted(rows, key=lambda row: int(row.get("position") or 0))
        lines = ["📊 CLASIFICACION", "", competition_name]
        if group_label:
            lines.append(group_label)
        lines.append("")
        previous_position: int | None = None
        for row in ordered_rows:
            position = int(row.get("position") or 0)
            if previous_position is not None and position > previous_position + 1:
                lines.append("...")
            prefix = NUMBER_EMOJIS.get(position, f"{position}.")
            zone_suffix = ""
            zone_tag = row.get("zone_tag")
            if zone_tag == "playoff":
                zone_suffix = " [PO]"
            elif zone_tag == "relegation":
                zone_suffix = " [DESC]"
            team = str(row.get("team") or "").strip()
            mention = self.resolve_team_mention(team, competition_slug) if include_mentions else ""
            points = row.get("points")
            lines.append(f"{prefix} {team}{mention} - {points}{zone_suffix}".strip())
            previous_position = position
        if hashtag:
            lines.extend(["", hashtag])
        return "\n".join(lines)

    def format_preview_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
    ) -> str | None:
        matches = list(source_payload.get("matches") or [])
        if not matches:
            return None
        group_label = self._group_label(self._preview_group_label(matches))
        hashtag = self.resolve_hashtag(competition_slug, ContentType.PREVIEW)
        include_hashtag = bool(hashtag)
        selected_count = min(len(matches), MAX_PREVIEW_MATCHES)

        while selected_count >= 1:
            text = self._render_preview_summary(
                competition_name=competition_name,
                group_label=group_label,
                matches=matches[:selected_count],
                hashtag=hashtag if include_hashtag else None,
            )
            if len(text) <= self.max_characters:
                return text
            if include_hashtag:
                include_hashtag = False
                continue
            if selected_count > 1:
                selected_count -= 1
                continue
            return text
        return None

    def _render_preview_summary(
        self,
        *,
        competition_name: str,
        group_label: str | None,
        matches: list[dict[str, Any]],
        hashtag: str | None,
    ) -> str:
        lines = ["PREVIA", competition_name]
        if group_label:
            lines.append(group_label)
        for match in matches:
            home_team = str(match.get("home_team") or "").strip()
            away_team = str(match.get("away_team") or "").strip()
            lines.append(f"{home_team} vs {away_team}".strip())
        if hashtag:
            lines.append(hashtag)
        return "\n".join(lines)

    def format_ranking_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
    ) -> str | None:
        ranking_rows = self._ranking_rows(source_payload)
        if not ranking_rows:
            return None
        hashtag = self.resolve_hashtag(competition_slug, ContentType.RANKING)
        selected_count = min(len(ranking_rows), MAX_VIRAL_RANKING_ROWS)
        include_hashtag = bool(hashtag)

        while selected_count >= 1:
            text = self._render_ranking_summary(
                competition_name=competition_name,
                ranking_rows=ranking_rows[:selected_count],
                hashtag=hashtag if include_hashtag else None,
            )
            if len(text) <= self.max_characters:
                return text
            if include_hashtag:
                include_hashtag = False
                continue
            if selected_count > 1:
                selected_count -= 1
                continue
            return text
        return None

    def _render_ranking_summary(
        self,
        *,
        competition_name: str,
        ranking_rows: list[dict[str, Any]],
        hashtag: str | None,
    ) -> str:
        lines = ["🏆 RANKING", "", competition_name]
        for index, row in enumerate(ranking_rows, start=1):
            title = str(row.get("title") or "Ranking")
            team_name = str(row.get("team") or "-")
            value = row.get("value")
            if value is None:
                lines.append(f"{index}. {title}: {team_name}")
            else:
                lines.append(f"{index}. {title}: {team_name} — {value}")
        if hashtag:
            lines.extend(["", hashtag])
        return "\n".join(lines)

    def format_narrative(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        content_type: ContentType,
        source_payload: dict[str, Any],
        base_text: str,
    ) -> str | None:
        hashtag = self.resolve_hashtag(competition_slug, content_type)
        team = self._primary_team(source_payload)
        team_line = team or ""
        mention = self.resolve_team_mention(team, competition_slug) if team else ""
        metric_value = source_payload.get("metric_value")
        kind = str(
            source_payload.get("story_type")
            or source_payload.get("narrative_type")
            or source_payload.get("event_type")
            or ""
        )

        if team and isinstance(metric_value, (int, float)) and kind in {"win_streak", "unbeaten_streak", "losing_streak"}:
            label = (
                "sin perder"
                if kind == "unbeaten_streak"
                else "victorias consecutivas"
                if kind == "win_streak"
                else "derrotas seguidas"
            )
            lines = [
                "🔥 RACHA",
                "",
                f"{team_line}{mention}",
                "",
                f"{int(metric_value)} partidos consecutivos",
                f"{label} en {competition_name}.",
            ]
            if hashtag:
                lines.extend(["", hashtag])
            text = "\n".join(lines)
            if len(text) <= self.max_characters:
                return text

        normalized_base = " ".join(base_text.split())
        if not normalized_base:
            return None
        text = f"🔥 {normalized_base}"
        if hashtag and len(text) + 2 + len(hashtag) <= self.max_characters:
            text = f"{text}\n\n{hashtag}"
        return text

    def format_match_result(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        base_text: str,
    ) -> str | None:
        home_team = str(source_payload.get("home_team") or "").strip()
        away_team = str(source_payload.get("away_team") or "").strip()
        home_score = source_payload.get("home_score")
        away_score = source_payload.get("away_score")
        if not home_team or not away_team or home_score is None or away_score is None:
            return " ".join(base_text.split()) or None
        hashtag = self.resolve_hashtag(competition_slug, ContentType.MATCH_RESULT)
        lines = [
            "📋 RESULTADO",
            "",
            f"{home_team}{self.resolve_team_mention(home_team, competition_slug)} {home_score}-{away_score} {away_team}{self.resolve_team_mention(away_team, competition_slug)}".strip(),
            competition_name,
        ]
        if hashtag:
            lines.extend(["", hashtag])
        text = "\n".join(lines)
        if len(text) <= self.max_characters:
            return text
        lines = [
            "📋 RESULTADO",
            "",
            f"{home_team} {home_score}-{away_score} {away_team}",
            competition_name,
        ]
        if hashtag:
            lines.extend(["", hashtag])
        return "\n".join(lines)

    def resolve_team_mention(self, team_name: str | None, competition_slug: str | None) -> str:
        if not team_name:
            return ""
        handle = self.identity_service.get_team_handle(team_name, competition_slug)
        if handle:
            return f" {handle}"
        return ""

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
        return self.social_enricher.enrich_text_with_mentions(
            text,
            payload_json,
            str(content_type),
            competition_slug=competition_slug,
        )

    def resolve_hashtag(self, competition_slug: str, content_type: ContentType) -> str | None:
        if content_type in {
            ContentType.MATCH_RESULT,
            ContentType.RESULTS_ROUNDUP,
            ContentType.STANDINGS,
            ContentType.STANDINGS_ROUNDUP,
            ContentType.PREVIEW,
        }:
            return HASHTAG_BY_COMPETITION.get(competition_slug, "#FutbolBalear")
        if content_type in NARRATIVE_TYPES:
            return HASHTAG_BY_COMPETITION.get(competition_slug, "#FutbolBalear")
        return HASHTAG_BY_COMPETITION.get(competition_slug)

    def resolve_hashtags(self, competition_slug: str) -> list[str]:
        hashtags = ["#FutbolBalear"]
        competition_hashtag = HASHTAG_BY_COMPETITION.get(competition_slug)
        if competition_hashtag and competition_hashtag not in hashtags:
            hashtags.append(competition_hashtag)
        return hashtags[:2]

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
            return self._viral_results_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                fallback_text=fallback_text,
            )
        if content_type in {ContentType.STANDINGS, ContentType.STANDINGS_ROUNDUP}:
            return self._viral_standings_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                fallback_text=fallback_text,
            )
        if content_type == ContentType.PREVIEW:
            return self._viral_preview_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                fallback_text=fallback_text,
            )
        if content_type == ContentType.RANKING:
            return self._viral_ranking_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                source_payload=source_payload,
                fallback_text=fallback_text,
            )
        return None

    def _viral_results_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
    ) -> str | None:
        matches = [match for match in list(source_payload.get("matches") or []) if isinstance(match, dict)]
        if not matches:
            return fallback_text
        hashtags = self.resolve_hashtags(competition_slug)
        prioritized_matches = self._prioritized_results_matches(matches, competition_slug)
        for selected_count in range(min(MAX_VIRAL_RESULTS_MATCHES, len(prioritized_matches)), 0, -1):
            for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
                text = self._render_viral_results_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    matches=prioritized_matches[:selected_count],
                    mention_limit=mention_limit,
                    hashtags=hashtags,
                )
                if len(text) <= self.max_characters:
                    return text
        return fallback_text

    def _render_viral_results_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        matches: list[dict[str, Any]],
        mention_limit: int,
        hashtags: list[str],
    ) -> str:
        team_names = self._unique(
            team_name
            for match in matches
            for team_name in (
                self._string(match.get("home_team")),
                self._string(match.get("away_team")),
            )
            if team_name
        )
        mention_map = self._mention_map(team_names, competition_slug, limit=mention_limit)
        lines = [f"{VIRAL_TITLE_BY_CONTENT_TYPE[ContentType.RESULTS_ROUNDUP]} {competition_name}", ""]
        for match in matches:
            home_team = self._string(match.get("home_team")) or "-"
            away_team = self._string(match.get("away_team")) or "-"
            home_score = int(match.get("home_score") or 0)
            away_score = int(match.get("away_score") or 0)
            lines.append(
                f"{self._render_results_team_label(home_team, mention_map)} {home_score}-{away_score} {self._render_results_team_label(away_team, mention_map)}"
            )
        lines.extend(["", " ".join(hashtags)])
        return self._compact_blank_lines("\n".join(lines))

    def _viral_standings_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
    ) -> str | None:
        rows = [row for row in list(source_payload.get("rows") or []) if isinstance(row, dict)]
        if not rows:
            return fallback_text
        rows = sorted(rows, key=lambda row: int(row.get("position") or 999))
        hashtags = self.resolve_hashtags(competition_slug)
        selected_rows = rows[: min(MAX_VIRAL_STANDINGS_ROWS, len(rows))]
        for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
            text = self._render_viral_standings_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                rows=selected_rows,
                mention_limit=mention_limit,
                hashtags=hashtags,
            )
            if len(text) <= self.max_characters:
                return text
        return fallback_text

    def _render_viral_standings_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        rows: list[dict[str, Any]],
        mention_limit: int,
        hashtags: list[str],
    ) -> str:
        team_names = [self._string(row.get("team")) for row in rows if self._string(row.get("team"))]
        mention_map = self._mention_map(team_names, competition_slug, limit=mention_limit, min_activity_rank=4)
        lines = [f"{VIRAL_TITLE_BY_CONTENT_TYPE[ContentType.STANDINGS_ROUNDUP]} {competition_name}", ""]
        for row in rows:
            position = int(row.get("position") or 0)
            team_name = self._string(row.get("team")) or "-"
            points = row.get("points")
            lines.append(f"{position}. {self._render_team_label(team_name, mention_map)} — {points}")
        lines.extend(["", " ".join(hashtags)])
        return self._compact_blank_lines("\n".join(lines))

    def _viral_preview_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
    ) -> str | None:
        featured_match = source_payload.get("featured_match")
        if not isinstance(featured_match, dict):
            matches = source_payload.get("matches")
            if isinstance(matches, list) and matches:
                featured_match = matches[0]
        if not isinstance(featured_match, dict):
            return fallback_text
        hashtags = self.resolve_hashtags(competition_slug)
        for include_context in (True, False):
            for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
                text = self._render_viral_preview_summary(
                    competition_slug=competition_slug,
                    competition_name=competition_name,
                    featured_match=featured_match,
                    mention_limit=mention_limit,
                    hashtags=hashtags,
                    include_context=include_context,
                )
                if len(text) <= self.max_characters:
                    return text
        return fallback_text

    def _render_viral_preview_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        featured_match: dict[str, Any],
        mention_limit: int,
        hashtags: list[str],
        include_context: bool,
    ) -> str:
        home_team = self._string(featured_match.get("home_team")) or "-"
        away_team = self._string(featured_match.get("away_team")) or "-"
        mention_map = self._mention_map([home_team, away_team], competition_slug, limit=mention_limit)
        lines = [f"{VIRAL_TITLE_BY_CONTENT_TYPE[ContentType.PREVIEW]} {competition_name}", ""]
        lines.append("Partido clave:")
        lines.append(
            f"{self._render_team_label(home_team, mention_map)} vs {self._render_team_label(away_team, mention_map)}"
        )
        if include_context:
            context = self._string(featured_match.get("round_name")) or self._string(featured_match.get("match_date_raw"))
            if context:
                lines.append(context)
        lines.extend(["", " ".join(hashtags)])
        return self._compact_blank_lines("\n".join(lines))

    def _viral_ranking_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        source_payload: dict[str, Any],
        fallback_text: str | None,
    ) -> str | None:
        ranking_rows = self._ranking_rows(source_payload)
        if not ranking_rows:
            return fallback_text
        hashtags = self.resolve_hashtags(competition_slug)
        selected_rows = ranking_rows[: min(MAX_VIRAL_RANKING_ROWS, len(ranking_rows))]
        for mention_limit in range(min(IDEAL_MENTION_LIMIT, self.settings.max_mentions_per_post), -1, -1):
            text = self._render_viral_ranking_summary(
                competition_slug=competition_slug,
                competition_name=competition_name,
                ranking_rows=selected_rows,
                mention_limit=mention_limit,
                hashtags=hashtags,
            )
            if len(text) <= self.max_characters:
                return text
        return fallback_text

    def _render_viral_ranking_summary(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        ranking_rows: list[tuple[str, str]],
        mention_limit: int,
        hashtags: list[str],
    ) -> str:
        mention_map = self._mention_map(
            [row["team"] for row in ranking_rows],
            competition_slug,
            limit=mention_limit,
            min_activity_rank=4,
        )
        lines = [f"🏆 {self._ranking_title(ranking_rows)}", ""]
        for index, row in enumerate(ranking_rows, start=1):
            team_label = self._render_team_label(row["team"], mention_map)
            value = row.get("value")
            if value is None:
                lines.append(f"{index}. {team_label}")
            else:
                lines.append(f"{index}. {team_label} — {value}")
        lines.extend(["", " ".join(hashtags)])
        return self._compact_blank_lines("\n".join(lines))

    def _prioritized_results_matches(
        self,
        matches: list[dict[str, Any]],
        competition_slug: str,
    ) -> list[dict[str, Any]]:
        scored: list[tuple[int, int, int, dict[str, Any]]] = []
        for index, match in enumerate(matches):
            home_rank, home_followers = self._team_social_priority(self._string(match.get("home_team")), competition_slug)
            away_rank, away_followers = self._team_social_priority(self._string(match.get("away_team")), competition_slug)
            scored.append((-(home_rank + away_rank), -(home_followers + away_followers), index, match))
        scored.sort()
        return [match for _, _, _, match in scored]

    def _team_social_priority(self, team_name: str | None, competition_slug: str) -> tuple[int, int]:
        if not team_name:
            return 0, 0
        social_info = self.identity_service.get_team_social_info(team_name, competition_slug=competition_slug)
        return (
            ACTIVITY_RANK.get(str(social_info.get("activity_level") or ""), 0),
            int(social_info.get("followers_approx") or 0),
        )

    def _mention_map(
        self,
        team_names: list[str],
        competition_slug: str,
        *,
        limit: int,
        min_activity_rank: int = 0,
    ) -> dict[str, str]:
        if limit <= 0:
            return {}
        rows: list[tuple[int, int, int, str, str]] = []
        for index, team_name in enumerate(team_names):
            social_info = self.identity_service.get_team_social_info(team_name, competition_slug=competition_slug)
            handle = self._string(social_info.get("x_handle"))
            if not handle:
                continue
            activity_rank = ACTIVITY_RANK.get(str(social_info.get("activity_level") or ""), 0)
            if activity_rank < min_activity_rank:
                continue
            followers = int(social_info.get("followers_approx") or 0)
            rows.append((index, -activity_rank, -followers, team_name, handle))
        rows.sort()
        selected: dict[str, str] = {}
        seen_handles: set[str] = set()
        for _, _, _, team_name, handle in rows:
            normalized_handle = handle.lower()
            if normalized_handle in seen_handles or team_name in selected:
                continue
            selected[team_name] = handle
            seen_handles.add(normalized_handle)
            if len(selected) >= limit:
                break
        return selected

    def _render_team_label(self, team_name: str, mention_map: dict[str, str]) -> str:
        handle = mention_map.get(team_name)
        if handle:
            return handle
        return team_name

    def _render_results_team_label(self, team_name: str, mention_map: dict[str, str]) -> str:
        return mention_map.get(team_name, team_name)

    def _normalize_alias_text(self, text: str) -> str:
        normalized_text = text
        for raw_name, editorial_name in load_team_name_aliases().items():
            normalized_text = normalized_text.replace(raw_name, editorial_name)
        return normalized_text

    def _normalize_match(self, value: Any) -> dict[str, Any] | Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for field in ("home_team", "away_team"):
            team_name = self._string(normalized.get(field))
            if team_name:
                normalized[field] = normalize_team_name(team_name)
        return normalized

    def _normalize_matches(self, value: Any) -> list[dict[str, Any]] | Any:
        if not isinstance(value, list):
            return value
        return [self._normalize_match(match) for match in value]

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

    def _ranking_rows(self, source_payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, title in {
            "best_attack": "Mejor ataque",
            "best_defense": "Mejor defensa",
            "most_wins": "Más victorias",
        }.items():
            value = source_payload.get(key)
            if not isinstance(value, dict):
                continue
            team_name = self._string(value.get("team"))
            if team_name:
                rows.append(
                    {
                        "key": key,
                        "title": title,
                        "team": team_name,
                        "value": value.get("value"),
                    }
                )
        return rows

    def _ranking_title(self, ranking_rows: list[dict[str, Any]]) -> str:
        if len(ranking_rows) == 1:
            return str(ranking_rows[0].get("title") or "Ranking")
        return "Ranking"

    def build_matchday_thread(
        self,
        *,
        competition_name: str,
        group_label: str | None,
        results_text: str | None,
        standings_text: str | None,
        narrative_text: str | None,
    ) -> list[MatchdayThreadPart]:
        parts: list[MatchdayThreadPart] = []
        header_lines = [competition_name]
        if group_label:
            header_lines.append(group_label)
        parts.append(MatchdayThreadPart(slot="header", text="\n".join(header_lines)))
        if results_text:
            parts.append(MatchdayThreadPart(slot="results", text=results_text))
        if standings_text:
            parts.append(MatchdayThreadPart(slot="standings", text=standings_text))
        if narrative_text:
            parts.append(MatchdayThreadPart(slot="narrative", text=narrative_text))
        return parts

    def _mentions(self) -> list[TeamMention]:
        if self._mentions_cache is None:
            self._mentions_cache = self.session.execute(select(TeamMention)).scalars().all()
        return self._mentions_cache

    def _competition_name(self, competition_slug: str) -> str:
        definition = self.catalog.get(competition_slug)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        return competition_slug

    def _group_label(self, raw_group_label: Any) -> str | None:
        if raw_group_label is None:
            return None
        value = str(raw_group_label).strip()
        return value or None

    def _preview_group_label(self, matches: list[dict[str, Any]]) -> str | None:
        round_names: list[str] = []
        for match in matches:
            round_name = match.get("round_name")
            if isinstance(round_name, str) and round_name.strip():
                round_names.append(round_name.strip())
        if round_names and len(set(round_names)) == 1:
            return round_names[0]
        return None

    def _primary_team(self, source_payload: dict[str, Any]) -> str | None:
        if isinstance(source_payload.get("team"), str) and source_payload.get("team").strip():
            return str(source_payload["team"]).strip()
        teams = source_payload.get("teams")
        if isinstance(teams, list):
            for team in teams:
                if isinstance(team, str) and team.strip():
                    return team.strip()
        return None

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
