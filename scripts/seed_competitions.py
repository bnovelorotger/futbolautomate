from __future__ import annotations

from app.core.catalog import load_competition_catalog
from app.db.repositories.competitions import CompetitionRepository
from app.db.session import init_db, session_scope
from app.normalizers.text import normalize_token


def main() -> None:
    init_db()
    catalog = load_competition_catalog()
    with session_scope() as session:
        repo = CompetitionRepository(session)
        for definition in catalog.values():
            source_name = None
            source_mapping = None
            if definition.primary_source:
                for candidate_name, candidate_mapping in definition.sources.items():
                    if str(candidate_name) != definition.primary_source:
                        continue
                    if candidate_mapping.enabled:
                        source_name = candidate_name
                        source_mapping = candidate_mapping
                    break
            if source_name is None:
                for candidate_name, candidate_mapping in definition.sources.items():
                    if candidate_mapping.enabled:
                        source_name = candidate_name
                        source_mapping = candidate_mapping
                        break
            repo.create_or_update(
                code=definition.code,
                name=definition.name,
                normalized_name=normalize_token(definition.name),
                category_level=definition.category_level,
                gender=str(definition.gender),
                region=definition.region,
                country=definition.country,
                federation=definition.federation,
                source_name=str(source_name) if source_name else None,
                source_competition_id=source_mapping.competition_id if source_mapping else None,
            )


if __name__ == "__main__":
    main()
