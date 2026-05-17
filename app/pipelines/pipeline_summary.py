from __future__ import annotations

import sys
from datetime import date as date_type

import typer

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.services.pipeline_summary_service import PipelineSummaryReport, PipelineSummaryService
from app.services.telegram_notification_service import TelegramNotificationService

app = typer.Typer(
    add_completion=False,
    help="Resumen operativo del pipeline editorial: bloqueos, publicacion y alertas.",
    no_args_is_help=False,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_SEP = "=" * 60
_SEP_THIN = "-" * 60


def _render(report: PipelineSummaryReport) -> str:
    lines: list[str] = []

    lines.append(_SEP)
    lines.append(f"  RESUMEN PIPELINE — {report.reference_date}  (ventana: {report.window_days}d)")
    lines.append(f"  Generado: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(_SEP)

    # ---- Bloqueos --------------------------------------------------------
    lines.append("")
    lines.append("[ BLOQUEOS ]")
    lines.append(_SEP_THIN)
    b = report.blocked
    lines.append(f"  Draft:    {b.draft_count}")
    lines.append(f"  Rejected: {b.rejected_count}")

    if b.rejection_reason_counts:
        lines.append("")
        lines.append("  Motivos de rechazo (top):")
        for reason, count in list(b.rejection_reason_counts.items())[:10]:
            lines.append(f"    {count:>3}x  {reason}")

    if b.quality_error_counts:
        lines.append("")
        lines.append("  Errores de quality check (top):")
        for err, count in list(b.quality_error_counts.items())[:10]:
            lines.append(f"    {count:>3}x  {err}")

    if b.by_content_type:
        lines.append("")
        lines.append("  Por tipo de contenido:")
        for ct, count in b.by_content_type.items():
            lines.append(f"    {count:>3}x  {ct}")

    if b.by_competition:
        lines.append("")
        lines.append("  Por competicion:")
        for slug, count in b.by_competition.items():
            lines.append(f"    {count:>3}x  {slug}")

    # ---- Publicacion -----------------------------------------------------
    lines.append("")
    lines.append(f"[ PUBLICACION — ultimas {report.publication.window_hours}h ]")
    lines.append(_SEP_THIN)
    p = report.publication
    lines.append(f"  Publicados en X:          {p.published_to_x}")
    lines.append(f"  Omitidos (antigüedad):    {p.skipped_stale}")
    lines.append(f"  Con error de publicacion: {p.publication_errors}")
    lines.append(f"  Pendientes de despachar:  {p.pending_dispatch}")

    if p.error_entries:
        lines.append("")
        lines.append("  Candidatos con error:")
        for e in p.error_entries[:10]:
            err_txt = (e.external_publication_error or "")[:80]
            lines.append(f"    ID {e.id:>5}  {e.content_type:<30} {e.competition_slug}")
            lines.append(f"           Error: {err_txt}")

    if p.pending_entries:
        lines.append("")
        lines.append("  Candidatos pendientes:")
        for e in p.pending_entries[:10]:
            pub_str = e.published_at.strftime("%Y-%m-%d %H:%M UTC") if e.published_at else "-"
            lines.append(f"    ID {e.id:>5}  {e.content_type:<30} {e.competition_slug}  published_at={pub_str}")

    # ---- Alertas ---------------------------------------------------------
    lines.append("")
    lines.append("[ ALERTAS ]")
    lines.append(_SEP_THIN)
    if report.alerts:
        for alert in report.alerts:
            lines.append(f"  [{alert.level}] {alert.code}: {alert.message}")
    else:
        lines.append("  Sin alertas activas.")

    lines.append(_SEP)
    return "\n".join(lines)


def _build_telegram_alert(report: PipelineSummaryReport) -> str:
    lines = ["⚠️ <b>futbolbalear — alertas activas</b>", ""]
    b = report.blocked
    p = report.publication
    total_blocked = b.draft_count + b.rejected_count
    rejection_pct = 0
    total = total_blocked + p.published_to_x
    if total > 0:
        rejection_pct = round(b.rejected_count * 100 / total)
    lines.append(f"• Candidatos bloqueados: {total_blocked}")
    lines.append(f"• Tasa de rechazo: {rejection_pct}%")
    lines.append(f"• Errores de sesión X: {p.publication_errors}")
    lines.append("")
    lines.append("Revisar: <code>logs\\cron_summary.log</code>")
    return "\n".join(lines)


@app.callback(invoke_without_command=True)
def run(
    date_str: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD (default: hoy)"),
    days: int = typer.Option(2, "--days", help="Ventana de dias a analizar (default: 2)"),
    rejection_threshold: int = typer.Option(
        5, "--rejection-threshold", help="Umbral de rechazos para alerta (default: 5)"
    ),
) -> None:
    """Resumen operativo del pipeline: bloqueos, publicacion y alertas.

    Sale con exit code 1 si hay alertas activas (util para scripting).
    """
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()

    parsed_date = date_type.fromisoformat(date_str) if date_str else None

    with session_scope() as session:
        report = PipelineSummaryService(
            session,
            rejection_alert_threshold=rejection_threshold,
        ).summary(reference_date=parsed_date, window_days=days)

    typer.echo(_render(report))

    if report.has_alerts:
        tg = TelegramNotificationService(settings=settings)
        if tg.is_configured():
            tg.send_message(_build_telegram_alert(report))
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
