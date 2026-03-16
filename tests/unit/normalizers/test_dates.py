from app.normalizers.dates import parse_match_datetime


def test_parse_match_datetime_combines_date_and_time() -> None:
    result = parse_match_datetime("14/03/2026", "17:30")

    assert result.match_date.isoformat() == "2026-03-14"
    assert result.match_time.isoformat() == "17:30:00"
    assert result.kickoff_datetime.isoformat() == "2026-03-14T17:30:00+01:00"


def test_parse_match_datetime_accepts_spanish_textual_dates() -> None:
    result = parse_match_datetime("sabado, 14 de marzo de 2026", "16:00")

    assert result.match_date.isoformat() == "2026-03-14"
    assert result.match_time.isoformat() == "16:00:00"
