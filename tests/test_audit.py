from phoenix.scoring.audit import compute_report_hash


def test_hash_is_deterministic_for_identical_input():
    evidence = [{"source_url": "https://x.com/1", "source_type": "reddit"}]
    report = {"run_id": 1, "entries": [{"opportunity_id": 1, "overall_score": 50.0}]}

    h1 = compute_report_hash(evidence, "v1", "ollama-local", report)
    h2 = compute_report_hash(evidence, "v1", "ollama-local", report)
    assert h1 == h2


def test_hash_changes_when_report_changes():
    evidence = [{"source_url": "https://x.com/1", "source_type": "reddit"}]
    report_a = {"run_id": 1, "entries": [{"opportunity_id": 1, "overall_score": 50.0}]}
    report_b = {"run_id": 1, "entries": [{"opportunity_id": 1, "overall_score": 51.0}]}

    h_a = compute_report_hash(evidence, "v1", "ollama-local", report_a)
    h_b = compute_report_hash(evidence, "v1", "ollama-local", report_b)
    assert h_a != h_b


def test_hash_changes_when_model_version_changes():
    evidence = [{"source_url": "https://x.com/1", "source_type": "reddit"}]
    report = {"run_id": 1, "entries": []}

    h_a = compute_report_hash(evidence, "v1", "ollama-local", report)
    h_b = compute_report_hash(evidence, "v1", "ollama-remote", report)
    assert h_a != h_b


def test_hash_is_key_order_independent():
    evidence = [{"b": 2, "a": 1}]
    evidence_reordered = [{"a": 1, "b": 2}]
    report = {"x": 1, "y": 2}
    report_reordered = {"y": 2, "x": 1}

    h1 = compute_report_hash(evidence, "v1", "m1", report)
    h2 = compute_report_hash(evidence_reordered, "v1", "m1", report_reordered)
    assert h1 == h2
