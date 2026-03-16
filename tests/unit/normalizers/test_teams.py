from app.normalizers.teams import TeamNameNormalizer


def test_team_alias_normalization_maps_common_aliases() -> None:
    normalizer = TeamNameNormalizer()

    result = normalizer.normalize("At. Baleares")
    assert result.canonical == "Atletico Baleares"
    assert result.normalized == "atletico baleares"


def test_team_alias_normalization_handles_accents() -> None:
    normalizer = TeamNameNormalizer()

    result = normalizer.normalize("SCR Peña Deportiva")
    assert result.canonical == "SCR Pena Deportiva"
    assert result.normalized == "scr pena deportiva"

