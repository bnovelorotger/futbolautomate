from __future__ import annotations

from app.core.enums import ContentType
from app.services.editorial_rewriter import CONTENT_TYPE_REWRITE_MODE, EditorialRewriteMode
from scripts.editorial_rewrite_offline_eval import evaluate_fixture, load_samples


def test_editorial_rewrite_eval_fixture_matches_mode_split() -> None:
    samples = load_samples()

    data_pure = [sample for sample in samples if sample["group"] == "data_pure"]
    humanizable = [sample for sample in samples if sample["group"] == "humanizable"]

    assert len(data_pure) == 10
    assert len(humanizable) == 10

    for sample in data_pure:
        assert CONTENT_TYPE_REWRITE_MODE[ContentType(sample["content_type"])] == EditorialRewriteMode.STRICT_DATA
    for sample in humanizable:
        assert CONTENT_TYPE_REWRITE_MODE[ContentType(sample["content_type"])] == EditorialRewriteMode.HUMANIZED_LOCAL


def test_editorial_rewrite_eval_report_exposes_required_metrics() -> None:
    report = evaluate_fixture()

    assert report["sample_count"] == 20
    assert len(report["rows"]) == 60
    assert set(report["groups"]) == {"data_pure", "humanizable"}
    assert set(report["variants"]) == {"draft", "current_rewrite", "humanized_local"}

    for group_name in ("data_pure", "humanizable"):
        metrics = report["groups"][group_name]
        for variant_name in ("draft", "current_rewrite", "humanized_local"):
            variant = metrics[variant_name]
            assert "qc_fail_rate" in variant
            assert "average_length" in variant
            assert "average_data_preservation_rate" in variant
            assert "handle_exact_match_rate" in variant
            assert "hashtag_exact_match_rate" in variant


def test_editorial_rewrite_eval_phase_gates_support_narrow_rollout() -> None:
    report = evaluate_fixture()

    phase3 = report["phase3_rollout"]
    humanized_phase3 = phase3["humanized_local"]
    current_phase3 = phase3["current_rewrite"]
    data_pure = report["groups"]["data_pure"]
    phase4 = report["phase4_candidates"]

    assert humanized_phase3["sample_count"] == 6
    assert humanized_phase3["qc_failed_count"] == 0
    assert humanized_phase3["average_data_preservation_rate"] == 1.0
    assert humanized_phase3["handle_exact_match_rate"] == 1.0
    assert humanized_phase3["hashtag_exact_match_rate"] == 1.0

    assert current_phase3["qc_failed_count"] == 0
    assert data_pure["humanized_local"]["qc_failed_count"] > data_pure["current_rewrite"]["qc_failed_count"]
    assert (
        data_pure["humanized_local"]["average_data_preservation_rate"]
        < data_pure["current_rewrite"]["average_data_preservation_rate"]
    )
    assert (
        phase4["humanized_local"]["average_data_preservation_rate"]
        < phase4["current_rewrite"]["average_data_preservation_rate"]
    )
