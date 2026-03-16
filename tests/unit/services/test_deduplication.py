from app.core.enums import MatchStatus, SourceName
from app.schemas.match import MatchRecord
from app.services.deduplication import match_content_hash
from app.utils.time import utcnow


def test_match_content_hash_changes_when_score_changes() -> None:
    base = MatchRecord(
        source_name=SourceName.FUTBOLME,
        source_url="https://example.com/match/1",
        competition_code="tercera_rfef_g11",
        home_team="CE Andratx",
        away_team="Poblense",
        home_score=1,
        away_score=0,
        status=MatchStatus.FINISHED,
        scraped_at=utcnow(),
    )
    modified = base.model_copy(update={"home_score": 2})

    assert match_content_hash(base, "ce andratx", "poblense") != match_content_hash(
        modified,
        "ce andratx",
        "poblense",
    )
