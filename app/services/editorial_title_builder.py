from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.core.catalog import load_competition_catalog
from app.core.enums import ContentType, NarrativeMetricType, StandingsEventType, ViralStoryType

GROUP_PATTERN = re.compile(r"(?:^|[\s_-])g(?:rupo)?\s*0*(\d+)(?:$|[\s_-])", re.IGNORECASE)
ROUND_PATTERN = re.compile(r"(?:j(?:ornada)?\.?\s*)0*(\d+)", re.IGNORECASE)

COMPETITION_SHORT_NAMES = {
    "tercera_rfef_g11": "3ª RFEF",
    "segunda_rfef_g3_baleares": "2ª RFEF",
    "primera_rfef_baleares": "1ª RFEF",
    "tercera_federacion_femenina_g11": "3ª RFEF Fem",
    "division_honor_mallorca": "DH Mallorca",
    "division_honor_ibiza_form": "DH Ibiza/Form",
    "division_honor_menorca": "DH Menorca",
}
COMPETITION_HASHTAGS = {
    "tercera_rfef_g11": "#3aRFEF",
    "segunda_rfef_g3_baleares": "#2aRFEF",
    "primera_rfef_baleares": "#1aRFEF",
    "tercera_federacion_femenina_g11": "#FutFemBalear",
    "division_honor_mallorca": "#DH",
    "division_honor_ibiza_form": "#DHIbiza",
    "division_honor_menorca": "#DHMenorca",
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


def _string(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def get_competition_name(competition_slug: str) -> str:
    catalog = load_competition_catalog()
    definition = catalog.get(competition_slug)
    if definition is not None and definition.editorial_name:
        return definition.editorial_name
    return competition_slug


def build_competition_title(competition_slug: str, competition_name: str) -> str:
    if competition_slug in COMPETITION_SHORT_NAMES:
        return COMPETITION_SHORT_NAMES[competition_slug]
    lowered_name = _fold_text(competition_name)
    if "tercera" in lowered_name or "3a rfef" in lowered_name or "3ª rfef" in lowered_name:
        return "3ª RFEF"
    if "segunda" in lowered_name or "2a rfef" in lowered_name or "2ª rfef" in lowered_name:
        return "2ª RFEF"
    if "division" in lowered_name and "honor" in lowered_name:
        return "DH Mallorca"
    return competition_name.strip()


def build_group_title(competition_slug: str, competition_name: str, source_payload: dict[str, Any]) -> str | None:
    for raw_value in (
        source_payload.get("group_code"),
        source_payload.get("group_label"),
        competition_slug.replace("_", " "),
        competition_name,
    ):
        value = _string(raw_value)
        if not value:
            continue
        match = GROUP_PATTERN.search(f" {value} ")
        if match:
            return f"G{int(match.group(1))}"
    return None


def _round_from_value(value: Any) -> str | None:
    raw_value = _string(value)
    if not raw_value:
        return None
    match = ROUND_PATTERN.search(raw_value)
    if match:
        return f"J{int(match.group(1))}"
    return f"J{int(raw_value)}" if raw_value.isdigit() else None


def build_round_title(source_payload: dict[str, Any]) -> str | None:
    for raw_value in (source_payload.get("round_name"), source_payload.get("group_label")):
        round_label = _round_from_value(raw_value)
        if round_label:
            return round_label
    featured_match = source_payload.get("featured_match")
    if isinstance(featured_match, dict):
        round_label = _round_from_value(featured_match.get("round_name"))
        if round_label:
            return round_label
    matches = source_payload.get("matches")
    if isinstance(matches, list):
        for match in matches:
            if isinstance(match, dict):
                round_label = _round_from_value(match.get("round_name"))
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


def build_part_suffix(source_payload: dict[str, Any]) -> str | None:
    part_index = source_payload.get("part_index")
    part_total = source_payload.get("part_total")
    if isinstance(part_index, int) and isinstance(part_total, int) and part_total > 1:
        return f"({part_index}/{part_total})"
    return None


def build_standard_title(
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
    parts = [title_override, build_competition_title(competition_slug, competition_name)]
    group_title = build_group_title(competition_slug, competition_name, source_payload)
    if group_title:
        parts.append(group_title)
    if include_round:
        round_title = build_round_title(source_payload)
        if round_title:
            parts.append(round_title)
    title = " - ".join(parts)
    part_suffix = build_part_suffix(source_payload)
    if part_suffix:
        title = f"{title} {part_suffix}"
    return title


def build_roundup_title(
    *,
    content_type: ContentType,
    competition_slug: str,
    competition_name: str,
    source_payload: dict[str, Any],
    compact: bool,
) -> str:
    if not compact:
        return build_standard_title(
            content_type=content_type,
            competition_slug=competition_slug,
            competition_name=competition_name,
            source_payload=source_payload,
        )
    parts = [build_competition_title(competition_slug, competition_name)]
    group_title = build_group_title(competition_slug, competition_name, source_payload)
    if group_title:
        parts.append(group_title)
    round_title = build_round_title(source_payload)
    if round_title and round_title != group_title:
        parts.append(round_title)
    title = " - ".join(parts)
    part_suffix = build_part_suffix(source_payload)
    if part_suffix:
        title = f"{title} {part_suffix}"
    return title


def build_ranking_title(
    *,
    competition_slug: str,
    competition_name: str,
    ranking_rows: list[dict[str, Any]],
) -> str:
    labels = [str(row.get("title") or "Ranking") for row in ranking_rows]
    title_label = labels[0] if len(labels) == 1 else " / ".join(labels)
    if len(title_label) > 40:
        title_label = labels[0]
    return build_standard_title(
        content_type=ContentType.RANKING,
        competition_slug=competition_slug,
        competition_name=competition_name,
        source_payload={},
        title_override=f"🏆 {title_label}",
        include_round=False,
    )


def build_narrative_label(content_type: ContentType, source_payload: dict[str, Any]) -> str:
    if content_type == ContentType.STANDINGS_EVENT:
        event_type = _string(source_payload.get("event_type"))
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
        narrative_type = _string(source_payload.get("narrative_type"))
        if narrative_type in {str(NarrativeMetricType.WIN_STREAK), str(NarrativeMetricType.UNBEATEN_STREAK)}:
            return "Forma"
        return "Dato"
    if content_type == ContentType.VIRAL_STORY:
        story_type = _string(source_payload.get("story_type"))
        if story_type in {
            str(ViralStoryType.WIN_STREAK),
            str(ViralStoryType.UNBEATEN_STREAK),
            str(ViralStoryType.LOSING_STREAK),
        }:
            return "Forma"
        if story_type in {str(ViralStoryType.HOT_FORM), str(ViralStoryType.COLD_FORM), str(ViralStoryType.GOALS_TREND)}:
            return "Tendencia"
        return "Dato"
    if content_type == ContentType.TOP_SCORER_UPDATE:
        return "Goleadores"
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


def build_narrative_title(content_type: ContentType, source_payload: dict[str, Any]) -> str:
    label = build_narrative_label(content_type, source_payload)
    emoji = NARRATIVE_EMOJIS.get(label, "🔥")
    return f"{emoji} {label}"
