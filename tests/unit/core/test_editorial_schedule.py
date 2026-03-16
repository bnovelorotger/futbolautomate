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
    assert monday_rules[0].content_type == EditorialPlanningContent.LATEST_RESULTS
    assert any(rule.competition_slug == "division_honor_mallorca" for rule in monday_rules)
    assert any(rule.content_type == EditorialPlanningContent.METRIC_NARRATIVE for rule in wednesday_rules)
    assert any(rule.content_type == EditorialPlanningContent.VIRAL_STORY for rule in wednesday_rules)
    assert len(sunday_rules) == 2
    assert {rule.competition_slug for rule in sunday_rules} == {
        "tercera_rfef_g11",
        "segunda_rfef_g3_baleares",
    }
