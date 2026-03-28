from app.schemas.reporting import CompetitionMatchView, StandingView
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
    assert service.has_tracked_teams("primera_rfef_baleares") is True
    assert service.tracked_teams("primera_rfef_baleares") == ["UD Ibiza"]
    assert service.is_tracked_team("primera_rfef_baleares", "Ibiza UD") is True
    assert service.is_tracked_team("primera_rfef_baleares", "AD Ceuta FC") is False


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


def test_competition_relevance_service_filters_standings_and_rankings_to_tracked_teams() -> None:
    service = CompetitionRelevanceService()
    standings = [
        StandingView(position=1, team="UE Sant Andreu", points=51, played=25, wins=15, draws=6, losses=4, goals_for=39, goals_against=20, goal_difference=19),
        StandingView(position=2, team="CD Atlético Baleares", points=48, played=25, wins=14, draws=6, losses=5, goals_for=35, goals_against=18, goal_difference=17),
        StandingView(position=3, team="UD Poblense", points=46, played=25, wins=13, draws=7, losses=5, goals_for=31, goals_against=19, goal_difference=12),
        StandingView(position=4, team="Reus FC Reddis", points=42, played=25, wins=12, draws=6, losses=7, goals_for=30, goals_against=22, goal_difference=8),
        StandingView(position=5, team="UE Porreres", points=41, played=25, wins=11, draws=8, losses=6, goals_for=28, goals_against=24, goal_difference=4),
    ]

    filtered_standings = service.filter_standing_views("segunda_rfef_g3_baleares", standings)
    top_attack = service.top_scoring_teams_from_standings("segunda_rfef_g3_baleares", standings, limit=2)
    top_defense = service.best_defense_teams_from_standings("segunda_rfef_g3_baleares", standings, limit=2)
    top_wins = service.most_wins_teams_from_standings("segunda_rfef_g3_baleares", standings, limit=2)

    assert [row.team for row in filtered_standings] == [
        "CD Atlético Baleares",
        "UD Poblense",
        "UE Porreres",
    ]
    assert [row.team for row in top_attack] == ["CD Atlético Baleares", "UD Poblense"]
    assert [row.team for row in top_defense] == ["CD Atlético Baleares", "UD Poblense"]
    assert [row.team for row in top_wins] == ["CD Atlético Baleares", "UD Poblense"]
