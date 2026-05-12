from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.db.models import PipelineMetric


class PipelineMetricRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        run_date: date,
        pipeline_name: str,
        **fields,
    ) -> PipelineMetric:
        existing = (
            self._session.query(PipelineMetric)
            .filter_by(run_date=run_date, pipeline_name=pipeline_name)
            .first()
        )
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            return existing
        metric = PipelineMetric(run_date=run_date, pipeline_name=pipeline_name, **fields)
        self._session.add(metric)
        return metric

    def get_recent(self, days: int = 30) -> list[PipelineMetric]:
        from app.utils.time import utcnow
        from datetime import timedelta
        cutoff = (utcnow() - timedelta(days=days)).date()
        return (
            self._session.query(PipelineMetric)
            .filter(PipelineMetric.run_date >= cutoff)
            .order_by(PipelineMetric.run_date.desc())
            .all()
        )
