from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.enums import ContentType
from app.db.models import ContentCandidate, TeamMention
from app.normalizers.text import normalize_token
from app.schemas.editorial_content import ContentCandidateDraft

MAX_FORMATTED_CHARACTERS = 240
MAX_RESULTS_MATCHES = 8
MAX_PREVIEW_MATCHES = 2
NUMBER_EMOJIS = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
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


class EditorialFormatterService:
    def __init__(
        self,
        session: Session,
        *,
        max_characters: int = MAX_FORMATTED_CHARACTERS,
    ) -> None:
        self.session = session
        self.max_characters = max_characters
        self.catalog = load_competition_catalog()
        self._mentions_cache: list[TeamMention] | None = None

    def apply_to_drafts(self, candidates: list[ContentCandidateDraft]) -> list[ContentCandidateDraft]:
        return [self.apply_to_draft(candidate) for candidate in candidates]

    def apply_to_draft(self, candidate: ContentCandidateDraft) -> ContentCandidateDraft:
        return candidate.model_copy(update={"formatted_text": self.format_draft(candidate)})

    def format_draft(self, candidate: ContentCandidateDraft) -> str | None:
        return self._format_content(
            competition_slug=candidate.competition_slug,
            content_type=ContentType(candidate.content_type),
            text_draft=candidate.text_draft,
            payload_json=candidate.payload_json,
        )

    def format_candidate(self, candidate: ContentCandidate) -> str | None:
        return self._format_content(
            competition_slug=candidate.competition_slug,
            content_type=ContentType(candidate.content_type),
            text_draft=candidate.text_draft,
            payload_json=candidate.payload_json or {},
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
        normalized_target = normalize_token(team_name)
        normalized_identity = normalize_team_identity_value(team_name)
        for row in self._mentions():
            if row.competition_slug not in {competition_slug, None}:
                continue
            row_normalized = normalize_token(row.team_name)
            row_identity = normalize_team_identity_value(row.team_name)
            if row.twitter_handle.strip() and (
                row_normalized == normalized_target or row_identity == normalized_identity
            ):
                handle = row.twitter_handle.strip()
                if not handle.startswith("@"):
                    handle = f"@{handle}"
                return f" {handle}"
        return ""

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

    def normalize_team_identity(self, team_name: str) -> str:
        return normalize_team_identity_value(team_name)
