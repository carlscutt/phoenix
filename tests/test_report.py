import pytest

from phoenix.scoring.report import score_run, get_score_report, list_score_versions
from phoenix.scoring.exceptions import NoScorableInputError, ScoringVersionNotFoundError


def test_score_run_produces_entries_for_every_cluster(seeded_run, fake_model_service):
    report = score_run(seeded_run["run_id"])
    ids = {e["opportunity_id"] for e in report["entries"]}
    assert ids == {seeded_run["rich_id"], seeded_run["thin_id"], seeded_run["empty_id"]}


def test_empty_cluster_marked_insufficient_evidence(seeded_run, fake_model_service):
    report = score_run(seeded_run["run_id"])
    empty_entry = next(e for e in report["entries"] if e["opportunity_id"] == seeded_run["empty_id"])
    assert empty_entry["status"] == "Insufficient Evidence"
    assert empty_entry["overall_score"] is None


def test_richer_cluster_outranks_thinner_cluster(seeded_run, fake_model_service):
    report = score_run(seeded_run["run_id"])
    rich = next(e for e in report["entries"] if e["opportunity_id"] == seeded_run["rich_id"])
    thin = next(e for e in report["entries"] if e["opportunity_id"] == seeded_run["thin_id"])
    assert rich["status"] == "Scored"
    assert thin["status"] == "Scored"
    assert rich["overall_score"] > thin["overall_score"]
    assert rich["ranking_position"] < thin["ranking_position"]


def test_no_clusters_raises(db, fake_model_service):
    with pytest.raises(NoScorableInputError):
        score_run(run_id=999)


def test_theme_id_attached_when_active_theme_exists(seeded_run_with_theme, fake_model_service):
    report = score_run(seeded_run_with_theme["run_id"])
    rich_entry = next(e for e in report["entries"] if e["opportunity_id"] == seeded_run_with_theme["rich_id"])
    assert rich_entry["theme_id"] == seeded_run_with_theme["theme_id"]
    assert report["theme_version_id"] == seeded_run_with_theme["theme_version_id"]


def test_no_theme_still_scores_successfully(seeded_run, fake_model_service):
    # seeded_run has no ThemeVersion at all — Module 2 optionality (Decision 2)
    report = score_run(seeded_run["run_id"])
    assert report["theme_version_id"] is None
    for e in report["entries"]:
        assert e["theme_id"] is None


def test_rerunning_creates_new_version_and_deactivates_prior(seeded_run, fake_model_service):
    score_run(seeded_run["run_id"])
    score_run(seeded_run["run_id"])
    versions = list_score_versions(seeded_run["run_id"])
    assert len(versions) == 2
    active = [v for v in versions if v["is_active"]]
    assert len(active) == 1
    assert active[0]["scoring_version"] == 2


def test_get_score_report_returns_active_version_by_default(seeded_run, fake_model_service):
    score_run(seeded_run["run_id"])
    report = get_score_report(seeded_run["run_id"])
    assert report["scoring_version"] == 1


def test_get_score_report_specific_version(seeded_run, fake_model_service):
    score_run(seeded_run["run_id"])
    score_run(seeded_run["run_id"])
    report_v1 = get_score_report(seeded_run["run_id"], scoring_version=1)
    assert report_v1["scoring_version"] == 1


def test_get_score_report_unknown_version_raises(seeded_run, fake_model_service):
    score_run(seeded_run["run_id"])
    with pytest.raises(ScoringVersionNotFoundError):
        get_score_report(seeded_run["run_id"], scoring_version=99)


def test_audit_hash_present_and_stable_across_read(seeded_run, fake_model_service):
    report = score_run(seeded_run["run_id"])
    persisted = get_score_report(seeded_run["run_id"])
    assert report["audit"]["hash"] == persisted["audit"]["hash"]
    assert len(report["audit"]["hash"]) == 64  # sha256 hex digest length


def test_ai_service_receives_batched_calls(seeded_run, fake_model_service):
    score_run(seeded_run["run_id"], batch_size=1)
    # 2 scorable clusters (rich, thin) at batch_size=1 -> 2 calls
    assert len(fake_model_service.calls) == 2
