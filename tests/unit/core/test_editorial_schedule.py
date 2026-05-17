from __future__ import annotations

from app.core.editorial_schedule import load_editorial_schedule
from app.core.enums import EditorialPlanningContent


def test_default_editorial_schedule_loads_expected_rules() -> None:
    load_editorial_schedule.cache_clear()
    schedule = load_editorial_schedule()

    monday_rules = schedule.rules_for_weekday("monday")
    wednesday_rules = schedule.rules_for_weekday("wednesday")
    thursday_rules = schedule.rules_for_weekday("thursday")
    sunday_rules = schedule.rules_for_weekday("sunday")

    assert len(monday_rules) == 37
    assert monday_rules[0].competition_slug == "tercera_rfef_g11"
    assert monday_rules[0].content_type == EditorialPlanningContent.RESULTS_ROUNDUP
    assert any(rule.content_type == EditorialPlanningContent.STANDINGS_ROUNDUP for rule in monday_rules)
    assert any(rule.competition_slug == "division_honor_mallorca" for rule in monday_rules)
    assert any(rule.competition_slug == "primera_rfef_baleares" for rule in monday_rules)
    assert any(rule.competition_slug == "tercera_federacion_femenina_g11" for rule in monday_rules)
    assert any(rule.competition_slug == "division_honor_ibiza_form" for rule in monday_rules)
    assert any(rule.competition_slug == "division_honor_menorca" for rule in monday_rules)
    assert any(
        rule.competition_slug == "tercera_federacion_femenina_g11"
        and rule.content_type == EditorialPlanningContent.STANDINGS_ROUNDUP
        for rule in monday_rules
    )
    assert any(
        rule.competition_slug == "division_honor_ibiza_form"
        and rule.content_type == EditorialPlanningContent.STANDINGS_ROUNDUP
        for rule in monday_rules
    )
    assert any(
        rule.competition_slug == "division_honor_menorca"
        and rule.content_type == EditorialPlanningContent.STANDINGS_ROUNDUP
        for rule in monday_rules
    )
    assert any(rule.content_type == EditorialPlanningContent.METRIC_NARRATIVE for rule in wednesday_rules)
    assert any(rule.content_type == EditorialPlanningContent.VIRAL_STORY for rule in wednesday_rules)
    assert len(thursday_rules) == 0
    friday_rules = schedule.rules_for_weekday("friday")
    assert len(friday_rules) == 14
    assert any(rule.content_type == EditorialPlanningContent.FEATURED_MATCH_PREVIEW for rule in friday_rules)
    assert any(rule.content_type == EditorialPlanningContent.MATCH_IMPACT_SCENARIO for rule in friday_rules)
    friday_slugs = {rule.competition_slug for rule in friday_rules}
    assert {
        "tercera_rfef_g11",
        "segunda_rfef_g3_baleares",
        "division_honor_mallorca",
        "tercera_federacion_femenina_g11",
        "primera_rfef_baleares",
        "tercera_rfef_g11_playoff",
        "segunda_rfef_g3_playoff_ascenso",
        "primera_rfef_playoff_ascenso",
        "segunda_rfef_g3_playoff_permanencia",
    }.issubset(friday_slugs)
    assert {
        rule.content_type for rule in friday_rules
    } == {
        EditorialPlanningContent.FEATURED_MATCH_PREVIEW,
        EditorialPlanningContent.MATCH_IMPACT_SCENARIO,
    }
    assert len(sunday_rules) == 4
    assert {rule.competition_slug for rule in sunday_rules} == {
        "tercera_rfef_g11",
        "segunda_rfef_g3_baleares",
    }
    assert {
        rule.content_type for rule in sunday_rules
    } == {
        EditorialPlanningContent.RESULTS_ROUNDUP,
        EditorialPlanningContent.STANDINGS_ROUNDUP,
    }


def test_wednesday_schedule_includes_narrative_duo_for_three_main_competitions() -> None:
    load_editorial_schedule.cache_clear()
    schedule = load_editorial_schedule()
    wednesday_rules = schedule.rules_for_weekday("wednesday")
    wednesday_pairs = {
        (rule.competition_slug, rule.content_type)
        for rule in wednesday_rules
    }

    expected_pairs = {
        ("tercera_rfef_g11", EditorialPlanningContent.METRIC_NARRATIVE),
        ("tercera_rfef_g11", EditorialPlanningContent.VIRAL_STORY),
        ("segunda_rfef_g3_baleares", EditorialPlanningContent.METRIC_NARRATIVE),
        ("segunda_rfef_g3_baleares", EditorialPlanningContent.VIRAL_STORY),
        ("tercera_federacion_femenina_g11", EditorialPlanningContent.METRIC_NARRATIVE),
        ("tercera_federacion_femenina_g11", EditorialPlanningContent.VIRAL_STORY),
    }

    assert expected_pairs.issubset(wednesday_pairs)


def test_monday_schedule_includes_race_and_milestone_slots_for_main_competitions() -> None:
    load_editorial_schedule.cache_clear()
    schedule = load_editorial_schedule()
    monday_rules = schedule.rules_for_weekday("monday")
    monday_pairs = {
        (rule.competition_slug, rule.content_type)
        for rule in monday_rules
    }

    expected_pairs = {
        ("tercera_rfef_g11", EditorialPlanningContent.RACE_NARRATIVE),
        ("tercera_rfef_g11", EditorialPlanningContent.MILESTONE_STORY),
        ("tercera_rfef_g11", EditorialPlanningContent.TOP_SCORER_UPDATE),
        ("segunda_rfef_g3_baleares", EditorialPlanningContent.RACE_NARRATIVE),
        ("segunda_rfef_g3_baleares", EditorialPlanningContent.MILESTONE_STORY),
        ("segunda_rfef_g3_baleares", EditorialPlanningContent.TOP_SCORER_UPDATE),
        ("division_honor_mallorca", EditorialPlanningContent.RACE_NARRATIVE),
        ("division_honor_mallorca", EditorialPlanningContent.MILESTONE_STORY),
        ("division_honor_mallorca", EditorialPlanningContent.TOP_SCORER_UPDATE),
        ("tercera_federacion_femenina_g11", EditorialPlanningContent.RACE_NARRATIVE),
        ("tercera_federacion_femenina_g11", EditorialPlanningContent.MILESTONE_STORY),
        ("tercera_federacion_femenina_g11", EditorialPlanningContent.TOP_SCORER_UPDATE),
        ("primera_rfef_baleares", EditorialPlanningContent.RACE_NARRATIVE),
        ("primera_rfef_baleares", EditorialPlanningContent.MILESTONE_STORY),
        ("primera_rfef_baleares", EditorialPlanningContent.TOP_SCORER_UPDATE),
    }

    assert expected_pairs.issubset(monday_pairs)
