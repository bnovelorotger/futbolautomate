from app.services.team_name_normalizer import normalize_team_name


def test_normalize_team_name_replaces_pena_alias() -> None:
    assert normalize_team_name("SCR Pena Deportiva") == "SCR Peña Deportiva"


def test_normalize_team_name_replaces_atletico_alias() -> None:
    assert normalize_team_name("Atletico Baleares") == "Atlético Baleares"


def test_normalize_team_name_keeps_already_correct_name() -> None:
    assert normalize_team_name("UE Alcúdia") == "UE Alcúdia"


def test_normalize_team_name_keeps_unknown_name() -> None:
    assert normalize_team_name("Equipo Desconocido") == "Equipo Desconocido"


def test_normalize_team_name_adds_new_island_aliases() -> None:
    assert normalize_team_name("CCE Sant Lluis") == "CCE Sant Lluís"
    assert normalize_team_name("UD Mahon") == "UD Mahón"
