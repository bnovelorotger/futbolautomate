from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentType, StandingsEventType
from app.core.exceptions import ConfigurationError
from app.core.standings_zones import CompetitionStandingsZones, load_standings_zones
from app.db.models import Competition
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.standings_events import (
    StandingsEventCandidatePayload,
    StandingsEventsGenerationResult,
    StandingsEventsResult,
    StandingsEventView,
)
from app.services.standings_history import (
    HistoricalStandingsSnapshot,
    SnapshotStandingRow,
    StandingsHistoryService,
)
from app.utils.hashing import stable_hash
from app.utils.time import utcnow

_EVENT_PRIORITY = {
    StandingsEventType.NEW_LEADER: 79,
    StandingsEventType.ENTERED_PLAYOFF: 76,
    StandingsEventType.LEFT_PLAYOFF: 75,
    StandingsEventType.ENTERED_RELEGATION: 76,
    StandingsEventType.LEFT_RELEGATION: 75,
    StandingsEventType.BIGGEST_POSITION_RISE: 73,
    StandingsEventType.BIGGEST_POSITION_DROP: 72,
}


def _ordinal(position: int | None) -> str:
    if position is None:
        return "-"
    return f"{position}º"


def _content_hash(
    competition_slug: str,
    event_type: StandingsEventType,
    team: str,
    current_snapshot_timestamp: datetime,
    previous_snapshot_timestamp: datetime | None,
) -> str:
    return stable_hash(
        {
            "competition_slug": competition_slug,
            "content_type": str(ContentType.STANDINGS_EVENT),
            "event_type": str(event_type),
            "team": team,
            "current_snapshot_timestamp": current_snapshot_timestamp.isoformat(),
            "previous_snapshot_timestamp": (
                previous_snapshot_timestamp.isoformat()
                if previous_snapshot_timestamp is not None
                else None
            ),
        }
    )


class StandingsEventsService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        history_service: StandingsHistoryService | None = None,
        zones: dict[str, CompetitionStandingsZones] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.history = history_service or StandingsHistoryService(session)
        self.repository = ContentCandidateRepository(session)
        self.catalog = load_competition_catalog()
        self.zones = zones or load_standings_zones()

    def preview_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> StandingsEventsResult:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        current_snapshot, previous_snapshot = self.history.latest_snapshot_pair(competition_code)
        zone_config = self.zones.get(competition_code, CompetitionStandingsZones())
        events = self._detect_events(current_snapshot, previous_snapshot, zone_config)
        return StandingsEventsResult(
            competition_slug=competition_code,
            competition_name=self._competition_name(competition),
            reference_date=selected_date,
            generated_at=utcnow(),
            current_snapshot_timestamp=current_snapshot.snapshot_timestamp,
            previous_snapshot_timestamp=(
                previous_snapshot.snapshot_timestamp if previous_snapshot is not None else None
            ),
            playoff_positions=list(zone_config.playoff_positions),
            relegation_positions=list(zone_config.relegation_positions),
            rows=events,
        )

    def generate_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> StandingsEventsGenerationResult:
        preview = self.preview_for_competition(competition_code, reference_date=reference_date)
        candidates = self.build_candidate_drafts(competition_code, reference_date=preview.reference_date)
        stats = self.store_candidates(candidates)
        return StandingsEventsGenerationResult(
            competition_slug=preview.competition_slug,
            competition_name=preview.competition_name,
            reference_date=preview.reference_date,
            generated_at=preview.generated_at,
            current_snapshot_timestamp=preview.current_snapshot_timestamp,
            previous_snapshot_timestamp=preview.previous_snapshot_timestamp,
            playoff_positions=preview.playoff_positions,
            relegation_positions=preview.relegation_positions,
            rows=preview.rows,
            stats=stats,
        )

    def build_candidate_drafts(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> list[ContentCandidateDraft]:
        preview = self.preview_for_competition(competition_code, reference_date=reference_date)
        candidates: list[ContentCandidateDraft] = []
        for event in preview.rows:
            payload_json = {
                "content_key": f"{event.event_type}:{event.team}",
                "template_name": f"standings_event_{event.event_type}_v1",
                "competition_name": preview.competition_name,
                "reference_date": preview.reference_date.isoformat(),
                "source_payload": {
                    "event_type": str(event.event_type),
                    "title": event.title,
                    "team": event.team,
                    "teams": [event.team],
                    "previous_position": event.previous_position,
                    "current_position": event.current_position,
                    "position_delta": event.position_delta,
                    "current_snapshot_timestamp": (
                        preview.current_snapshot_timestamp.isoformat()
                        if preview.current_snapshot_timestamp is not None
                        else None
                    ),
                    "previous_snapshot_timestamp": (
                        preview.previous_snapshot_timestamp.isoformat()
                        if preview.previous_snapshot_timestamp is not None
                        else None
                    ),
                    "playoff_positions": list(preview.playoff_positions),
                    "relegation_positions": list(preview.relegation_positions),
                },
            }
            candidates.append(
                ContentCandidateDraft(
                    competition_slug=preview.competition_slug,
                    content_type=ContentType.STANDINGS_EVENT,
                    priority=event.priority,
                    text_draft=event.text_draft,
                    payload_json=payload_json,
                    source_summary_hash=event.source_summary_hash,
                )
            )
        return candidates

    def store_candidates(self, candidates: list[ContentCandidateDraft]) -> IngestStats:
        stats = IngestStats(found=len(candidates))
        for candidate in candidates:
            _, inserted, updated = self.repository.upsert(candidate.model_dump(mode="python"))
            stats.inserted += int(inserted)
            stats.updated += int(updated)
        return stats

    def _detect_events(
        self,
        current_snapshot: HistoricalStandingsSnapshot,
        previous_snapshot: HistoricalStandingsSnapshot | None,
        zone_config: CompetitionStandingsZones,
    ) -> list[StandingsEventView]:
        if previous_snapshot is None:
            return []

        events: list[StandingsEventView] = []
        previous_map = {row.team_key: row for row in previous_snapshot.rows}

        current_leader = next((row for row in current_snapshot.rows if row.position == 1), None)
        previous_leader = next((row for row in previous_snapshot.rows if row.position == 1), None)
        if (
            current_leader is not None
            and previous_leader is not None
            and current_leader.team_key != previous_leader.team_key
        ):
            events.append(
                self._event_view(
                    competition_slug=current_snapshot.competition_slug,
                    competition_name=current_snapshot.competition_name,
                    event_type=StandingsEventType.NEW_LEADER,
                    team=current_leader.team,
                    previous_position=previous_map.get(current_leader.team_key).position
                    if previous_map.get(current_leader.team_key) is not None
                    else None,
                    current_position=current_leader.position,
                    current_snapshot_timestamp=current_snapshot.snapshot_timestamp,
                    previous_snapshot_timestamp=previous_snapshot.snapshot_timestamp,
                )
            )

        playoff_positions = set(zone_config.playoff_positions)
        relegation_positions = set(zone_config.relegation_positions)
        for current_row in current_snapshot.rows:
            previous_row = previous_map.get(current_row.team_key)
            if previous_row is None:
                continue
            previous_in_playoff = previous_row.position in playoff_positions
            current_in_playoff = current_row.position in playoff_positions
            previous_in_relegation = previous_row.position in relegation_positions
            current_in_relegation = current_row.position in relegation_positions

            if (
                playoff_positions
                and current_in_playoff
                and not previous_in_playoff
                and previous_row.position != 1
            ):
                events.append(
                    self._event_view(
                        competition_slug=current_snapshot.competition_slug,
                        competition_name=current_snapshot.competition_name,
                        event_type=StandingsEventType.ENTERED_PLAYOFF,
                        team=current_row.team,
                        previous_position=previous_row.position,
                        current_position=current_row.position,
                        current_snapshot_timestamp=current_snapshot.snapshot_timestamp,
                        previous_snapshot_timestamp=previous_snapshot.snapshot_timestamp,
                    )
                )
            if (
                playoff_positions
                and previous_in_playoff
                and not current_in_playoff
                and current_row.position != 1
            ):
                events.append(
                    self._event_view(
                        competition_slug=current_snapshot.competition_slug,
                        competition_name=current_snapshot.competition_name,
                        event_type=StandingsEventType.LEFT_PLAYOFF,
                        team=current_row.team,
                        previous_position=previous_row.position,
                        current_position=current_row.position,
                        current_snapshot_timestamp=current_snapshot.snapshot_timestamp,
                        previous_snapshot_timestamp=previous_snapshot.snapshot_timestamp,
                    )
                )
            if relegation_positions and current_in_relegation and not previous_in_relegation:
                events.append(
                    self._event_view(
                        competition_slug=current_snapshot.competition_slug,
                        competition_name=current_snapshot.competition_name,
                        event_type=StandingsEventType.ENTERED_RELEGATION,
                        team=current_row.team,
                        previous_position=previous_row.position,
                        current_position=current_row.position,
                        current_snapshot_timestamp=current_snapshot.snapshot_timestamp,
                        previous_snapshot_timestamp=previous_snapshot.snapshot_timestamp,
                    )
                )
            if relegation_positions and previous_in_relegation and not current_in_relegation:
                events.append(
                    self._event_view(
                        competition_slug=current_snapshot.competition_slug,
                        competition_name=current_snapshot.competition_name,
                        event_type=StandingsEventType.LEFT_RELEGATION,
                        team=current_row.team,
                        previous_position=previous_row.position,
                        current_position=current_row.position,
                        current_snapshot_timestamp=current_snapshot.snapshot_timestamp,
                        previous_snapshot_timestamp=previous_snapshot.snapshot_timestamp,
                    )
                )

        biggest_rise = self._biggest_position_change(
            current_rows=current_snapshot.rows,
            previous_map=previous_map,
            rising=True,
        )
        if biggest_rise is not None:
            current_row, previous_row = biggest_rise
            events.append(
                self._event_view(
                    competition_slug=current_snapshot.competition_slug,
                    competition_name=current_snapshot.competition_name,
                    event_type=StandingsEventType.BIGGEST_POSITION_RISE,
                    team=current_row.team,
                    previous_position=previous_row.position,
                    current_position=current_row.position,
                    current_snapshot_timestamp=current_snapshot.snapshot_timestamp,
                    previous_snapshot_timestamp=previous_snapshot.snapshot_timestamp,
                )
            )

        biggest_drop = self._biggest_position_change(
            current_rows=current_snapshot.rows,
            previous_map=previous_map,
            rising=False,
        )
        if biggest_drop is not None:
            current_row, previous_row = biggest_drop
            events.append(
                self._event_view(
                    competition_slug=current_snapshot.competition_slug,
                    competition_name=current_snapshot.competition_name,
                    event_type=StandingsEventType.BIGGEST_POSITION_DROP,
                    team=current_row.team,
                    previous_position=previous_row.position,
                    current_position=current_row.position,
                    current_snapshot_timestamp=current_snapshot.snapshot_timestamp,
                    previous_snapshot_timestamp=previous_snapshot.snapshot_timestamp,
                )
            )

        return sorted(
            events,
            key=lambda item: (-item.priority, item.current_position or 999, item.team),
        )

    def _biggest_position_change(
        self,
        *,
        current_rows: list[SnapshotStandingRow],
        previous_map: dict[str, SnapshotStandingRow],
        rising: bool,
    ) -> tuple[SnapshotStandingRow, SnapshotStandingRow] | None:
        best: tuple[int, SnapshotStandingRow, SnapshotStandingRow] | None = None
        for current_row in current_rows:
            previous_row = previous_map.get(current_row.team_key)
            if previous_row is None:
                continue
            if rising:
                delta = previous_row.position - current_row.position
            else:
                delta = current_row.position - previous_row.position
            if delta <= 0:
                continue
            candidate = (delta, current_row, previous_row)
            if best is None:
                best = candidate
                continue
            best_delta, best_current, _ = best
            if delta > best_delta:
                best = candidate
                continue
            if delta == best_delta:
                if current_row.position < best_current.position:
                    best = candidate
                elif current_row.position == best_current.position and current_row.team < best_current.team:
                    best = candidate
        if best is None:
            return None
        return best[1], best[2]

    def _event_view(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        event_type: StandingsEventType,
        team: str,
        previous_position: int | None,
        current_position: int | None,
        current_snapshot_timestamp: datetime,
        previous_snapshot_timestamp: datetime | None,
    ) -> StandingsEventView:
        payload = StandingsEventCandidatePayload(
            competition_slug=competition_slug,
            event_type=event_type,
            title=self._title(event_type, competition_name, team),
            team=team,
            previous_position=previous_position,
            current_position=current_position,
            position_delta=(
                previous_position - current_position
                if previous_position is not None and current_position is not None
                else None
            ),
        )
        return StandingsEventView(
            competition_slug=competition_slug,
            competition_name=competition_name,
            event_type=event_type,
            team=team,
            previous_position=previous_position,
            current_position=current_position,
            position_delta=payload.position_delta,
            priority=_EVENT_PRIORITY[event_type],
            title=payload.title,
            text_draft=self._text_draft(payload, competition_name),
            source_summary_hash=_content_hash(
                competition_slug,
                event_type,
                team,
                current_snapshot_timestamp,
                previous_snapshot_timestamp,
            ),
        )

    def _title(
        self,
        event_type: StandingsEventType,
        competition_name: str,
        team: str,
    ) -> str:
        mapping = {
            StandingsEventType.NEW_LEADER: f"Nuevo lider en {competition_name}",
            StandingsEventType.ENTERED_PLAYOFF: f"{team} entra en playoff",
            StandingsEventType.LEFT_PLAYOFF: f"{team} sale del playoff",
            StandingsEventType.ENTERED_RELEGATION: f"{team} entra en descenso",
            StandingsEventType.LEFT_RELEGATION: f"{team} sale del descenso",
            StandingsEventType.BIGGEST_POSITION_RISE: f"La mayor subida es de {team}",
            StandingsEventType.BIGGEST_POSITION_DROP: f"La mayor caida es de {team}",
        }
        return mapping[event_type]

    def _text_draft(
        self,
        payload: StandingsEventCandidatePayload,
        competition_name: str,
    ) -> str:
        team = payload.team
        previous_position = _ordinal(payload.previous_position)
        current_position = _ordinal(payload.current_position)
        if payload.event_type == StandingsEventType.NEW_LEADER:
            return (
                f"Nuevo lider en {competition_name}: {team} pasa del {previous_position} al 1º."
            )
        if payload.event_type == StandingsEventType.ENTERED_PLAYOFF:
            return (
                f"{team} entra en puestos de playoff en {competition_name} tras subir "
                f"del {previous_position} al {current_position}."
            )
        if payload.event_type == StandingsEventType.LEFT_PLAYOFF:
            return (
                f"{team} sale de los puestos de playoff en {competition_name} y cae "
                f"del {previous_position} al {current_position}."
            )
        if payload.event_type == StandingsEventType.ENTERED_RELEGATION:
            return (
                f"{team} cae a puestos de descenso en {competition_name} tras bajar "
                f"del {previous_position} al {current_position}."
            )
        if payload.event_type == StandingsEventType.LEFT_RELEGATION:
            return (
                f"{team} sale del descenso en {competition_name} y sube "
                f"del {previous_position} al {current_position}."
            )
        if payload.event_type == StandingsEventType.BIGGEST_POSITION_RISE:
            return (
                f"La mayor subida de la jornada en {competition_name} la firma {team}: "
                f"del {previous_position} al {current_position}."
            )
        return (
            f"La mayor caida de la jornada en {competition_name} la firma {team}: "
            f"del {previous_position} al {current_position}."
        )

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(
            select(Competition).where(Competition.code == competition_code)
        )
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _competition_name(self, competition: Competition) -> str:
        definition = self.catalog.get(competition.code)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        return competition.name

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.settings.timezone)).date()
