from __future__ import annotations

from app.core.editorial_schedule import load_editorial_schedule
from app.core.enums import EditorialPlanningContent


def test_default_editorial_schedule_loads_expected_rules() -> None:
    load_editorial_schedule.cache_clear()
    schedule = load_editorial_schedule()

    monday_rules = schedule.rules_for_weekday("monday")
    wednesday_rules = schedule.rules_for_weekday("wednesday")
    sunday_rules = schedule.rules_for_weekday("sunday")

    assert len(monday_rules) == 6
    assert monday_rules[0].competition_slug == "tercera_rfef_g11"
    assert monday_rules[0].content_type == EditorialPlanningContent.RESULTS_ROUNDUP
    assert any(rule.content_type == EditorialPlanningContent.STANDINGS_ROUNDUP for rule in monday_rules)
    assert any(rule.competition_slug == "division_honor_mallorca" for rule in monday_rules)
    assert any(rule.content_type == EditorialPlanningContent.METRIC_NARRATIVE for rule in wednesday_rules)
    assert any(rule.content_type == EditorialPlanningContent.VIRAL_STORY for rule in wednesday_rules)
    friday_rules = schedule.rules_for_weekday("friday")
    assert any(rule.content_type == EditorialPlanningContent.FEATURED_MATCH_PREVIEW for rule in friday_rules)
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
