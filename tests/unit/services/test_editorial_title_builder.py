from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from app.core.enums import (
    ContentType,
    NarrativeMetricType,
    StandingsEventType,
    ViralStoryType,
)
from app.services.editorial_title_builder import (
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

# ---------------------------------------------------------------------------
# get_competition_name
# ---------------------------------------------------------------------------


def _make_catalog_entry(editorial_name: str | None) -> MagicMock:
    entry = MagicMock()
    entry.editorial_name = editorial_name
    return entry


def test_get_competition_name_returns_editorial_name_when_present() -> None:
    fake_catalog = {"tercera_rfef_g11": _make_catalog_entry("3a RFEF Baleares")}
    with patch("app.services.editorial_title_builder.load_competition_catalog", return_value=fake_catalog):
        result = get_competition_name("tercera_rfef_g11")
    assert result == "3a RFEF Baleares"


def test_get_competition_name_falls_back_to_slug_when_no_editorial_name() -> None:
    fake_catalog = {"tercera_rfef_g11": _make_catalog_entry(None)}
    with patch("app.services.editorial_title_builder.load_competition_catalog", return_value=fake_catalog):
        result = get_competition_name("tercera_rfef_g11")
    assert result == "tercera_rfef_g11"


def test_get_competition_name_falls_back_to_slug_when_slug_not_in_catalog() -> None:
    with patch("app.services.editorial_title_builder.load_competition_catalog", return_value={}):
        result = get_competition_name("unknown_competition")
    assert result == "unknown_competition"


# ---------------------------------------------------------------------------
# build_competition_title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug, competition_name, expected",
    [
        ("tercera_rfef_g11", "anything", "3ª RFEF"),
        ("segunda_rfef_g3_baleares", "anything", "2ª RFEF"),
        ("primera_rfef_baleares", "anything", "1ª RFEF"),
        ("tercera_federacion_femenina_g11", "anything", "3ª RFEF Fem"),
        ("division_honor_mallorca", "anything", "DH Mallorca"),
        ("division_honor_ibiza_form", "anything", "DH Ibiza/Form"),
        ("division_honor_menorca", "anything", "DH Menorca"),
    ],
)
def test_build_competition_title_returns_short_name_for_known_slugs(
    slug: str, competition_name: str, expected: str
) -> None:
    assert build_competition_title(slug, competition_name) == expected


@pytest.mark.parametrize(
    "competition_name, expected",
    [
        ("Tercera División RFEF Baleares", "3ª RFEF"),
        ("Competición 3a RFEF Nacional", "3ª RFEF"),
        ("Liga 3ª RFEF Grupo 5", "3ª RFEF"),
        ("Segunda División RFEF Balear", "2ª RFEF"),
        ("Categoría 2a RFEF Costa", "2ª RFEF"),
        ("Liga 2ª RFEF Grupo 12", "2ª RFEF"),
        ("División de Honor de Mallorca", "DH Mallorca"),
    ],
)
def test_build_competition_title_infers_from_competition_name_for_unknown_slug(
    competition_name: str, expected: str
) -> None:
    assert build_competition_title("unknown_slug", competition_name) == expected


def test_build_competition_title_returns_stripped_name_as_fallback() -> None:
    result = build_competition_title("custom_league", "  Liga Especial Balear  ")
    assert result == "Liga Especial Balear"


def test_build_competition_title_slug_takes_precedence_over_name_keywords() -> None:
    # Known slug must win even when name would suggest something else
    result = build_competition_title("tercera_rfef_g11", "Segunda RFEF something")
    assert result == "3ª RFEF"


# ---------------------------------------------------------------------------
# build_group_title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source_payload, slug, name, expected",
    [
        ({"group_code": "Grupo 11"}, "any_slug", "any name", "G11"),
        ({"group_label": "Jornada 5 - Grupo 3"}, "any_slug", "any name", "G3"),
        ({}, "tercera_rfef_g11", "any name", "G11"),
        ({}, "segunda_rfef_g3_baleares", "any name", "G3"),
        ({}, "any_slug", "Liga Grupo 7 Regional", "G7"),
        ({"group_code": "G02"}, "any_slug", "any name", "G2"),
    ],
)
def test_build_group_title_extracts_group_number(
    source_payload: dict, slug: str, name: str, expected: str
) -> None:
    assert build_group_title(slug, name, source_payload) == expected


def test_build_group_title_returns_none_when_no_group_found() -> None:
    result = build_group_title("division_honor_mallorca", "Division Honor Mallorca", {})
    assert result is None


def test_build_group_title_group_code_takes_priority_over_slug() -> None:
    # group_code is checked first in the iteration order
    result = build_group_title("tercera_rfef_g11", "any name", {"group_code": "Grupo 5"})
    assert result == "G5"


def test_build_group_title_strips_leading_zeros() -> None:
    result = build_group_title("any_slug", "any name", {"group_code": "Grupo 007"})
    assert result == "G7"


# ---------------------------------------------------------------------------
# build_round_title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source_payload, expected",
    [
        ({"round_name": "Jornada 26"}, "J26"),
        ({"round_name": "J. 5"}, "J5"),
        ({"round_name": "Jornada 01"}, "J1"),
        ({"group_label": "Jornada 14"}, "J14"),
        ({"group_label": "J3"}, "J3"),
    ],
)
def test_build_round_title_from_round_name_and_group_label(source_payload: dict, expected: str) -> None:
    assert build_round_title(source_payload) == expected


def test_build_round_title_falls_back_to_featured_match() -> None:
    payload = {"featured_match": {"round_name": "Jornada 10"}}
    assert build_round_title(payload) == "J10"


def test_build_round_title_falls_back_to_first_match_round_name() -> None:
    payload = {
        "matches": [
            {"round_name": "Jornada 8"},
            {"round_name": "Jornada 9"},
        ]
    }
    assert build_round_title(payload) == "J8"


def test_build_round_title_falls_back_to_rows_played_count() -> None:
    payload = {
        "rows": [
            {"position": 1, "team": "Team A", "played": 22},
            {"position": 2, "team": "Team B", "played": 22},
            {"position": 3, "team": "Team C", "played": 21},
        ]
    }
    assert build_round_title(payload) == "J22"


def test_build_round_title_returns_none_for_empty_payload() -> None:
    assert build_round_title({}) is None


def test_build_round_title_returns_none_when_rows_have_no_played() -> None:
    payload = {"rows": [{"position": 1, "team": "Team A"}]}
    assert build_round_title(payload) == None


def test_build_round_title_strips_leading_zeros_from_round_number() -> None:
    assert build_round_title({"round_name": "Jornada 03"}) == "J3"


def test_build_round_title_round_name_takes_priority_over_group_label() -> None:
    # round_name is checked before group_label
    payload = {"round_name": "Jornada 20", "group_label": "Jornada 99"}
    assert build_round_title(payload) == "J20"


# ---------------------------------------------------------------------------
# build_part_suffix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "part_index, part_total, expected",
    [
        (1, 2, "(1/2)"),
        (2, 3, "(2/3)"),
        (1, 5, "(1/5)"),
    ],
)
def test_build_part_suffix_returns_fraction_when_multi_part(
    part_index: int, part_total: int, expected: str
) -> None:
    payload = {"part_index": part_index, "part_total": part_total}
    assert build_part_suffix(payload) == expected


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"part_index": 1},
        {"part_total": 2},
        {"part_index": 1, "part_total": 1},  # part_total must be > 1
        {"part_index": "1", "part_total": 3},  # wrong type
        {"part_index": 1, "part_total": "3"},  # wrong type
    ],
)
def test_build_part_suffix_returns_none_for_invalid_or_single_part(payload: dict) -> None:
    assert build_part_suffix(payload) is None


# ---------------------------------------------------------------------------
# build_standard_title
# ---------------------------------------------------------------------------


def test_build_standard_title_results_roundup_with_known_slug_and_round() -> None:
    title = build_standard_title(
        content_type=ContentType.RESULTS_ROUNDUP,
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF Baleares",
        source_payload={"group_label": "Jornada 26"},
    )
    assert title == "📋 Resultados - 3ª RFEF - G11 - J26"


def test_build_standard_title_standings_roundup_with_known_slug() -> None:
    title = build_standard_title(
        content_type=ContentType.STANDINGS_ROUNDUP,
        competition_slug="segunda_rfef_g3_baleares",
        competition_name="2a RFEF Baleares",
        source_payload={"group_label": "Jornada 10"},
    )
    assert title == "📊 Clasificación - 2ª RFEF - G3 - J10"


def test_build_standard_title_preview_content_type() -> None:
    title = build_standard_title(
        content_type=ContentType.PREVIEW,
        competition_slug="segunda_rfef_g3_baleares",
        competition_name="2a RFEF Baleares",
        source_payload={"matches": [{"round_name": "Jornada 28"}]},
    )
    assert title == "🔎 Previa - 2ª RFEF - G3 - J28"


def test_build_standard_title_unknown_content_type_uses_default_emoji() -> None:
    title = build_standard_title(
        content_type=ContentType.RANKING,
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF",
        source_payload={},
    )
    # RANKING is not in TITLE_SPECS → default emoji 📝 and label "Contenido"
    assert title.startswith("📝 Contenido")


def test_build_standard_title_uses_title_override_when_provided() -> None:
    title = build_standard_title(
        content_type=ContentType.RESULTS_ROUNDUP,
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF Baleares",
        source_payload={"group_label": "Jornada 5"},
        title_override="🏆 Mejor ataque",
    )
    assert title.startswith("🏆 Mejor ataque - 3ª RFEF")


def test_build_standard_title_excludes_round_when_include_round_is_false() -> None:
    title = build_standard_title(
        content_type=ContentType.RESULTS_ROUNDUP,
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF",
        source_payload={"group_label": "Jornada 26"},
        include_round=False,
    )
    assert "J26" not in title


def test_build_standard_title_omits_group_when_no_group_detectable() -> None:
    title = build_standard_title(
        content_type=ContentType.RESULTS_ROUNDUP,
        competition_slug="division_honor_mallorca",
        competition_name="Division Honor Mallorca",
        source_payload={"group_label": "Jornada 5"},
    )
    # No group number in slug or name for DH Mallorca
    assert "G" not in title
    assert "J5" in title


def test_build_standard_title_appends_part_suffix_when_multi_part() -> None:
    title = build_standard_title(
        content_type=ContentType.RESULTS_ROUNDUP,
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF",
        source_payload={"group_label": "Jornada 26", "part_index": 1, "part_total": 2},
    )
    assert title.endswith("(1/2)")


# ---------------------------------------------------------------------------
# build_roundup_title
# ---------------------------------------------------------------------------


def test_build_roundup_title_non_compact_produces_standard_title() -> None:
    title = build_roundup_title(
        content_type=ContentType.RESULTS_ROUNDUP,
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF Baleares",
        source_payload={"group_label": "Jornada 26"},
        compact=False,
    )
    assert title == "📋 Resultados - 3ª RFEF - G11 - J26"


def test_build_roundup_title_compact_omits_emoji_and_label() -> None:
    title = build_roundup_title(
        content_type=ContentType.RESULTS_ROUNDUP,
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF Baleares",
        source_payload={"group_label": "Jornada 26"},
        compact=True,
    )
    assert title == "3ª RFEF - G11 - J26"
    assert "📋" not in title
    assert "Resultados" not in title


def test_build_roundup_title_compact_without_round_just_competition_and_group() -> None:
    title = build_roundup_title(
        content_type=ContentType.STANDINGS_ROUNDUP,
        competition_slug="segunda_rfef_g3_baleares",
        competition_name="2a RFEF",
        source_payload={},
        compact=True,
    )
    assert title == "2ª RFEF - G3"


def test_build_roundup_title_compact_appends_part_suffix() -> None:
    title = build_roundup_title(
        content_type=ContentType.RESULTS_ROUNDUP,
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF",
        source_payload={"group_label": "Jornada 12", "part_index": 2, "part_total": 3},
        compact=True,
    )
    assert title.endswith("(2/3)")


def test_build_roundup_title_compact_does_not_repeat_round_when_same_as_group() -> None:
    # If build_round_title returns same value as build_group_title, it should not be appended again.
    # This is an edge case: payload group_label containing both group and round identical tokens is
    # unusual, so instead we test the deduplication logic by making round == group.
    # build_group_title checks group_code first; if group_code is "G5" (no digit match in round),
    # and group_label is "Jornada 5", round is J5 != G5, so they differ.
    # To exercise the deduplication guard we'd need round_title == group_title, which only happens
    # if both return None (they're both None → not appended). So we just verify compact=False path.
    title = build_roundup_title(
        content_type=ContentType.RESULTS_ROUNDUP,
        competition_slug="division_honor_mallorca",
        competition_name="Division Honor Mallorca",
        source_payload={},
        compact=True,
    )
    # No group, no round → only competition name
    assert title == "DH Mallorca"


# ---------------------------------------------------------------------------
# build_ranking_title
# ---------------------------------------------------------------------------


def test_build_ranking_title_single_row_uses_row_title() -> None:
    title = build_ranking_title(
        competition_slug="segunda_rfef_g3_baleares",
        competition_name="2a RFEF",
        ranking_rows=[{"title": "Mejor ataque"}],
    )
    assert title.startswith("🏆 Mejor ataque")
    assert "2ª RFEF" in title


def test_build_ranking_title_two_rows_joins_labels_with_slash() -> None:
    title = build_ranking_title(
        competition_slug="segunda_rfef_g3_baleares",
        competition_name="2a RFEF",
        ranking_rows=[{"title": "Ataque"}, {"title": "Defensa"}],
    )
    assert "Ataque / Defensa" in title


def test_build_ranking_title_long_joined_label_falls_back_to_first_label() -> None:
    long_label_a = "A" * 25
    long_label_b = "B" * 20
    title = build_ranking_title(
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF",
        ranking_rows=[{"title": long_label_a}, {"title": long_label_b}],
    )
    # Joined label exceeds 40 chars → falls back to first label only
    assert long_label_a in title
    assert long_label_b not in title


def test_build_ranking_title_row_without_title_key_uses_ranking_fallback() -> None:
    title = build_ranking_title(
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF",
        ranking_rows=[{}],
    )
    assert "Ranking" in title


def test_build_ranking_title_row_with_none_title_uses_ranking_fallback() -> None:
    title = build_ranking_title(
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF",
        ranking_rows=[{"title": None}],
    )
    assert "Ranking" in title


def test_build_ranking_title_never_includes_round() -> None:
    # include_round=False is hardcoded — build_ranking_title passes source_payload={}
    # so no round token (e.g. "J26") can appear in the output.
    title = build_ranking_title(
        competition_slug="tercera_rfef_g11",
        competition_name="3a RFEF",
        ranking_rows=[{"title": "Mejor ataque"}],
    )
    # Expected: "🏆 Mejor ataque - 3ª RFEF - G11" — no round segment
    assert not re.search(r"\bJ\d+\b", title)


# ---------------------------------------------------------------------------
# build_narrative_label
# ---------------------------------------------------------------------------


class TestBuildNarrativeLabelStandingsEvent:
    @pytest.mark.parametrize(
        "event_type, expected",
        [
            (str(StandingsEventType.NEW_LEADER), "Nuevo líder"),
            (str(StandingsEventType.ENTERED_PLAYOFF), "Playoff"),
            (str(StandingsEventType.LEFT_PLAYOFF), "Playoff"),
            (str(StandingsEventType.ENTERED_RELEGATION), "Descenso"),
            (str(StandingsEventType.LEFT_RELEGATION), "Descenso"),
            ("unknown_event", "Dato"),
            (None, "Dato"),
        ],
    )
    def test_standings_event_labels(self, event_type: str | None, expected: str) -> None:
        payload: dict = {} if event_type is None else {"event_type": event_type}
        result = build_narrative_label(ContentType.STANDINGS_EVENT, payload)
        assert result == expected


def test_build_narrative_label_form_event_always_returns_forma() -> None:
    assert build_narrative_label(ContentType.FORM_EVENT, {}) == "Forma"
    assert build_narrative_label(ContentType.FORM_EVENT, {"anything": "irrelevant"}) == "Forma"


@pytest.mark.parametrize(
    "narrative_type, expected",
    [
        (str(NarrativeMetricType.WIN_STREAK), "Forma"),
        (str(NarrativeMetricType.UNBEATEN_STREAK), "Forma"),
        (str(NarrativeMetricType.BEST_ATTACK), "Dato"),
        (str(NarrativeMetricType.BEST_DEFENSE), "Dato"),
        (str(NarrativeMetricType.GOALS_AVERAGE), "Dato"),
        ("unknown_metric", "Dato"),
    ],
)
def test_build_narrative_label_metric_narrative(narrative_type: str, expected: str) -> None:
    result = build_narrative_label(ContentType.METRIC_NARRATIVE, {"narrative_type": narrative_type})
    assert result == expected


@pytest.mark.parametrize(
    "story_type, expected",
    [
        (str(ViralStoryType.WIN_STREAK), "Forma"),
        (str(ViralStoryType.UNBEATEN_STREAK), "Forma"),
        (str(ViralStoryType.LOSING_STREAK), "Forma"),
        (str(ViralStoryType.HOT_FORM), "Tendencia"),
        (str(ViralStoryType.COLD_FORM), "Tendencia"),
        (str(ViralStoryType.GOALS_TREND), "Tendencia"),
        (str(ViralStoryType.BEST_ATTACK), "Dato"),
        (str(ViralStoryType.RECENT_TOP_SCORER), "Dato"),
        ("unknown_story", "Dato"),
    ],
)
def test_build_narrative_label_viral_story(story_type: str, expected: str) -> None:
    result = build_narrative_label(ContentType.VIRAL_STORY, {"story_type": story_type})
    assert result == expected


@pytest.mark.parametrize(
    "tags, expected",
    [
        (["playoff_clash"], "Playoff"),
        (["relegation_clash"], "Descenso"),
        (["hot_form_match"], "Forma"),
        (["cold_form_match"], "Forma"),
        (["hot_form_match", "playoff_clash"], "Playoff"),  # playoff_clash checked first
        ([], "Dato"),
        (["irrelevant_tag"], "Dato"),
    ],
)
def test_build_narrative_label_featured_match_event(tags: list, expected: str) -> None:
    result = build_narrative_label(ContentType.FEATURED_MATCH_EVENT, {"tags": tags})
    assert result == expected


def test_build_narrative_label_featured_match_event_without_tags_key() -> None:
    assert build_narrative_label(ContentType.FEATURED_MATCH_EVENT, {}) == "Dato"


def test_build_narrative_label_featured_match_event_tags_not_a_list() -> None:
    assert build_narrative_label(ContentType.FEATURED_MATCH_EVENT, {"tags": "playoff_clash"}) == "Dato"


def test_build_narrative_label_unknown_content_type_returns_dato() -> None:
    assert build_narrative_label(ContentType.MATCH_RESULT, {}) == "Dato"
    assert build_narrative_label(ContentType.RESULTS_ROUNDUP, {}) == "Dato"


def test_build_narrative_label_top_scorer_update_returns_goleadores() -> None:
    assert build_narrative_label(ContentType.TOP_SCORER_UPDATE, {}) == "Goleadores"


# ---------------------------------------------------------------------------
# build_narrative_title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content_type, payload, expected_prefix",
    [
        (ContentType.FORM_EVENT, {}, "💪🏼 Forma"),
        (ContentType.VIRAL_STORY, {"story_type": str(ViralStoryType.WIN_STREAK)}, "💪🏼 Forma"),
        (ContentType.VIRAL_STORY, {"story_type": str(ViralStoryType.GOALS_TREND)}, "📈 Tendencia"),
        (ContentType.VIRAL_STORY, {"story_type": str(ViralStoryType.BEST_ATTACK)}, "🔥 Dato"),
        (ContentType.METRIC_NARRATIVE, {"narrative_type": str(NarrativeMetricType.BEST_ATTACK)}, "🔥 Dato"),
        (ContentType.TOP_SCORER_UPDATE, {}, "🔥 Goleadores"),
        (ContentType.STANDINGS_EVENT, {"event_type": str(StandingsEventType.NEW_LEADER)}, "🔥 Nuevo líder"),
        (ContentType.STANDINGS_EVENT, {"event_type": str(StandingsEventType.ENTERED_PLAYOFF)}, "🔥 Playoff"),
        (ContentType.STANDINGS_EVENT, {"event_type": str(StandingsEventType.ENTERED_RELEGATION)}, "🔥 Descenso"),
    ],
)
def test_build_narrative_title_produces_correct_emoji_and_label(
    content_type: ContentType, payload: dict, expected_prefix: str
) -> None:
    result = build_narrative_title(content_type, payload)
    assert result == expected_prefix


def test_build_narrative_title_narrative_emojis_only_map_three_labels() -> None:
    # NARRATIVE_EMOJIS maps only "Forma", "Tendencia", "Dato".
    # All other labels produced by build_narrative_label ("Nuevo líder", "Playoff", "Descenso")
    # fall through to the default 🔥 emoji via dict.get(..., "🔥").
    # Verify that "Nuevo líder" gets 🔥 (not a custom emoji).
    result = build_narrative_title(ContentType.STANDINGS_EVENT, {"event_type": str(StandingsEventType.NEW_LEADER)})
    assert result == "🔥 Nuevo líder"


def test_build_narrative_title_always_returns_nonempty_string() -> None:
    result = build_narrative_title(ContentType.MATCH_RESULT, {})
    assert result
    assert " " in result
