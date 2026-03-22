from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import ContentCandidateStatus, ContentType
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft, ContentGenerationResult
from app.schemas.editorial_summary import CompetitionEditorialSummary
from app.schemas.reporting import CompetitionMatchView, StandingView
from app.services.editorial_formatter import EditorialFormatterService
from app.services.editorial_summary import CompetitionEditorialSummaryService
from app.utils.hashing import stable_hash
from app.utils.time import utcnow


def _score_line(match: CompetitionMatchView) -> str:
    if match.home_score is not None and match.away_score is not None:
        return f"{match.home_team} {match.home_score}-{match.away_score} {match.away_team}"
    return f"{match.home_team} vs {match.away_team}"


def _match_label(match: CompetitionMatchView) -> str:
    parts = [match.round_name or "-", match.match_date_raw or "-"]
    if match.match_time_raw:
        parts.append(match.match_time_raw)
    parts.append(f"{match.home_team} vs {match.away_team}")
    return " | ".join(parts)


def _candidate_hash(
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


class EditorialContentGenerator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.summary_service = CompetitionEditorialSummaryService(session)
        self.repository = ContentCandidateRepository(session)

    def _draft(
        self,
        summary: CompetitionEditorialSummary,
        content_type: ContentType,
        priority: int,
        content_key: str,
        text_draft: str,
        source_payload: dict[str, Any],
        scheduled_at=None,
    ) -> ContentCandidateDraft:
        payload_json = {
            "content_key": content_key,
            "template_name": f"{content_type}_v1",
            "competition_name": summary.metadata.competition_name,
            "reference_date": summary.metadata.reference_date.isoformat(),
            "source_payload": source_payload,
        }
        return ContentCandidateDraft(
            competition_slug=summary.metadata.competition_slug,
            content_type=content_type,
            priority=priority,
            text_draft=text_draft,
            payload_json=payload_json,
            source_summary_hash=_candidate_hash(
                competition_slug=summary.metadata.competition_slug,
                content_type=content_type,
                content_key=content_key,
                source_payload=source_payload,
            ),
            scheduled_at=scheduled_at,
            status=ContentCandidateStatus.DRAFT,
        )

    def _result_candidates(self, summary: CompetitionEditorialSummary) -> list[ContentCandidateDraft]:
        drafts: list[ContentCandidateDraft] = []
        for index, match in enumerate(summary.latest_results, start=1):
            if match.home_score is None or match.away_score is None:
                continue
            source_payload = {
                "source_url": match.source_url,
                "round_name": match.round_name,
                "match_date_raw": match.match_date_raw,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "home_score": match.home_score,
                "away_score": match.away_score,
                "status": match.status,
            }
            text_draft = (
                "RESULTADO FINAL\n\n"
                f"{_score_line(match)}\n\n"
                f"{summary.metadata.competition_name}\n"
                f"{match.round_name or '-'}\n"
                f"Estado: {match.status}"
            )
            drafts.append(
                self._draft(
                    summary=summary,
                    content_type=ContentType.MATCH_RESULT,
                    priority=100 - index,
                    content_key=f"result:{match.source_url}",
                    text_draft=text_draft,
                    source_payload=source_payload,
                    scheduled_at=match.kickoff_datetime,
                )
            )
        return drafts

    def _standings_candidate(self, summary: CompetitionEditorialSummary) -> ContentCandidateDraft | None:
        if not summary.current_standings:
            return None
        top_rows = summary.current_standings[:3]
        lines = [
            "CLASIFICACION",
            "",
            summary.metadata.competition_name,
            "",
        ]
        for row in top_rows:
            lines.append(f"{row.position}. {row.team} - {row.points} pts")
        source_payload = {
            "rows": [row.model_dump(mode="json") for row in top_rows],
        }
        return self._draft(
            summary=summary,
            content_type=ContentType.STANDINGS,
            priority=80,
            content_key="standings:top3",
            text_draft="\n".join(lines),
            source_payload=source_payload,
        )

    def _preview_candidate(self, summary: CompetitionEditorialSummary) -> ContentCandidateDraft | None:
        if not summary.upcoming_matches:
            return None
        selected_matches = summary.upcoming_matches[:3]
        featured_match = summary.upcoming_matches[0]
        lines = [
            "PREVIA DE LA JORNADA",
            "",
            summary.metadata.competition_name,
            "",
        ]
        for match in selected_matches:
            lines.append(_match_label(match))
        lines.extend(
            [
                "",
                f"Partido destacado: {featured_match.home_team} vs {featured_match.away_team}",
            ]
        )
        source_payload = {
            "matches": [match.model_dump(mode="json") for match in selected_matches],
            "featured_match": featured_match.model_dump(mode="json"),
        }
        return self._draft(
            summary=summary,
            content_type=ContentType.PREVIEW,
            priority=90,
            content_key="preview:upcoming",
            text_draft="\n".join(lines),
            source_payload=source_payload,
            scheduled_at=featured_match.kickoff_datetime,
        )

    def _ranking_candidate(self, summary: CompetitionEditorialSummary) -> ContentCandidateDraft | None:
        ranking_lines: list[str] = []
        source_payload: dict[str, Any] = {}
        seen_teams: set[str] = set()
        for key, label, row in (
            ("best_attack", "Mejor ataque", summary.rankings.best_attack),
            ("best_defense", "Mejor defensa", summary.rankings.best_defense),
            ("most_wins", "Mas victorias", summary.rankings.most_wins),
        ):
            if row is None:
                continue
            normalized_team = row.team.strip().lower()
            if normalized_team in seen_teams:
                continue
            seen_teams.add(normalized_team)
            ranking_lines.append(f"{label}: {row.team} ({row.value})")
            source_payload[key] = row.model_dump(mode="json")
        if not ranking_lines:
            return None
        text_draft = "\n".join(
            [
                "RANKINGS DESTACADOS",
                "",
                summary.metadata.competition_name,
                "",
                *ranking_lines,
            ]
        )
        return self._draft(
            summary=summary,
            content_type=ContentType.RANKING,
            priority=70,
            content_key="ranking:overview",
            text_draft=text_draft,
            source_payload=source_payload,
        )

    def _stat_narrative_candidate(self, summary: CompetitionEditorialSummary) -> ContentCandidateDraft | None:
        if summary.competition_state.played_matches == 0:
            return None
        source_payload = {
            "played_matches": summary.competition_state.played_matches,
            "total_goals_scored": summary.aggregate_metrics.total_goals_scored,
            "average_goals_per_played_match": summary.aggregate_metrics.average_goals_per_played_match,
        }
        extra_sentence = ""
        if summary.rankings.best_attack is not None:
            extra_sentence = (
                f" {summary.rankings.best_attack.team} firma el mejor ataque con "
                f"{summary.rankings.best_attack.value} goles."
            )
        text_draft = (
            "NARRATIVA ESTADISTICA\n\n"
            f"En {summary.metadata.competition_name} se han marcado "
            f"{summary.aggregate_metrics.total_goals_scored} goles en "
            f"{summary.competition_state.played_matches} partidos jugados, con una media de "
            f"{summary.aggregate_metrics.average_goals_per_played_match} por encuentro."
            f"{extra_sentence}"
        )
        return self._draft(
            summary=summary,
            content_type=ContentType.STAT_NARRATIVE,
            priority=60,
            content_key="stat:aggregate",
            text_draft=text_draft,
            source_payload=source_payload,
        )

    def generate_from_summary(self, summary: CompetitionEditorialSummary) -> list[ContentCandidateDraft]:
        drafts: list[ContentCandidateDraft] = []
        standings_candidate = self._standings_candidate(summary)
        if standings_candidate is not None:
            drafts.append(standings_candidate)

        preview_candidate = self._preview_candidate(summary)
        if preview_candidate is not None:
            drafts.append(preview_candidate)

        ranking_candidate = self._ranking_candidate(summary)
        if ranking_candidate is not None:
            drafts.append(ranking_candidate)

        stat_candidate = self._stat_narrative_candidate(summary)
        if stat_candidate is not None:
            drafts.append(stat_candidate)

        return sorted(drafts, key=lambda item: (-item.priority, str(item.content_type), item.source_summary_hash))

    def store_candidates(self, candidates: list[ContentCandidateDraft]) -> IngestStats:
        candidates = EditorialFormatterService(self.session).apply_to_drafts(candidates)
        stats = IngestStats(found=len(candidates))
        for candidate in candidates:
            _, inserted, updated = self.repository.upsert(candidate.model_dump(mode="python"))
            stats.inserted += int(inserted)
            stats.updated += int(updated)
        return stats

    def _summary_hash(self, summary: CompetitionEditorialSummary) -> str:
        payload = summary.model_dump(
            mode="json",
            exclude={"metadata": {"generated_at"}},
        )
        return stable_hash(payload)

    def generate_for_competition(
        self,
        competition_code: str,
        reference_date: date | None = None,
        relevant_only: bool = True,
        results_limit: int = 5,
        upcoming_limit: int = 5,
        news_limit: int = 5,
        standings_limit: int = 5,
    ) -> ContentGenerationResult:
        summary = self.summary_service.build_competition_summary(
            competition_code=competition_code,
            reference_date=reference_date,
            results_limit=results_limit,
            upcoming_limit=upcoming_limit,
            news_limit=news_limit,
            standings_limit=standings_limit,
            relevant_only=relevant_only,
        )
        candidates = self.generate_from_summary(summary)
        stats = self.store_candidates(candidates)
        return ContentGenerationResult(
            competition_slug=summary.metadata.competition_slug,
            competition_name=summary.metadata.competition_name,
            summary_hash=self._summary_hash(summary),
            generated_at=utcnow(),
            candidates=candidates,
            stats=stats,
        )
