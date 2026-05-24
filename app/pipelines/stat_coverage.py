from __future__ import annotations

import json
from datetime import date

import typer

from app.core.catalog import load_competition_catalog
from app.core.enums import CompetitionIntegrationStatus
from app.db.session import init_db, session_scope
from app.services.stat_coverage import StatCoverageService

app = typer.Typer(
    add_completion=False,
    help="Informes de cobertura de estadisticas editoriales.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("report")
def report(
    competition_code: str | None = typer.Option(None, "--competition", help="Codigo interno de competicion"),
    season: str | None = typer.Option(None, "--season", help="Temporada a revisar, por ejemplo 2025-26"),
    reference_date_raw: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    reference_date = _parse_reference_date(reference_date_raw)
    with session_scope() as session:
        if competition_code:
            codes = [competition_code]
        else:
            codes = [
                definition.code
                for definition in load_competition_catalog().values()
                if definition.status == CompetitionIntegrationStatus.INTEGRATED
            ]
        service = StatCoverageService(session)
        reports = [
            service.report(code, season=season, reference_date=reference_date).model_dump(mode="json")
            for code in codes
        ]
        if as_json:
            _dump_json(reports)
            return
        for current_report in reports:
            typer.echo(f"{current_report['competition_slug']} season={current_report.get('season') or '-'}")
            for row in current_report["rows"]:
                typer.echo(
                    f"- {row['data_type']}: {row['status']} "
                    f"{row['observed_count']}/{row['expected_count']} "
                    f"ratio={row['coverage_ratio']:.3f}"
                )


def _parse_reference_date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise typer.BadParameter("--date debe tener formato YYYY-MM-DD") from exc


if __name__ == "__main__":
    app()
