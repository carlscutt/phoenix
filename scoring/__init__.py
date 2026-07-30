"""
Phoenix Module 3 — Commercial Opportunity Scoring.

Scores opportunity clusters produced by Module 1 (optionally enriched by
Module 2 themes) using a two-layer engine:

  - deterministic.py  — Frequency, Evidence Confidence, Commercial Confidence
                         (pure arithmetic over stored evidence stats, no model call)
  - ai_scoring.py      — Severity, Market Demand, Revenue Potential,
                         Competition Saturation, Automation Potential,
                         Time To First Revenue (batched ModelService calls,
                         pinned model/prompt/temperature for reproducibility)
  - weighting.py       — Unknown-aware renormalised weighted sum
  - audit.py           — SHA-256 hash over evidence + versions + report
  - report.py           — orchestrates the above into an OpportunityScoreReport

See PHOENIX_MODULE3_ARCHITECTURE.md for the approved design this implements.
"""

from phoenix.scoring.report import score_run, get_score_report, list_score_versions

__all__ = ["score_run", "get_score_report", "list_score_versions"]
