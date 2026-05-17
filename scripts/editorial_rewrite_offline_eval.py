from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import ContentCandidate
from app.services.editorial_quality_checks import EditorialQualityChecksService
from tests.unit.services.service_test_support import build_export_policy, build_session, build_settings
from tests.unit.services.test_editorial_narratives import seed_narratives_data

FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "editorial_rewrite_eval_samples.json"
VARIANT_ORDER = ("draft", "current_rewrite", "humanized_local")
PHASE3_CONTENT_TYPES = {"preview", "viral_story"}
PHASE4_CONTENT_TYPES = {"race_narrative", "milestone_story"}
HANDLE_PATTERN = re.compile(r"(?<!\w)@[A-Za-z0-9_]{1,15}")
HASHTAG_PATTERN = re.compile(r"(?<!\w)#[A-Za-z0-9_]+")


def load_samples(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise ValueError(f"Fixture invalido en {path}: falta la lista 'samples'")
    return samples


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _token_set(pattern: re.Pattern[str], text: str) -> set[str]:
    return {token.lower() for token in pattern.findall(text)}


def _selected_text(sample: dict[str, Any], variant: str) -> str:
    if variant == "draft":
        return str(sample["draft_text"])
    return str(sample["variants"][variant])


def _preservation(sample: dict[str, Any], selected_text: str) -> dict[str, Any]:
    normalized_text = _normalize(selected_text)
    expected_data_points = [str(value) for value in sample.get("expected_data_points", [])]
    expected_handles = {str(value).lower() for value in sample.get("expected_handles", [])}
    expected_hashtags = {str(value).lower() for value in sample.get("expected_hashtags", [])}

    preserved_data = [point for point in expected_data_points if _normalize(point) in normalized_text]
    found_handles = _token_set(HANDLE_PATTERN, selected_text)
    found_hashtags = _token_set(HASHTAG_PATTERN, selected_text)

    return {
        "data_points_total": len(expected_data_points),
        "data_points_preserved": len(preserved_data),
        "data_preservation_rate": (
            len(preserved_data) / len(expected_data_points) if expected_data_points else 1.0
        ),
        "missing_data_points": [point for point in expected_data_points if point not in preserved_data],
        "handles_exact_match": found_handles == expected_handles,
        "missing_handles": sorted(expected_handles - found_handles),
        "extra_handles": sorted(found_handles - expected_handles),
        "hashtags_exact_match": found_hashtags == expected_hashtags,
        "missing_hashtags": sorted(expected_hashtags - found_hashtags),
        "extra_hashtags": sorted(found_hashtags - expected_hashtags),
    }


def _seed_candidates(samples: list[dict[str, Any]]) -> tuple[Any, dict[str, int]]:
    session = build_session()
    seed_narratives_data(session)
    base_timestamp = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    sample_id_map: dict[str, int] = {}
    for index, sample in enumerate(samples, start=1):
        created_at = base_timestamp + timedelta(days=(index - 1) * 4)
        status = str(sample["status"])
        candidate = ContentCandidate(
            id=index,
            competition_slug=str(sample["competition_slug"]),
            content_type=str(sample["content_type"]),
            priority=int(sample["priority"]),
            text_draft=str(sample["draft_text"]),
            formatted_text=str(sample["draft_text"]),
            payload_json=dict(sample["payload_json"]),
            source_summary_hash=str(sample["id"]),
            scheduled_at=created_at,
            status=status,
            rewritten_text=None,
            rewrite_status=None,
            rewrite_model=None,
            rewrite_timestamp=None,
            rewrite_error=None,
            reviewed_at=created_at if status == "published" else None,
            approved_at=created_at if status == "published" else None,
            published_at=created_at if status == "published" else None,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(candidate)
        sample_id_map[str(sample["id"])] = index
    session.commit()
    return session, sample_id_map


def build_report(samples: list[dict[str, Any]]) -> dict[str, Any]:
    session, sample_id_map = _seed_candidates(samples)
    try:
        service = EditorialQualityChecksService(
            session,
            settings=build_settings(),
            policy=build_export_policy(),
        )
        rows: list[dict[str, Any]] = []
        for sample in samples:
            candidate_id = sample_id_map[str(sample["id"])]
            candidate = session.get(ContentCandidate, candidate_id)
            if candidate is None:
                raise ValueError(f"No se pudo cargar el candidato para {sample['id']}")
            for variant in VARIANT_ORDER:
                selected_text = _selected_text(sample, variant)
                candidate.rewritten_text = None if variant == "draft" else selected_text
                candidate.updated_at = candidate.created_at
                session.add(candidate)
                session.flush()

                prefer_rewrite = variant != "draft"
                if bool(sample.get("approval_precheck", False)):
                    batch = service.check_candidates(
                        [candidate.id],
                        dry_run=True,
                        prefer_rewrite=prefer_rewrite,
                        require_published=False,
                    )
                    qc_errors = list(batch.rows[0].errors)
                    qc_warnings = list(batch.rows[0].warnings)
                else:
                    result = service.check_candidate(
                        candidate.id,
                        dry_run=True,
                        prefer_rewrite=prefer_rewrite,
                    )
                    qc_errors = list(result.candidate.errors)
                    qc_warnings = list(result.candidate.warnings)

                preservation = _preservation(sample, selected_text)
                rows.append(
                    {
                        "sample_id": sample["id"],
                        "group": sample["group"],
                        "content_type": sample["content_type"],
                        "variant": variant,
                        "approval_precheck": bool(sample.get("approval_precheck", False)),
                        "length": len(selected_text),
                        "qc_passed": not qc_errors,
                        "qc_errors": qc_errors,
                        "qc_warnings": qc_warnings,
                        "selected_text": selected_text,
                        **preservation,
                    }
                )

        return {
            "fixture_path": str(FIXTURE_PATH),
            "sample_count": len(samples),
            "variants": list(VARIANT_ORDER),
            "groups": _aggregate_rows(rows, by="group"),
            "content_types": _aggregate_rows(rows, by="content_type"),
            "phase3_rollout": _aggregate_by_variant(
                [row for row in rows if row["content_type"] in PHASE3_CONTENT_TYPES],
            ),
            "phase4_candidates": _aggregate_by_variant(
                [row for row in rows if row["content_type"] in PHASE4_CONTENT_TYPES],
            ),
            "rows": rows,
        }
    finally:
        session.close()


def _aggregate_rows(rows: list[dict[str, Any]], *, by: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[by])].append(row)

    report: dict[str, Any] = {}
    for key, bucket in sorted(grouped.items()):
        per_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in bucket:
            per_variant[row["variant"]].append(row)

        report[key] = {
            variant: _summarize_bucket(per_variant.get(variant, []))
            for variant in VARIANT_ORDER
            if per_variant.get(variant)
        }
    return report


def _aggregate_by_variant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["variant"]].append(row)
    return {variant: _summarize_bucket(grouped[variant]) for variant in VARIANT_ORDER if grouped.get(variant)}


def _summarize_bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sample_count = len(rows)
    qc_failed = [row for row in rows if not row["qc_passed"]]
    relevant_diffs = [
        {
            "sample_id": row["sample_id"],
            "qc_errors": row["qc_errors"],
            "missing_data_points": row["missing_data_points"],
            "missing_handles": row["missing_handles"],
            "extra_handles": row["extra_handles"],
            "missing_hashtags": row["missing_hashtags"],
            "extra_hashtags": row["extra_hashtags"],
        }
        for row in rows
        if row["qc_errors"]
        or row["missing_data_points"]
        or row["missing_handles"]
        or row["extra_handles"]
        or row["missing_hashtags"]
        or row["extra_hashtags"]
    ]
    return {
        "sample_count": sample_count,
        "qc_failed_count": len(qc_failed),
        "qc_fail_rate": (len(qc_failed) / sample_count) if sample_count else 0.0,
        "average_length": (sum(row["length"] for row in rows) / sample_count) if sample_count else 0.0,
        "average_data_preservation_rate": (
            sum(row["data_preservation_rate"] for row in rows) / sample_count if sample_count else 0.0
        ),
        "handle_exact_match_rate": (
            sum(1 for row in rows if row["handles_exact_match"]) / sample_count if sample_count else 0.0
        ),
        "hashtag_exact_match_rate": (
            sum(1 for row in rows if row["hashtags_exact_match"]) / sample_count if sample_count else 0.0
        ),
        "relevant_diffs": relevant_diffs,
    }


def evaluate_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    return build_report(load_samples(path))


def _render_section(name: str, payload: dict[str, Any]) -> list[str]:
    lines = [name]
    for variant in VARIANT_ORDER:
        metrics = payload.get(variant)
        if metrics is None:
            continue
        lines.append(
            (
                f"  {variant}: samples={metrics['sample_count']} "
                f"qc_fail_rate={metrics['qc_fail_rate']:.2f} "
                f"avg_len={metrics['average_length']:.1f} "
                f"data={metrics['average_data_preservation_rate']:.2f} "
                f"handles={metrics['handle_exact_match_rate']:.2f} "
                f"hashtags={metrics['hashtag_exact_match_rate']:.2f}"
            )
        )
        for diff in metrics["relevant_diffs"][:5]:
            lines.append(
                (
                    f"    - {diff['sample_id']}: "
                    f"errors={diff['qc_errors']} "
                    f"missing_data={diff['missing_data_points']} "
                    f"missing_handles={diff['missing_handles']} "
                    f"missing_hashtags={diff['missing_hashtags']}"
                )
            )
    return lines


def render_report(report: dict[str, Any]) -> str:
    lines = [
        f"fixture={report['fixture_path']}",
        f"samples={report['sample_count']}",
        "",
        "groups:",
    ]
    for group_name, payload in report["groups"].items():
        lines.extend(_render_section(f"- {group_name}", payload))
    lines.extend(["", "phase3_rollout:"])
    for variant, payload in report["phase3_rollout"].items():
        lines.extend(_render_section(f"- {variant}", {variant: payload}))
    lines.extend(["", "phase4_candidates:"])
    for variant, payload in report["phase4_candidates"].items():
        lines.extend(_render_section(f"- {variant}", {variant: payload}))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Comparativa offline de baseline editorial_rewriter.")
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH, help="Ruta al fixture JSON de muestras.")
    parser.add_argument("--json", action="store_true", help="Emite el informe en JSON.")
    parser.add_argument("--output", type=Path, help="Guarda el informe en disco.")
    args = parser.parse_args()

    report = evaluate_fixture(args.fixture)
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_report(report)

    if args.output is not None:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
