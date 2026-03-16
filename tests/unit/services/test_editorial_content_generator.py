from __future__ import annotations

from datetime import date, datetime, time, timezone

from app.core.enums import ContentType
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.editorial_summary import (
    CompetitionEditorialSummary,
    EditorialAggregateMetrics,
    EditorialCalendarWindows,
    EditorialCompetitionState,
    EditorialRankings,
    EditorialSummaryMetadata,
)
from app.schemas.reporting import CompetitionMatchView, StandingView, TeamRankingView
from app.services.editorial_content_generator import EditorialContentGenerator


def build_summary() -> CompetitionEditorialSummary:
    return CompetitionEditorialSummary(
        metadata=EditorialSummaryMetadata(
            competition_slug="tercera_rfef_g11",
            competition_name="3a RFEF Grupo 11",
            reference_date=date(2026, 3, 14),
            generated_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
        ),
        competition_state=EditorialCompetitionState(
            total_teams=18,
            total_matches=306,
            played_matches=223,
            pending_matches=83,
        ),
        latest_results=[
            CompetitionMatchView(
                round_name="Jornada 25",
                match_date=date(2026, 3, 7),
                match_date_raw="sabado, 07 de marzo de 2026",
                match_time=time(17, 0),
                match_time_raw="17:00",
                kickoff_datetime=datetime(2026, 3, 7, 17, 0, tzinfo=timezone.utc),
                home_team="CD Llosetense",
                away_team="SD Portmany",
                home_score=3,
                away_score=0,
                status="finished",
                source_url="https://example.com/result-1",
            ),
            CompetitionMatchView(
                round_name="Jornada 25",
                match_date=date(2026, 3, 7),
                match_date_raw="sabado, 07 de marzo de 2026",
                match_time=time(18, 0),
                match_time_raw="18:00",
                kickoff_datetime=datetime(2026, 3, 7, 18, 0, tzinfo=timezone.utc),
                home_team="CD Cardassar",
                away_team="SCR Pena Deportiva",
                home_score=0,
                away_score=2,
                status="finished",
                source_url="https://example.com/result-2",
            ),
        ],
        upcoming_matches=[
            CompetitionMatchView(
                round_name="Jornada 26",
                match_date=date(2026, 3, 14),
                match_date_raw="sabado, 14 de marzo de 2026",
                match_time=time(12, 0),
                match_time_raw="12:00",
                kickoff_datetime=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                home_team="RCD Mallorca B",
                away_team="CE Santanyi",
                status="scheduled",
                source_url="https://example.com/upcoming-1",
            ),
            CompetitionMatchView(
                round_name="Jornada 26",
                match_date=date(2026, 3, 14),
                match_date_raw="sabado, 14 de marzo de 2026",
                match_time=time(16, 30),
                match_time_raw="16:30",
                kickoff_datetime=datetime(2026, 3, 14, 16, 30, tzinfo=timezone.utc),
                home_team="CE Mercadal",
                away_team="CD Manacor",
                status="scheduled",
                source_url="https://example.com/upcoming-2",
            ),
        ],
        current_standings=[
            StandingView(position=1, team="RCD Mallorca B", points=63, played=25, goals_for=73, goals_against=16, goal_difference=57),
            StandingView(position=2, team="CD Manacor", points=61, played=25, goals_for=55, goals_against=27, goal_difference=28),
            StandingView(position=3, team="SCR Pena Deportiva", points=56, played=25, goals_for=50, goals_against=19, goal_difference=31),
        ],
        rankings=EditorialRankings(
            best_attack=TeamRankingView(team="RCD Mallorca B", value=73, position=1),
            best_defense=TeamRankingView(team="RCD Mallorca B", value=16, position=1),
            most_wins=TeamRankingView(team="RCD Mallorca B", value=20, position=1),
        ),
        calendar_windows=EditorialCalendarWindows(today=[], tomorrow=[], next_weekend=[]),
        editorial_news=[],
        aggregate_metrics=EditorialAggregateMetrics(
            total_goals_scored=637,
            average_goals_per_played_match=2.95,
            relevant_news_count=3,
        ),
    )


def test_editorial_content_generator_creates_expected_draft_types() -> None:
    generator = EditorialContentGenerator.__new__(EditorialContentGenerator)
    summary = build_summary()

    drafts = EditorialContentGenerator.generate_from_summary(generator, summary)

    assert len(drafts) == 6
    assert [draft.content_type for draft in drafts[:2]] == [
        ContentType.MATCH_RESULT,
        ContentType.MATCH_RESULT,
    ]
    assert {draft.content_type for draft in drafts} == {
        ContentType.MATCH_RESULT,
        ContentType.STANDINGS,
        ContentType.PREVIEW,
        ContentType.RANKING,
        ContentType.STAT_NARRATIVE,
    }
    assert drafts[0].text_draft.startswith("RESULTADO FINAL")
    assert "CD Llosetense 3-0 SD Portmany" in drafts[0].text_draft
    assert any(draft.text_draft.startswith("CLASIFICACION") for draft in drafts)
    assert any("PREVIA DE LA JORNADA" in draft.text_draft for draft in drafts)
    assert any("NARRATIVA ESTADISTICA" in draft.text_draft for draft in drafts)


def test_editorial_content_generator_hashes_source_payload_not_template_text() -> None:
    generator = EditorialContentGenerator.__new__(EditorialContentGenerator)
    summary = build_summary()

    draft = EditorialContentGenerator.generate_from_summary(generator, summary)[0]

    assert isinstance(draft, ContentCandidateDraft)
    assert draft.source_summary_hash
    assert draft.payload_json["content_key"] == "result:https://example.com/result-1"
