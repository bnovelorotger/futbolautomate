from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select

from app.core.enums import DataCoverageStatus, DataCoverageType
from app.db.models import MatchDataCoverage
from app.db.repositories.base import BaseRepository
from app.utils.time import utcnow


class MatchDataCoverageRepository(BaseRepository[MatchDataCoverage]):
    def get_for_match(
        self,
        match_id: int,
        data_type: DataCoverageType | str,
    ) -> MatchDataCoverage | None:
        return self.session.scalar(
            select(MatchDataCoverage).where(
                MatchDataCoverage.match_id == match_id,
                MatchDataCoverage.data_type == str(data_type),
            )
        )

    def upsert_for_match(
        self,
        *,
        match_id: int,
        data_type: DataCoverageType | str,
        status: DataCoverageStatus | str,
        source_name: str | None = None,
        expected_count: int | None = None,
        observed_count: int | None = None,
        checked_at: datetime | None = None,
        details_json: dict | None = None,
    ) -> MatchDataCoverage:
        row = self.get_for_match(match_id, data_type)
        if row is None:
            row = MatchDataCoverage(
                match_id=match_id,
                data_type=str(data_type),
                status=str(status),
                source_name=source_name,
                expected_count=expected_count,
                observed_count=observed_count,
                checked_at=checked_at or utcnow(),
                details_json=details_json or {},
            )
            self.session.add(row)
            self.session.flush()
            return row

        row.status = str(status)
        row.source_name = source_name
        row.expected_count = expected_count
        row.observed_count = observed_count
        row.checked_at = checked_at or utcnow()
        row.details_json = details_json or {}
        self.session.add(row)
        self.session.flush()
        return row

    def list_for_matches(
        self,
        match_ids: Iterable[int],
        *,
        data_type: DataCoverageType | str | None = None,
    ) -> list[MatchDataCoverage]:
        ids = list(match_ids)
        if not ids:
            return []
        query = select(MatchDataCoverage).where(MatchDataCoverage.match_id.in_(ids))
        if data_type is not None:
            query = query.where(MatchDataCoverage.data_type == str(data_type))
        return self.session.scalars(
            query.order_by(MatchDataCoverage.match_id.asc(), MatchDataCoverage.data_type.asc())
        ).all()
