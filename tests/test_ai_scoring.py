import json
import pytest

from phoenix.scoring.ai_scoring import (
    ClusterForScoring,
    score_clusters_ai,
    _parse_response,
    AI_CATEGORIES,
)
from phoenix.scoring.weighting import UNKNOWN


class StubModelService:
    def __init__(self, response_text):
        self.response_text = response_text
        self.calls = []

    def complete(self, prompt, model=None, **kwargs):
        self.calls.append({"prompt": prompt, "model": model, "kwargs": kwargs})
        return self.response_text


def test_well_formed_response_parses_all_categories():
    clusters = [ClusterForScoring(cluster_id=1, representative_text="x", evidence_snippets=["a", "b"])]
    response = json.dumps(
        [{"cluster_id": 1, "severity": 70, "market_demand": 60, "revenue_potential": 55,
          "competition_saturation": 40, "automation_potential": 80, "time_to_first_revenue": 30,
          "reasoning": "ok"}]
    )
    svc = StubModelService(response)
    results = score_clusters_ai(svc, clusters, batch_size=5)
    assert results[1]["severity"] == 70.0
    assert all(cat in results[1] for cat in AI_CATEGORIES)


def test_missing_cluster_in_response_falls_back_to_unknown():
    clusters = [
        ClusterForScoring(cluster_id=1, representative_text="x", evidence_snippets=[]),
        ClusterForScoring(cluster_id=2, representative_text="y", evidence_snippets=[]),
    ]
    # response only covers cluster_id 1
    response = json.dumps([{"cluster_id": 1, "severity": 50, "market_demand": 50,
                             "revenue_potential": 50, "competition_saturation": 50,
                             "automation_potential": 50, "time_to_first_revenue": 50}])
    svc = StubModelService(response)
    results = score_clusters_ai(svc, clusters, batch_size=5)
    assert results[2]["severity"] == UNKNOWN


def test_malformed_json_falls_back_to_unknown_for_all():
    clusters = [ClusterForScoring(cluster_id=1, representative_text="x", evidence_snippets=[])]
    svc = StubModelService("not json at all")
    results = score_clusters_ai(svc, clusters, batch_size=5)
    assert all(results[1][cat] == UNKNOWN for cat in AI_CATEGORIES)


def test_model_literal_unknown_string_is_respected():
    clusters = [ClusterForScoring(cluster_id=1, representative_text="x", evidence_snippets=[])]
    response = json.dumps(
        [{"cluster_id": 1, "severity": "Unknown", "market_demand": 50, "revenue_potential": 50,
          "competition_saturation": 50, "automation_potential": 50, "time_to_first_revenue": 50}]
    )
    svc = StubModelService(response)
    results = score_clusters_ai(svc, clusters, batch_size=5)
    assert results[1]["severity"] == UNKNOWN


def test_out_of_range_value_treated_as_unknown():
    clusters = [ClusterForScoring(cluster_id=1, representative_text="x", evidence_snippets=[])]
    response = json.dumps(
        [{"cluster_id": 1, "severity": 150, "market_demand": 50, "revenue_potential": 50,
          "competition_saturation": 50, "automation_potential": 50, "time_to_first_revenue": 50}]
    )
    svc = StubModelService(response)
    results = score_clusters_ai(svc, clusters, batch_size=5)
    assert results[1]["severity"] == UNKNOWN


def test_batching_respects_batch_size():
    clusters = [ClusterForScoring(cluster_id=i, representative_text="x", evidence_snippets=[]) for i in range(1, 8)]
    svc = StubModelService(json.dumps([
        {"cluster_id": i, "severity": 10, "market_demand": 10, "revenue_potential": 10,
         "competition_saturation": 10, "automation_potential": 10, "time_to_first_revenue": 10}
        for i in range(1, 4)
    ]))
    score_clusters_ai(svc, clusters, batch_size=3)
    # 7 clusters at batch_size=3 -> 3 calls (3,3,1)
    assert len(svc.calls) == 3
