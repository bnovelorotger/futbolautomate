from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Competition, ContentCandidate
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


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_summary() -> CompetitionEditorialSummary:
    return CompetitionEditorialSummary(
        metadata=EditorialSummaryMetadata(
            competition_slug="division_honor_mallorca",
            competition_name="Division Honor Mallorca",
            reference_date=date(2026, 3, 14),
            generated_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
        ),
        competition_state=EditorialCompetitionState(
            total_teams=18,
            total_matches=306,
            played_matches=216,
            pending_matches=90,
        ),
        latest_results=[
            CompetitionMatchView(
                round_name="Jornada 24",
                match_date=date(2026, 3, 7),
                match_date_raw="sabado, 07 de marzo de 2026",
                match_time=time(16, 0),
                match_time_raw="16:00",
                kickoff_datetime=datetime(2026, 3, 7, 16, 0, tzinfo=timezone.utc),
                home_team="CE Andratx B",
                away_team="CE Sineu",
                home_score=2,
                away_score=1,
                status="finished",
                source_url="https://example.com/m1",
            )
        ],
        upcoming_matches=[
            CompetitionMatchView(
                round_name="Jornada 25",
                match_date=date(2026, 3, 14),
                match_date_raw="sabado, 14 de marzo de 2026",
                match_time=time(16, 0),
                match_time_raw="16:00",
                kickoff_datetime=datetime(2026, 3, 14, 16, 0, tzinfo=timezone.utc),
                home_team="CE Andratx B",
                away_team="CD Ferriolense",
                status="scheduled",
                source_url="https://example.com/m2",
            )
        ],
        current_standings=[
            StandingView(position=1, team="CE Andratx B", points=54, played=24, goals_for=50, goals_against=24, goal_difference=26),
            StandingView(position=2, team="CE Sineu", points=47, played=24, goals_for=43, goals_against=19, goal_difference=24),
            StandingView(position=3, team="CD Ferriolense", points=42, played=24, goals_for=49, goals_against=37, goal_difference=12),
        ],
        rankings=EditorialRankings(
            best_attack=TeamRankingView(team="CE Andratx B", value=50, position=1),
            best_defense=TeamRankingView(team="CE Sineu", value=19, position=2),
            most_wins=TeamRankingView(team="CE Andratx B", value=17, position=1),
        ),
        calendar_windows=EditorialCalendarWindows(today=[], tomorrow=[], next_weekend=[]),
        editorial_news=[],
        aggregate_metrics=EditorialAggregateMetrics(
            total_goals_scored=637,
            average_goals_per_played_match=2.95,
            relevant_news_count=2,
        ),
    )


def test_editorial_content_generator_stores_candidates_idempotently() -> None:
    session = build_session()
    try:
        session.add(
            Competition(
                code="division_honor_mallorca",
                name="Division Honor Mallorca",
                normalized_name="division honor mallorca",
                category_level=6,
                gender="male",
                region="Mallorca",
                country="Spain",
                federation="FFIB",
                source_name="futbolme",
                source_competition_id="4018",
            )
        )
        session.commit()

        generator = EditorialContentGenerator(session)
        summary = build_summary()

        candidates = generator.generate_from_summary(summary)
        stats = generator.store_candidates(candidates)
        session.commit()

        assert stats.found == 4
        assert stats.inserted == 4
        assert stats.updated == 0

        stats_second = generator.store_candidates(candidates)
        session.commit()

        assert stats_second.found == 4
        assert stats_second.inserted == 0
        assert stats_second.updated == 0

        rows = session.execute(
            select(ContentCandidate).where(ContentCandidate.competition_slug == "division_honor_mallorca")
        ).scalars().all()
        assert len(rows) == 4
        assert rows[0].status == "draft"
    finally:
        session.close()


def test_editorial_content_generator_does_not_override_manual_schedule_on_draft() -> None:
    session = build_session()
    try:
        session.add(
            Competition(
                code="division_honor_mallorca",
                name="Division Honor Mallorca",
                normalized_name="division honor mallorca",
                category_level=6,
                gender="male",
                region="Mallorca",
                country="Spain",
                federation="FFIB",
                source_name="futbolme",
                source_competition_id="4018",
            )
        )
        session.commit()

        generator = EditorialContentGenerator(session)
        summary = build_summary()
        candidates = generator.generate_from_summary(summary)
        generator.store_candidates(candidates)
        session.commit()

        candidate = session.execute(
            select(ContentCandidate)
            .where(ContentCandidate.competition_slug == "division_honor_mallorca")
            .order_by(ContentCandidate.id.asc())
        ).scalars().first()
        manual_schedule = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        candidate.scheduled_at = manual_schedule
        session.add(candidate)
        session.commit()

        stats = generator.store_candidates(candidates)
        session.commit()

        refreshed = session.get(ContentCandidate, candidate.id)
        assert stats.inserted == 0
        assert stats.updated == 0
        assert refreshed.scheduled_at == manual_schedule
    finally:
        session.close()


def test_editorial_content_generator_resets_rewrite_fields_when_base_draft_changes() -> None:
    session = build_session()
    try:
        session.add(
            Competition(
                code="division_honor_mallorca",
                name="Division Honor Mallorca",
                normalized_name="division honor mallorca",
                category_level=6,
                gender="male",
                region="Mallorca",
                country="Spain",
                federation="FFIB",
                source_name="futbolme",
                source_competition_id="4018",
            )
        )
        session.commit()

        generator = EditorialContentGenerator(session)
        summary = build_summary()
        candidates = generator.generate_from_summary(summary)
        generator.store_candidates(candidates)
        session.commit()

        candidate = session.execute(
            select(ContentCandidate)
            .where(ContentCandidate.competition_slug == "division_honor_mallorca")
            .order_by(ContentCandidate.id.asc())
        ).scalars().first()
        assert candidate is not None
        candidate.rewritten_text = "Version reescrita antigua"
        candidate.rewrite_status = "rewritten"
        candidate.rewrite_model = "gpt-4.1-mini"
        candidate.rewrite_timestamp = datetime(2026, 3, 14, 13, 0, tzinfo=timezone.utc)
        candidate.rewrite_error = None
        session.add(candidate)
        session.commit()

        updated_candidates = generator.generate_from_summary(summary)
        updated_candidates[0].text_draft = "RESULTADO FINAL\n\nCE Andratx B 3-1 CE Sineu\n\nDivision Honor Mallorca\nJornada 24\nEstado: finished"
        stats = generator.store_candidates(updated_candidates)
        session.commit()

        refreshed = session.get(ContentCandidate, candidate.id)
        assert stats.updated == 1
        assert refreshed.text_draft.startswith("RESULTADO FINAL\n\nCE Andratx B 3-1")
        assert refreshed.rewritten_text is None
        assert refreshed.rewrite_status is None
        assert refreshed.rewrite_model is None
        assert refreshed.rewrite_timestamp is None
        assert refreshed.rewrite_error is None
    finally:
        session.close()


def test_editorial_content_generator_updates_legacy_preview_draft_with_new_anchor_key() -> None:
    session = build_session()
    try:
        session.add(
            Competition(
                code="division_honor_mallorca",
                name="Division Honor Mallorca",
                normalized_name="division honor mallorca",
                category_level=6,
                gender="male",
                region="Mallorca",
                country="Spain",
                federation="FFIB",
                source_name="futbolme",
                source_competition_id="4018",
            )
        )
        session.commit()

        generator = EditorialContentGenerator(session)
        summary = build_summary()
        preview_candidate = next(
            candidate
            for candidate in generator.generate_from_summary(summary)
            if candidate.content_type == "preview"
        )
        session.add(
            ContentCandidate(
                competition_slug="division_honor_mallorca",
                content_type="preview",
                priority=preview_candidate.priority,
                text_draft=preview_candidate.text_draft,
                formatted_text=preview_candidate.formatted_text,
                payload_json={
                    "content_key": "preview:upcoming",
                    "template_name": "preview_v1",
                    "competition_name": summary.metadata.competition_name,
                    "reference_date": summary.metadata.reference_date.isoformat(),
                    "source_payload": preview_candidate.payload_json["source_payload"],
                },
                source_summary_hash="legacy-preview-hash",
                scheduled_at=preview_candidate.scheduled_at,
                status="draft",
            )
        )
        session.commit()

        stats = generator.store_candidates([preview_candidate])
        session.commit()

        rows = session.execute(
            select(ContentCandidate)
            .where(ContentCandidate.competition_slug == "division_honor_mallorca")
            .where(ContentCandidate.content_type == "preview")
        ).scalars().all()

        assert stats.inserted == 0
        assert stats.updated == 1
        assert len(rows) == 1
        assert rows[0].payload_json["content_key"] == "preview:jornada-25:2026-03-14:ce-andratx-b:cd-ferriolense"
        assert rows[0].source_summary_hash == preview_candidate.source_summary_hash
    finally:
        session.close()
