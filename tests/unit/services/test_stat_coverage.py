from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.db.models import Competition, ContentCandidate, Match, ScraperRun, Standing, Team
from app.services.editorial_quality_checks import EditorialQualityChecksService
from app.services.stat_coverage import StatCoverageService
from tests.unit.services.service_test_support import build_export_policy, build_settings
from tests.unit.services.test_editorial_narratives import build_session, seed_narratives_data


def _competition(session) -> Competition:
    return session.scalar(select(Competition).where(Competition.code == "tercera_rfef_g11"))


def _team(session, name: str) -> Team:
    return session.scalar(select(Team).where(Team.name == name))


def test_stat_coverage_reports_incomplete_finished_results() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        competition = _competition(session)
        home = _team(session, "CD Llosetense")
        away = _team(session, "SD Portmany")
        session.add(
            Match(
                external_id="result-incomplete",
                source_name="futbolme",
                source_url="https://example.com/result-incomplete",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo test",
                round_name="Jornada 13",
                raw_match_date="2026-03-16",
                raw_match_time="18:00",
                match_date=date(2026, 3, 16),
                match_time=time(18, 0),
                kickoff_datetime=datetime(2026, 3, 16, 18, 0, tzinfo=timezone.utc),
                home_team_id=home.id,
                away_team_id=away.id,
                home_team_raw=home.name,
                away_team_raw=away.name,
                home_score=None,
                away_score=None,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=datetime(2026, 3, 16, 21, 0, tzinfo=timezone.utc),
                content_hash="result-incomplete",
                extra_data=None,
            )
        )
        session.commit()

        summary = StatCoverageService(session).result_coverage(
            "tercera_rfef_g11",
            season="2025-26",
            reference_date=date(2026, 3, 18),
        )

        assert summary.status == "partial"
        assert summary.expected_count == 5
        assert summary.observed_count == 4
        assert summary.coverage_ratio == 0.8
    finally:
        session.close()


def test_stat_coverage_reports_incomplete_standings_rows() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        row = session.scalar(
            select(Standing).where(
                Standing.competition.has(code="tercera_rfef_g11"),
                Standing.team_raw == "CD Manacor",
            )
        )
        row.points = None
        session.add(row)
        session.commit()

        summary = StatCoverageService(session).standings_coverage(
            "tercera_rfef_g11",
            season="2025-26",
            reference_date=date(2026, 3, 18),
        )

        assert summary.status == "partial"
        assert summary.expected_count == 4
        assert summary.observed_count == 3
        assert summary.coverage_ratio == 0.75
    finally:
        session.close()


def test_stat_coverage_uses_successful_scraper_run_when_standings_are_unchanged() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        old_scraped_at = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        for row in session.scalars(select(Standing).where(Standing.competition.has(code="tercera_rfef_g11"))):
            row.scraped_at = old_scraped_at
            session.add(row)
        session.add(
            ScraperRun(
                scraper_name="FutbolmeScraper",
                source_name="futbolme",
                target_type="standings",
                competition_code="tercera_rfef_g11",
                started_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 3, 18, 8, 1, tzinfo=timezone.utc),
                status="success",
                records_found=4,
                records_inserted=0,
                records_updated=0,
                errors_count=0,
            )
        )
        session.commit()

        summary = StatCoverageService(session).standings_coverage(
            "tercera_rfef_g11",
            season="2025-26",
            reference_date=date(2026, 3, 18),
        )

        assert summary.status == "covered"
        assert summary.details["latest_successful_run_at"] == "2026-03-18T08:01:00+00:00"
        assert summary.details["latest_scraped_at"] == "2026-03-01T10:00:00+00:00"
    finally:
        session.close()


def test_quality_precheck_blocks_result_stat_when_result_coverage_is_low() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        competition = _competition(session)
        home = _team(session, "CD Llosetense")
        away = _team(session, "SD Portmany")
        session.add(
            Match(
                external_id="quality-result-incomplete",
                source_name="futbolme",
                source_url="https://example.com/quality-result-incomplete",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo test",
                round_name="Jornada 13",
                raw_match_date="2026-03-16",
                raw_match_time="18:00",
                match_date=date(2026, 3, 16),
                match_time=time(18, 0),
                kickoff_datetime=datetime(2026, 3, 16, 18, 0, tzinfo=timezone.utc),
                home_team_id=home.id,
                away_team_id=away.id,
                home_team_raw=home.name,
                away_team_raw=away.name,
                home_score=None,
                away_score=None,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=datetime(2026, 3, 16, 21, 0, tzinfo=timezone.utc),
                content_hash="quality-result-incomplete",
                extra_data=None,
            )
        )
        candidate = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="stat_narrative",
            priority=60,
            text_draft="NARRATIVA ESTADISTICA\n\nEn 3a RFEF Grupo 11 se han marcado 9 goles en 4 partidos.",
            payload_json={
                "content_key": "stat:coverage-low",
                "reference_date": "2026-03-18",
                "source_payload": {
                    "season": "2025-26",
                    "played_matches": 4,
                    "total_goals_scored": 9,
                    "average_goals_per_played_match": 2.25,
                },
            },
            source_summary_hash="stat-coverage-low",
            status="draft",
            created_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
        )
        session.add(candidate)
        session.commit()

        result = EditorialQualityChecksService(
            session,
            settings=build_settings(),
            policy=build_export_policy(),
        ).check_candidates([candidate.id], dry_run=True, require_published=False)

        assert result.failed_count == 1
        assert "result_coverage_ratio<0.95" in result.rows[0].errors
    finally:
        session.close()
