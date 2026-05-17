from __future__ import annotations

import importlib
import inspect
import sys
from datetime import date as date_type

import typer

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.services.telegram_event_notifier import TelegramEventNotifier
from app.services.telegram_notification_service import TelegramNotificationService
from app.utils.time import utcnow

app = typer.Typer(
    add_completion=False,
    help="Agenda editorial del dia para consola y envio opcional a Telegram.",
    no_args_is_help=False,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _load_plan_service_class():
    last_error: Exception | None = None
    for module_name in (
        "app.services.editorial_day_plan",
        "app.services.editorial_day_plan_service",
    ):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
            last_error = exc
            continue
        service_class = getattr(module, "EditorialDayPlanService", None)
        if service_class is not None:
            return service_class
    if last_error is not None:
        raise RuntimeError("EditorialDayPlanService no esta disponible en el entorno actual") from last_error
    raise RuntimeError("No se encontro EditorialDayPlanService")


def _invoke_supported(callable_obj, **kwargs):
    signature = inspect.signature(callable_obj)
    supported_kwargs = {
        key: value for key, value in kwargs.items() if value is not None and key in signature.parameters
    }
    return callable_obj(**supported_kwargs)


def _build_plan_service(settings: Settings, session):
    service_class = _load_plan_service_class()
    return _invoke_supported(service_class, session=session, settings=settings)


def _start_task_notification(task_name: str, *, mode: str, summary_metrics: dict[str, object] | None = None):
    notifier = TelegramEventNotifier()
    started_at = utcnow()
    if notifier.is_configured():
        notifier.task_started(
            task_name=task_name,
            mode=mode,
            started_at=started_at,
            summary_metrics=summary_metrics,
        )
    return notifier, started_at


def _finish_task_notification(
    notifier: TelegramEventNotifier,
    task_name: str,
    *,
    mode: str,
    started_at,
    status: str = "ok",
    summary_metrics: dict[str, object] | None = None,
) -> None:
    if not notifier.is_configured():
        return
    notifier.task_finished(
        task_name=task_name,
        mode=mode,
        started_at=started_at,
        duration_seconds=(utcnow() - started_at).total_seconds(),
        status=status,
        summary_metrics=summary_metrics,
    )


def _fail_task_notification(
    notifier: TelegramEventNotifier,
    task_name: str,
    *,
    mode: str,
    started_at,
    error_message: str,
    summary_metrics: dict[str, object] | None = None,
) -> None:
    if not notifier.is_configured():
        return
    notifier.task_failed(
        task_name=task_name,
        mode=mode,
        started_at=started_at,
        duration_seconds=(utcnow() - started_at).total_seconds(),
        error_message=error_message[:200],
        summary_metrics=summary_metrics,
    )


@app.callback(invoke_without_command=True)
def run(
    date_str: str | None = typer.Option(None, "--date", help="Fecha objetivo YYYY-MM-DD (default: hoy)"),
    send_telegram: bool = typer.Option(False, "--send-telegram", help="Enviar la agenda renderizada a Telegram"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No enviar mensajes externos; solo previsualizar"),
) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()

    parsed_date = date_type.fromisoformat(date_str) if date_str else None
    mode = "dry_run" if dry_run else "live"
    notifier, started_at = _start_task_notification(
        "editorial_day_plan",
        mode=mode,
        summary_metrics={
            "send_telegram": send_telegram,
            "target_date": parsed_date.isoformat() if parsed_date else None,
        },
    )

    try:
        with session_scope() as session:
            plan_service = _build_plan_service(settings, session)
            report = _invoke_supported(
                plan_service.build_report,
                target_date=parsed_date,
                reference_date=parsed_date,
                date=parsed_date,
            )
            console_output = plan_service.render_console(report)
            telegram_output = plan_service.render_telegram(report)

        typer.echo(console_output)

        telegram_sent = False
        if send_telegram:
            telegram_service = TelegramNotificationService(settings=settings)
            if dry_run:
                typer.echo("")
                typer.echo("[dry-run] Preview Telegram:")
                typer.echo(telegram_output)
            elif telegram_service.is_configured():
                telegram_sent = telegram_service.send_message(telegram_output)
                if not telegram_sent:
                    typer.echo("No se pudo enviar la agenda editorial a Telegram.", err=True)
            else:
                typer.echo("Telegram no configurado; agenda no enviada.", err=True)

        _finish_task_notification(
            notifier,
            "editorial_day_plan",
            mode=mode,
            started_at=started_at,
            summary_metrics={
                "send_telegram": send_telegram,
                "target_date": parsed_date.isoformat() if parsed_date else None,
                "telegram_sent": telegram_sent,
            },
        )
    except Exception as exc:
        _fail_task_notification(
            notifier,
            "editorial_day_plan",
            mode=mode,
            started_at=started_at,
            error_message=str(exc),
            summary_metrics={
                "send_telegram": send_telegram,
                "target_date": parsed_date.isoformat() if parsed_date else None,
            },
        )
        raise


if __name__ == "__main__":
    app()
