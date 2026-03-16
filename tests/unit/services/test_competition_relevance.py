from app.schemas.reporting import CompetitionMatchView
from app.services.competition_relevance import CompetitionRelevanceService


def test_competition_relevance_service_resolves_tracked_teams_and_aliases() -> None:
    service = CompetitionRelevanceService()

    assert service.has_tracked_teams("segunda_rfef_g3_baleares") is True
    assert service.tracked_teams("segunda_rfef_g3_baleares") == [
        "UD Poblense",
        "Atletico Baleares",
        "CD Ibiza Islas Pitiusas",
        "CE Andratx",
        "UE Porreres",
    ]
    assert service.is_tracked_team("segunda_rfef_g3_baleares", "CD Atlético Baleares") is True
    assert service.is_tracked_team("segunda_rfef_g3_baleares", "UE Sant Andreu") is False


def test_competition_relevance_service_filters_only_matches_with_tracked_teams() -> None:
    service = CompetitionRelevanceService()
    rows = [
        CompetitionMatchView(
            home_team="UE Sant Andreu",
            away_team="Reus FC Reddis",
            status="finished",
            source_url="https://example.com/1",
        ),
        CompetitionMatchView(
            home_team="UD Poblense",
            away_team="UE Sant Andreu",
            status="finished",
            source_url="https://example.com/2",
        ),
        CompetitionMatchView(
            home_team="CD Atlético Baleares",
            away_team="Reus FC Reddis",
            status="scheduled",
            source_url="https://example.com/3",
        ),
    ]

    filtered = service.filter_match_views("segunda_rfef_g3_baleares", rows)

    assert [row.source_url for row in filtered] == [
        "https://example.com/2",
        "https://example.com/3",
    ]
