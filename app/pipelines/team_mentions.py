from __future__ import annotations

import json

import typer
from sqlalchemy import select

from app.db.models import TeamMention
from app.db.session import init_db, session_scope

app = typer.Typer(add_completion=False, help="Gestion minima de menciones de equipos para editorial_formatter.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("list")
def list_mentions(
    competition: str | None = typer.Option(None, "--competition", help="Filtra por competition_slug"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        query = select(TeamMention).order_by(TeamMention.competition_slug.asc(), TeamMention.team_name.asc())
        if competition:
            query = query.where(TeamMention.competition_slug == competition)
        rows = session.execute(query).scalars().all()
        payload = [
            {
                "id": row.id,
                "competition_slug": row.competition_slug,
                "team_name": row.team_name,
                "twitter_handle": row.twitter_handle,
            }
            for row in rows
        ]
        if as_json:
            _dump_json(payload)
        elif not payload:
            typer.echo("sin menciones")
        else:
            for row in payload:
                typer.echo(
                    f"{row['id']:>3} | {row['competition_slug'] or '-'} | "
                    f"{row['team_name']} | {row['twitter_handle']}"
                )


@app.command("upsert")
def upsert_mention(
    team_name: str = typer.Option(..., "--team", help="Nombre del equipo"),
    twitter_handle: str = typer.Option(..., "--handle", help="Handle con o sin @"),
    competition: str | None = typer.Option(None, "--competition", help="competition_slug opcional"),
) -> None:
    init_db()
    handle = twitter_handle.strip()
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"
    with session_scope() as session:
        row = session.execute(
            select(TeamMention).where(
                TeamMention.team_name == team_name,
                TeamMention.competition_slug == competition,
            )
        ).scalars().first()
        if row is None:
            row = TeamMention(
                team_name=team_name,
                twitter_handle=handle,
                competition_slug=competition,
            )
            session.add(row)
            session.flush()
            typer.echo(f"created id={row.id} team={row.team_name} handle={row.twitter_handle}")
            return
        row.twitter_handle = handle
        session.add(row)
        session.flush()
        typer.echo(f"updated id={row.id} team={row.team_name} handle={row.twitter_handle}")


if __name__ == "__main__":
    app()
