from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    ContentType,
    DataCoverageStatus,
    DataCoverageType,
    NarrativeMetricType,
    ViralStoryType,
)
from app.db.models import Competition, ContentCandidate, Match, ScraperRun, Standing
from app.db.repositories.standings import StandingRepository
from app.schemas.stat_coverage import StatCoverageReport, StatCoverageSummary
from app.utils.time import utcnow

RESULT_COVERAGE_MIN_RATIO = 0.95
STANDINGS_COVERAGE_MIN_RATIO = 1.0
STANDINGS_MAX_STALENESS_DAYS = 7

_RESULT_DEPENDENT_METRICS = {
    NarrativeMetricType.WIN_STREAK,
    NarrativeMetricType.UNBEATEN_STREAK,
    NarrativeMetricType.GOALS_AVERAGE,
}
_STANDINGS_DEPENDENT_METRICS = {
    NarrativeMetricType.BEST_ATTACK,
    NarrativeMetricType.BEST_DEFENSE,
    NarrativeMetricType.MOST_WINS,
}
_RESULT_DEPENDENT_VIRAL = {
    ViralStoryType.WIN_STREAK,
    ViralStoryType.UNBEATEN_STREAK,
    ViralStoryType.LOSING_STREAK,
    ViralStoryType.RECENT_TOP_SCORER,
    ViralStoryType.HOT_FORM,
    ViralStoryType.COLD_FORM,
    ViralStoryType.GOALS_TREND,
}
_STANDINGS_DEPENDENT_VIRAL = {
    ViralStoryType.BEST_ATTACK,
    ViralStoryType.BEST_DEFENSE,
}
_RESULT_DEPENDENT_CONTENT = {
    ContentType.MATCH_RESULT,
    ContentType.RESULTS_ROUNDUP,
    ContentType.STAT_NARRATIVE,
    ContentType.FORM_RANKING,
    ContentType.FORM_EVENT,
}
_STANDINGS_DEPENDENT_CONTENT = {
    ContentType.STANDINGS,
    ContentType.STANDINGS_ROUNDUP,
    ContentType.STANDINGS_EVENT,
    ContentType.RANKING,
    ContentType.RACE_NARRATIVE,
    ContentType.MATCH_IMPACT_SCENARIO,
}


class StatCoverageService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.standings_repository = StandingRepository(session)

    def report(
        self,
        competition_slug: str,
        *,
        season: str | None = None,
        reference_date: date | None = None,
    ) -> StatCoverageReport:
        selected_date = reference_date or utcnow().date()
        return StatCoverageReport(
            competition_slug=competition_slug,
            season=season,
            reference_date=selected_date,
            rows=[
                self.result_coverage(competition_slug, season=season, reference_date=selected_date),
                self.standings_coverage(competition_slug, season=season, reference_date=selected_date),
            ],
        )

    def result_coverage(
        self,
        competition_slug: str,
        *,
        season: str | None = None,
        reference_date: date | None = None,
    ) -> StatCoverageSummary:
        competition = self._competition(competition_slug)
        filters = [
            Match.competition_id == competition.id,
            Match.status == "finished",
        ]
        if season:
            filters.append(Match.season == season)
        if reference_date is not None:
            filters.append(Match.match_date <= reference_date)

        expected_count = self.session.scalar(select(func.count()).select_from(Match).where(*filters)) or 0
        observed_count = (
            self.session.scalar(
                select(func.count())
                .select_from(Match)
                .where(
                    *filters,
                    Match.home_score.is_not(None),
                    Match.away_score.is_not(None),
                )
            )
            or 0
        )
        ratio = float(observed_count) / float(expected_count) if expected_count else 0.0
        if expected_count == 0:
            status = DataCoverageStatus.NO_DATA
        elif ratio >= RESULT_COVERAGE_MIN_RATIO:
            status = DataCoverageStatus.COVERED
        elif observed_count > 0:
            status = DataCoverageStatus.PARTIAL
        else:
            status = DataCoverageStatus.SOURCE_MISSING
        return StatCoverageSummary(
            competition_slug=competition_slug,
            season=season,
            reference_date=reference_date,
            data_type=DataCoverageType.RESULT,
            status=status,
            expected_count=int(expected_count),
            observed_count=int(observed_count),
            coverage_ratio=round(ratio, 4),
            checked_at=utcnow(),
            details={"threshold": RESULT_COVERAGE_MIN_RATIO},
        )

    def standings_coverage(
        self,
        competition_slug: str,
        *,
        season: str | None = None,
        reference_date: date | None = None,
    ) -> StatCoverageSummary:
        competition = self._competition(competition_slug)
        query = select(Standing).where(Standing.competition_id == competition.id)
        if season:
            query = query.where(Standing.season == season)
        rows = self.session.scalars(query.order_by(Standing.position.asc())).all()
        complete_rows = [
            row
            for row in rows
            if row.position is not None
            and row.team_raw
            and row.played is not None
            and row.points is not None
            and row.goals_for is not None
            and row.goals_against is not None
        ]
        schedule_team_count = len(self.standings_repository.team_schedule_counts(competition.id))
        expected_count = max(len(rows), schedule_team_count)
        observed_count = len(complete_rows)
        ratio = float(observed_count) / float(expected_count) if expected_count else 0.0
        latest_scraped_at = self._latest_datetime(row.scraped_at for row in rows if row.scraped_at is not None)
        latest_successful_run_at = self._latest_successful_standings_run_at(
            competition_slug,
            expected_count=expected_count,
        )
        latest_observed_at = self._latest_datetime(
            value for value in (latest_scraped_at, latest_successful_run_at) if value is not None
        )
        stale_days = self._stale_days(latest_observed_at, reference_date)
        stale = stale_days is not None and stale_days > STANDINGS_MAX_STALENESS_DAYS

        if expected_count == 0:
            status = DataCoverageStatus.NO_DATA
        elif ratio >= STANDINGS_COVERAGE_MIN_RATIO and not stale:
            status = DataCoverageStatus.COVERED
        elif ratio >= STANDINGS_COVERAGE_MIN_RATIO and stale:
            status = DataCoverageStatus.STALE
        elif observed_count > 0:
            status = DataCoverageStatus.PARTIAL
        else:
            status = DataCoverageStatus.SOURCE_MISSING
        return StatCoverageSummary(
            competition_slug=competition_slug,
            season=season,
            reference_date=reference_date,
            data_type=DataCoverageType.STANDINGS,
            status=status,
            expected_count=int(expected_count),
            observed_count=int(observed_count),
            coverage_ratio=round(ratio, 4),
            checked_at=utcnow(),
            details={
                "threshold": STANDINGS_COVERAGE_MIN_RATIO,
                "latest_scraped_at": latest_scraped_at.isoformat() if latest_scraped_at else None,
                "latest_successful_run_at": latest_successful_run_at.isoformat() if latest_successful_run_at else None,
                "latest_observed_at": latest_observed_at.isoformat() if latest_observed_at else None,
                "stale_days": stale_days,
                "max_staleness_days": STANDINGS_MAX_STALENESS_DAYS,
                "schedule_team_count": schedule_team_count,
            },
        )

    def coverage_errors_for_candidate(
        self,
        candidate: ContentCandidate,
        source_payload: dict[str, Any],
    ) -> list[str]:
        requirements = self._requirements(candidate, source_payload)
        if not requirements:
            return []
        season = self._candidate_season(candidate, source_payload)
        reference_date = self._candidate_reference_date(candidate, source_payload)
        errors: list[str] = []
        if DataCoverageType.RESULT in requirements:
            errors.extend(
                self._result_errors(
                    candidate.competition_slug,
                    season=season,
                    reference_date=reference_date,
                    source_payload=source_payload,
                )
            )
        if DataCoverageType.STANDINGS in requirements:
            errors.extend(
                self._standings_errors(
                    candidate.competition_slug,
                    season=season,
                    reference_date=reference_date,
                    source_payload=source_payload,
                )
            )
        return errors

    def _result_errors(
        self,
        competition_slug: str,
        *,
        season: str | None,
        reference_date: date | None,
        source_payload: dict[str, Any],
    ) -> list[str]:
        summary = self.result_coverage(competition_slug, season=season, reference_date=reference_date)
        if summary.status == DataCoverageStatus.NO_DATA:
            if self._payload_has_complete_results(source_payload):
                return []
            return ["result_coverage_no_finished_matches"]
        if summary.coverage_ratio < RESULT_COVERAGE_MIN_RATIO:
            return [f"result_coverage_ratio<{RESULT_COVERAGE_MIN_RATIO:g}"]
        return []

    def _standings_errors(
        self,
        competition_slug: str,
        *,
        season: str | None,
        reference_date: date | None,
        source_payload: dict[str, Any],
    ) -> list[str]:
        summary = self.standings_coverage(competition_slug, season=season, reference_date=reference_date)
        if summary.status == DataCoverageStatus.NO_DATA:
            if self._payload_has_complete_standings(source_payload):
                return []
            return ["standings_coverage_rows_missing"]
        if summary.coverage_ratio < STANDINGS_COVERAGE_MIN_RATIO:
            return [f"standings_coverage_ratio<{STANDINGS_COVERAGE_MIN_RATIO:g}"]
        stale_days = summary.details.get("stale_days")
        if isinstance(stale_days, int) and stale_days > STANDINGS_MAX_STALENESS_DAYS:
            return [f"standings_coverage_stale>{STANDINGS_MAX_STALENESS_DAYS}d"]
        return []

    def _requirements(
        self,
        candidate: ContentCandidate,
        source_payload: dict[str, Any],
    ) -> set[DataCoverageType]:
        content_type = ContentType(candidate.content_type)
        requirements: set[DataCoverageType] = set()
        if content_type in _RESULT_DEPENDENT_CONTENT:
            requirements.add(DataCoverageType.RESULT)
        if content_type in _STANDINGS_DEPENDENT_CONTENT:
            requirements.add(DataCoverageType.STANDINGS)
        if content_type == ContentType.METRIC_NARRATIVE:
            metric = self._safe_metric_type(source_payload.get("narrative_type"))
            if metric in _RESULT_DEPENDENT_METRICS:
                requirements.add(DataCoverageType.RESULT)
            if metric in _STANDINGS_DEPENDENT_METRICS:
                requirements.add(DataCoverageType.STANDINGS)
        if content_type == ContentType.VIRAL_STORY:
            story_type = self._safe_viral_type(source_payload.get("story_type"))
            if story_type in _RESULT_DEPENDENT_VIRAL:
                requirements.add(DataCoverageType.RESULT)
            if story_type in _STANDINGS_DEPENDENT_VIRAL:
                requirements.add(DataCoverageType.STANDINGS)
        return requirements

    def _competition(self, competition_slug: str) -> Competition:
        competition = self.session.scalar(select(Competition).where(Competition.code == competition_slug))
        if competition is None:
            raise ValueError(f"Competicion desconocida: {competition_slug}")
        return competition

    def _candidate_season(self, candidate: ContentCandidate, source_payload: dict[str, Any]) -> str | None:
        season = source_payload.get("season")
        if isinstance(season, str) and season.strip():
            return season.strip()
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        season = payload.get("season")
        return season.strip() if isinstance(season, str) and season.strip() else None

    def _candidate_reference_date(self, candidate: ContentCandidate, source_payload: dict[str, Any]) -> date | None:
        for raw in (
            source_payload.get("reference_date"),
            (candidate.payload_json or {}).get("reference_date") if isinstance(candidate.payload_json, dict) else None,
            candidate.published_at,
            candidate.approved_at,
            candidate.reviewed_at,
            candidate.scheduled_at,
            candidate.created_at,
        ):
            parsed = self._parse_date(raw)
            if parsed is not None:
                return parsed
        return None

    def _payload_has_complete_results(self, source_payload: dict[str, Any]) -> bool:
        if isinstance(source_payload.get("home_score"), int) and isinstance(source_payload.get("away_score"), int):
            return True
        result_metric_keys = {
            "streak_length",
            "recent_points",
            "recent_matches",
            "played_matches",
            "average_goals_per_played_match",
            "total_goals",
            "total_goals_scored",
            "season_matches",
            "recent_average",
            "season_average",
            "delta",
        }
        if any(key in source_payload for key in result_metric_keys):
            return True
        matches = source_payload.get("matches")
        if not isinstance(matches, list) or not matches:
            return False
        for row in matches:
            if not isinstance(row, dict):
                return False
            if not isinstance(row.get("home_score"), int) or not isinstance(row.get("away_score"), int):
                return False
        return True

    def _payload_has_complete_standings(self, source_payload: dict[str, Any]) -> bool:
        if any(isinstance(source_payload.get(key), dict) for key in ("best_attack", "best_defense", "most_wins")):
            return True
        rows = source_payload.get("rows")
        if not isinstance(rows, list) or not rows:
            teams = source_payload.get("teams")
            if not isinstance(teams, list) or not teams:
                return False
            return all(
                isinstance(row, dict)
                and isinstance(row.get("team"), str)
                and isinstance(row.get("position"), int)
                and isinstance(row.get("points"), int)
                for row in teams
            )
        for row in rows:
            if not isinstance(row, dict):
                return False
            if not isinstance(row.get("position"), int):
                return False
            if not isinstance(row.get("team"), str) or not row["team"].strip():
                return False
            if not isinstance(row.get("points"), int):
                return False
        return True

    def _stale_days(self, scraped_at: datetime | None, reference_date: date | None) -> int | None:
        if scraped_at is None or reference_date is None:
            return None
        value = self._normalize_datetime(scraped_at)
        return max((reference_date - value.date()).days, 0)

    def _latest_datetime(self, values) -> datetime | None:
        normalized = [self._normalize_datetime(value) for value in values if value is not None]
        return max(normalized, default=None)

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _parse_date(self, value: object) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str) and value.strip():
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

    def _safe_metric_type(self, value: object) -> NarrativeMetricType | None:
        if not isinstance(value, str):
            return None
        try:
            return NarrativeMetricType(value)
        except ValueError:
            return None

    def _safe_viral_type(self, value: object) -> ViralStoryType | None:
        if not isinstance(value, str):
            return None
        try:
            return ViralStoryType(value)
        except ValueError:
            return None

    def _latest_successful_standings_run_at(
        self,
        competition_slug: str,
        *,
        expected_count: int,
    ) -> datetime | None:
        query = (
            select(ScraperRun.finished_at)
            .where(
                ScraperRun.competition_code == competition_slug,
                ScraperRun.target_type == "standings",
                ScraperRun.status == "success",
                ScraperRun.finished_at.is_not(None),
            )
            .order_by(ScraperRun.finished_at.desc())
            .limit(1)
        )
        if expected_count > 0:
            query = query.where(ScraperRun.records_found >= expected_count)
        value = self.session.scalar(query)
        return self._normalize_datetime(value) if value is not None else None
