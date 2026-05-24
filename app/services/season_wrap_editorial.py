from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType, MatchStatus
from app.core.exceptions import ConfigurationError
from app.core.standings_zones import load_standings_zones
from app.db.models import Competition, Match
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.reporting import CompetitionMatchView, StandingView
from app.services.competition_queries import CompetitionQueryService
from app.services.editorial_formatter import EditorialFormatterService
from app.utils.hashing import stable_hash


@dataclass(slots=True)
class PlayoffTieSummary:
    team_a: str
    team_b: str
    team_a_goals: int
    team_b_goals: int
    winner: str | None
    match_count: int


class SeasonWrapEditorialService:
    """Builds end-of-season editorial drafts from already ingested local data."""

    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = CompetitionQueryService(session)
        self.repository = ContentCandidateRepository(session)
        self.catalog = load_competition_catalog()
        self.zones = load_standings_zones()

    def build_stats_drafts(
        self,
        competition_slug: str,
        *,
        reference_date: date | None = None,
    ) -> list[ContentCandidateDraft]:
        selected_date = self._reference_date(reference_date)
        standings = self._standings(competition_slug)
        matches = self._finished_matches(competition_slug, reference_date=selected_date)
        if not matches:
            return []

        source_payload = self._stats_payload(competition_slug, matches, standings)
        content_key = self._season_content_key(
            ContentType.SEASON_WRAP_STATS,
            competition_slug,
            source_payload,
        )
        return [
            ContentCandidateDraft(
                competition_slug=competition_slug,
                content_type=ContentType.SEASON_WRAP_STATS,
                priority=88,
                text_draft=self._stats_text(source_payload),
                payload_json={
                    "content_key": content_key,
                    "template_name": "season_wrap_stats_v1",
                    "competition_name": self._competition_name(competition_slug),
                    "reference_date": selected_date.isoformat(),
                    "source_payload": source_payload,
                },
                source_summary_hash=self._summary_hash(
                    competition_slug,
                    ContentType.SEASON_WRAP_STATS,
                    content_key,
                    source_payload,
                ),
                status=ContentCandidateStatus.DRAFT,
            )
        ]

    def build_outcome_drafts(
        self,
        competition_slug: str,
        *,
        reference_date: date | None = None,
    ) -> list[ContentCandidateDraft]:
        selected_date = self._reference_date(reference_date)
        standings = self._standings(competition_slug)
        matches = self._finished_matches(competition_slug, reference_date=selected_date)
        if not standings and not matches:
            return []

        source_payload = self._outcomes_payload(
            competition_slug,
            standings,
            matches,
            reference_date=selected_date,
        )
        if not self._has_outcome_signal(source_payload):
            return []
        content_key = self._season_content_key(
            ContentType.SEASON_WRAP_OUTCOMES,
            competition_slug,
            source_payload,
        )
        return [
            ContentCandidateDraft(
                competition_slug=competition_slug,
                content_type=ContentType.SEASON_WRAP_OUTCOMES,
                priority=91,
                text_draft=self._outcomes_text(source_payload),
                payload_json={
                    "content_key": content_key,
                    "template_name": "season_wrap_outcomes_v1",
                    "competition_name": self._competition_name(competition_slug),
                    "reference_date": selected_date.isoformat(),
                    "source_payload": source_payload,
                },
                source_summary_hash=self._summary_hash(
                    competition_slug,
                    ContentType.SEASON_WRAP_OUTCOMES,
                    content_key,
                    source_payload,
                ),
                status=ContentCandidateStatus.DRAFT,
            )
        ]

    def store_candidates(self, candidates: list[ContentCandidateDraft]) -> IngestStats:
        formatted_candidates = EditorialFormatterService(self.session, settings=self.settings).apply_to_drafts(
            candidates
        )
        stats = IngestStats(found=len(formatted_candidates))
        for candidate in formatted_candidates:
            _, inserted, updated = self.repository.upsert(candidate.model_dump(mode="python"))
            stats.inserted += int(inserted)
            stats.updated += int(updated)
        return stats

    def _stats_payload(
        self,
        competition_slug: str,
        matches: list[CompetitionMatchView],
        standings: list[StandingView],
    ) -> dict[str, Any]:
        scored_matches = [
            match
            for match in matches
            if match.home_score is not None and match.away_score is not None
        ]
        total_goals = sum(int(match.home_score or 0) + int(match.away_score or 0) for match in scored_matches)
        home_wins = sum(1 for match in scored_matches if int(match.home_score or 0) > int(match.away_score or 0))
        away_wins = sum(1 for match in scored_matches if int(match.home_score or 0) < int(match.away_score or 0))
        draws = sum(1 for match in scored_matches if int(match.home_score or 0) == int(match.away_score or 0))
        highest_scoring = max(
            scored_matches,
            key=lambda match: int(match.home_score or 0) + int(match.away_score or 0),
            default=None,
        )
        best_attack = max(
            [row for row in standings if row.goals_for is not None],
            key=lambda row: int(row.goals_for or 0),
            default=None,
        )
        best_defense = min(
            [row for row in standings if row.goals_against is not None],
            key=lambda row: int(row.goals_against or 0),
            default=None,
        )
        return {
            "summary_kind": "season_wrap_stats",
            "editorial_phase": "season_wrap",
            "season": self._latest_season(competition_slug),
            "finished_matches_count": len(matches),
            "scored_matches_count": len(scored_matches),
            "total_goals": total_goals,
            "average_goals_per_match": round(total_goals / len(scored_matches), 2) if scored_matches else None,
            "home_wins": home_wins,
            "draws": draws,
            "away_wins": away_wins,
            "highest_scoring_match": highest_scoring.model_dump(mode="json") if highest_scoring is not None else None,
            "best_attack": best_attack.model_dump(mode="json") if best_attack is not None else None,
            "best_defense": best_defense.model_dump(mode="json") if best_defense is not None else None,
            "teams": [row.team for row in standings[:6]],
        }

    def _outcomes_payload(
        self,
        competition_slug: str,
        standings: list[StandingView],
        matches: list[CompetitionMatchView],
        *,
        reference_date: date,
    ) -> dict[str, Any]:
        zone_config = self.zones.get(competition_slug)
        playoff_positions = set(zone_config.playoff_positions if zone_config is not None else [])
        relegation_positions = set(zone_config.relegation_positions if zone_config is not None else [])
        champion = next((row for row in standings if row.position == 1), None)
        playoff_rows = [row for row in standings if row.position in playoff_positions]
        relegation_rows = [row for row in standings if row.position in relegation_positions]
        tie_summaries = self._playoff_tie_summaries(matches) if self._is_playoff_competition(competition_slug) else []
        child_playoffs = self._child_playoff_outcomes(competition_slug, reference_date=reference_date)
        teams = {
            row.team
            for row in [champion, *playoff_rows, *relegation_rows]
            if row is not None
        }
        for tie in tie_summaries:
            teams.update({tie.team_a, tie.team_b})
            if tie.winner:
                teams.add(tie.winner)
        for child in child_playoffs:
            for tie in child["ties"]:
                teams.update({tie["team_a"], tie["team_b"]})
                if tie.get("winner"):
                    teams.add(str(tie["winner"]))

        return {
            "summary_kind": "season_wrap_outcomes",
            "editorial_phase": "season_wrap",
            "season": self._latest_season(competition_slug),
            "champion": champion.model_dump(mode="json") if champion is not None else None,
            "playoff_rows": [row.model_dump(mode="json") for row in playoff_rows],
            "relegation_rows": [row.model_dump(mode="json") for row in relegation_rows],
            "playoff_ties": [self._tie_payload(tie) for tie in tie_summaries],
            "child_playoff_outcomes": child_playoffs,
            "teams": sorted(teams),
        }

    def _child_playoff_outcomes(self, competition_slug: str, *, reference_date: date) -> list[dict[str, Any]]:
        outcomes: list[dict[str, Any]] = []
        for child_slug in self._child_playoff_slugs(competition_slug):
            matches = self._finished_matches(child_slug, reference_date=reference_date)
            if not self._matches_recent_enough(matches, reference_date=reference_date):
                continue
            ties = [self._tie_payload(tie) for tie in self._playoff_tie_summaries(matches)]
            if not ties:
                continue
            outcomes.append(
                {
                    "competition_slug": child_slug,
                    "competition_name": self._competition_name(child_slug),
                    "playoff_type": self.catalog.get(child_slug).playoff_type if self.catalog.get(child_slug) else None,
                    "ties": ties,
                }
            )
        return outcomes

    def _playoff_tie_summaries(self, matches: list[CompetitionMatchView]) -> list[PlayoffTieSummary]:
        buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for match in matches:
            if match.home_score is None or match.away_score is None:
                continue
            team_a, team_b = sorted([match.home_team, match.away_team])
            bucket = buckets.setdefault(
                (team_a, team_b),
                {"team_a_goals": 0, "team_b_goals": 0, "match_count": 0},
            )
            home_score = int(match.home_score or 0)
            away_score = int(match.away_score or 0)
            if match.home_team == team_a:
                bucket["team_a_goals"] += home_score
                bucket["team_b_goals"] += away_score
            else:
                bucket["team_a_goals"] += away_score
                bucket["team_b_goals"] += home_score
            bucket["match_count"] += 1
        summaries: list[PlayoffTieSummary] = []
        for (team_a, team_b), values in sorted(buckets.items()):
            team_a_goals = int(values["team_a_goals"])
            team_b_goals = int(values["team_b_goals"])
            winner = None
            if team_a_goals > team_b_goals:
                winner = team_a
            elif team_b_goals > team_a_goals:
                winner = team_b
            summaries.append(
                PlayoffTieSummary(
                    team_a=team_a,
                    team_b=team_b,
                    team_a_goals=team_a_goals,
                    team_b_goals=team_b_goals,
                    winner=winner,
                    match_count=int(values["match_count"]),
                )
            )
        return summaries

    def _tie_payload(self, tie: PlayoffTieSummary) -> dict[str, Any]:
        return {
            "team_a": tie.team_a,
            "team_b": tie.team_b,
            "team_a_goals": tie.team_a_goals,
            "team_b_goals": tie.team_b_goals,
            "winner": tie.winner,
            "match_count": tie.match_count,
        }

    def _stats_text(self, source_payload: dict[str, Any]) -> str:
        matches = int(source_payload.get("finished_matches_count") or 0)
        goals = int(source_payload.get("total_goals") or 0)
        average = source_payload.get("average_goals_per_match")
        parts = [f"Balance final: {matches} partidos, {goals} goles"]
        if isinstance(average, (int, float)):
            parts[0] += f" ({average:.2f}/p)"
        best_attack = source_payload.get("best_attack")
        if isinstance(best_attack, dict) and best_attack.get("team") and best_attack.get("goals_for") is not None:
            parts.append(f"Mejor ataque: {best_attack['team']} ({best_attack['goals_for']})")
        best_defense = source_payload.get("best_defense")
        if (
            isinstance(best_defense, dict)
            and best_defense.get("team")
            and best_defense.get("goals_against") is not None
        ):
            parts.append(f"Mejor defensa: {best_defense['team']} ({best_defense['goals_against']})")
        return ". ".join(parts) + "."

    def _outcomes_text(self, source_payload: dict[str, Any]) -> str:
        parts: list[str] = []
        champion = source_payload.get("champion")
        if isinstance(champion, dict) and champion.get("team"):
            suffix = f" ({champion['points']} pts)" if champion.get("points") is not None else ""
            parts.append(f"Campeon: {champion['team']}{suffix}")

        playoff_rows = [row for row in source_payload.get("playoff_rows") or [] if isinstance(row, dict)]
        if playoff_rows:
            parts.append("Playoff: " + ", ".join(str(row.get("team")) for row in playoff_rows[:5] if row.get("team")))

        relegation_rows = [row for row in source_payload.get("relegation_rows") or [] if isinstance(row, dict)]
        if relegation_rows:
            parts.append("Descenso: " + ", ".join(str(row.get("team")) for row in relegation_rows[:5] if row.get("team")))

        playoff_ties = [row for row in source_payload.get("playoff_ties") or [] if isinstance(row, dict)]
        if playoff_ties:
            winners = [str(row["winner"]) for row in playoff_ties if row.get("winner")]
            if winners:
                parts.append("Eliminatorias: " + ", ".join(winners[:4]))

        child_playoff_outcomes = [
            row for row in source_payload.get("child_playoff_outcomes") or [] if isinstance(row, dict)
        ]
        child_winners: list[str] = []
        for child in child_playoff_outcomes:
            for tie in child.get("ties") or []:
                if isinstance(tie, dict) and tie.get("winner"):
                    child_winners.append(str(tie["winner"]))
        if child_winners:
            parts.append("Playoff cerrado: " + ", ".join(dict.fromkeys(child_winners[:4])))

        return ". ".join(parts) + "."

    def _has_outcome_signal(self, source_payload: dict[str, Any]) -> bool:
        return any(
            bool(source_payload.get(key))
            for key in (
                "champion",
                "playoff_rows",
                "relegation_rows",
                "playoff_ties",
                "child_playoff_outcomes",
            )
        )

    def _standings(self, competition_slug: str) -> list[StandingView]:
        try:
            return self.queries.current_standings(competition_slug)
        except ConfigurationError:
            return []

    def _finished_matches(
        self,
        competition_slug: str,
        *,
        reference_date: date | None,
    ) -> list[CompetitionMatchView]:
        try:
            return self.queries.finished_matches(
                competition_slug,
                limit=None,
                relevant_only=False,
                reference_date=reference_date,
            )
        except ConfigurationError:
            return []

    def _matches_recent_enough(self, matches: list[CompetitionMatchView], *, reference_date: date) -> bool:
        match_dates = [match.match_date for match in matches if match.match_date is not None]
        if not match_dates:
            return False
        return max(match_dates) >= date.fromordinal(reference_date.toordinal() - 30)

    def _latest_season(self, competition_slug: str) -> str | None:
        return self.session.scalar(
            select(Match.season)
            .where(
                Match.competition.has(code=competition_slug),
                Match.status == str(MatchStatus.FINISHED),
                Match.season.is_not(None),
            )
            .order_by(Match.match_date.desc().nullslast(), Match.id.desc())
            .limit(1)
        )

    def _competition_name(self, competition_slug: str) -> str:
        definition = self.catalog.get(competition_slug)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        competition = self.session.scalar(select(Competition).where(Competition.code == competition_slug))
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_slug}")
        return competition.name

    def _is_playoff_competition(self, competition_slug: str) -> bool:
        definition = self.catalog.get(competition_slug)
        return bool(
            (definition is not None and definition.competition_type == "playoff")
            or "playoff" in competition_slug.lower()
        )

    def _child_playoff_slugs(self, competition_slug: str) -> list[str]:
        return sorted(
            slug
            for slug, definition in self.catalog.items()
            if definition.parent_competition == competition_slug or (
                definition.parent_competition is None
                and self._is_playoff_competition(slug)
                and slug.startswith(f"{competition_slug}_")
            )
        )

    def _season_content_key(
        self,
        content_type: ContentType,
        competition_slug: str,
        source_payload: dict[str, Any],
    ) -> str:
        season = source_payload.get("season") or "seasonless"
        return f"{content_type}:{competition_slug}:{season}"

    def _summary_hash(
        self,
        competition_slug: str,
        content_type: ContentType,
        content_key: str,
        source_payload: dict[str, Any],
    ) -> str:
        return stable_hash(
            {
                "competition_slug": competition_slug,
                "content_type": str(content_type),
                "content_key": content_key,
                "source_payload": source_payload,
            }
        )

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.settings.timezone)).date()
