from __future__ import annotations

import logging

import typer

from app.db.session import init_db, session_scope
from app.services.top_scorer_service import TopScorerService

logger = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    help="Generacion de tabla de goleadores por competicion.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """CLI de top_scorer."""


@app.command("generate")
def generate(
    competition: str | None = typer.Option(
        None, "--competition", help="Codigo interno de competicion (omitir para todas las integradas)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simular sin persistir cambios"),
) -> None:
    """Genera candidatos TOP_SCORER_UPDATE para una competicion o para todas las integradas."""
    init_db()
    with session_scope() as session:
        service = TopScorerService(session)
        if competition:
            candidate = service.generate(competition, dry_run=dry_run)
            if candidate is None:
                typer.echo(f"No hay suficientes datos de goleadores para: {competition}")
            else:
                typer.echo(f"Candidato generado para {competition} (dry_run={dry_run}):")
                typer.echo(candidate.text_draft)
        else:
            candidates = service.generate_all(dry_run=dry_run)
            typer.echo(f"Candidatos generados: {len(candidates)} (dry_run={dry_run})")
            for candidate in candidates:
                typer.echo(f"  [{candidate.competition_slug}] {candidate.text_draft[:80]!r}")
