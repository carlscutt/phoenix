from phoenix.scoring.deterministic import (
    ClusterEvidenceStats,
    compute_frequency,
    compute_evidence_confidence,
    compute_commercial_confidence,
)


def test_frequency_scales_relative_to_run_max():
    a = ClusterEvidenceStats(1, complaint_count=10, unique_source_types=2, total_known_source_types=2)
    b = ClusterEvidenceStats(2, complaint_count=5, unique_source_types=1, total_known_source_types=2)
    all_stats = [a, b]
    assert compute_frequency(a, all_stats) == 100.0
    assert compute_frequency(b, all_stats) == 50.0


def test_frequency_empty_run_is_zero():
    a = ClusterEvidenceStats(1, complaint_count=0, unique_source_types=0, total_known_source_types=2)
    assert compute_frequency(a, [a]) == 0.0


def test_evidence_confidence_rewards_diversity_and_volume():
    low = ClusterEvidenceStats(1, complaint_count=1, unique_source_types=1, total_known_source_types=2)
    high = ClusterEvidenceStats(2, complaint_count=10, unique_source_types=2, total_known_source_types=2)
    assert compute_evidence_confidence(high) > compute_evidence_confidence(low)


def test_evidence_confidence_zero_known_sources_no_crash():
    stats = ClusterEvidenceStats(1, complaint_count=3, unique_source_types=0, total_known_source_types=0)
    assert compute_evidence_confidence(stats) >= 0.0


def test_commercial_confidence_bands():
    strong = ClusterEvidenceStats(1, complaint_count=8, unique_source_types=2, total_known_source_types=2)
    weak = ClusterEvidenceStats(2, complaint_count=1, unique_source_types=1, total_known_source_types=2)

    assert compute_commercial_confidence(strong, unknown_category_count=0, total_category_count=8) == "High"
    assert compute_commercial_confidence(weak, unknown_category_count=6, total_category_count=8) == "Low"


def test_commercial_confidence_handles_zero_categories():
    stats = ClusterEvidenceStats(1, complaint_count=1, unique_source_types=1, total_known_source_types=2)
    # should not raise a ZeroDivisionError
    result = compute_commercial_confidence(stats, unknown_category_count=0, total_category_count=0)
    assert result in ("Low", "Medium", "High")
