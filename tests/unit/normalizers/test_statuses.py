from app.core.enums import MatchStatus
from app.normalizers.statuses import normalize_match_status


def test_status_normalization_finishes_match() -> None:
    assert normalize_match_status("Finalizado") == MatchStatus.FINISHED


def test_status_normalization_scheduled_match() -> None:
    assert normalize_match_status("Programado") == MatchStatus.SCHEDULED

