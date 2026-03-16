from app.core.catalog import load_competition_catalog
from app.core.enums import CompetitionIntegrationStatus, CompetitionReferenceRole, SourceName, TargetType


def test_competition_catalog_tracks_current_status_and_sources() -> None:
    catalog = load_competition_catalog()

    tercera = catalog["tercera_rfef_g11"]
    assert tercera.status == CompetitionIntegrationStatus.INTEGRATED
    assert tercera.primary_source == "futbolme"
    assert tercera.editorial_name == "3a RFEF Baleares"
    assert tercera.sources[SourceName.FUTBOLME].competition_id == "3065"
    assert (
        tercera.sources[SourceName.FUTBOLME].urls[TargetType.MATCHES]
        == "https://futbolme.com/resultados-directo/torneo/tercera-federacion-grupo-11/3065/calendario"
    )

    preferente = catalog["preferente_mallorca"]
    assert preferente.status == CompetitionIntegrationStatus.MANUAL_ONLY
    assert preferente.sources == {}
    assert any(reference.role == CompetitionReferenceRole.OFFICIAL for reference in preferente.references)

    segunda = catalog["segunda_rfef_g3_baleares"]
    assert segunda.status == CompetitionIntegrationStatus.INTEGRATED
    assert segunda.primary_source == "futbolme"
    assert segunda.tracked_teams == [
        "UD Poblense",
        "Atletico Baleares",
        "CD Ibiza Islas Pitiusas",
        "CE Andratx",
        "UE Porreres",
    ]
    assert (
        segunda.sources[SourceName.FUTBOLME].urls[TargetType.STANDINGS]
        == "https://futbolme.com/resultados-directo/torneo/segunda-federacion-grupo-3/3059/"
    )

    femenina = catalog["tercera_federacion_femenina_g11"]
    assert femenina.editorial_name == "Primera Nacional femenina con equipos baleares"
    assert femenina.status == CompetitionIntegrationStatus.READY_TO_INTEGRATE

    juvenil = catalog["juvenil_division_honor_g3"]
    assert juvenil.status == CompetitionIntegrationStatus.DEFERRED
    assert juvenil.primary_source == "resultados_futbol"
