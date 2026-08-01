"""
phoenix/routes.py — Flask blueprint for all Phoenix API routes
(Modules 1-4).

REBUILT 2026-07-31: the live routes.py was found to contain only
"addition fragments" (Module 3's and Module 4's, pasted one after
another) with no `phoenix_bp = Blueprint(...)` definition anywhere —
the same category of incident as the earlier phoenix_actions.py
overwrite. This is a from-scratch reconstruction, not a guess: every
route below is either (a) directly confirmed against a real fetch()
call in studio.html (exact URL, method, and request/response shape),
or (b) a direct wrap of a real, already-verified phoenix_actions.py
function using the same conventions as the confirmed routes.

If your real routes.py had additional routes beyond what studio.html
actually calls (e.g. an admin-only or CLI-only endpoint with no UI
caller), those aren't reconstructable from what's available this
session and would need to be re-added separately — nothing here
removes anything real, but nothing invisible to studio.html could be
recovered either.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from phoenix.phoenix_actions import (
    submit_opportunity_discovery,
    get_report,
    list_reports,
    theme_report,
    list_theme_versions,
    submit_opportunity_scoring,
    get_score,
    list_scoring_versions,
    submit_solution_generation,
    get_solutions,
    get_solution_versions,
    approve_solution_blueprint,
)
from phoenix.solution_generation.exceptions import BlueprintNotFoundError

phoenix_bp = Blueprint("phoenix", __name__)


# ---------------------------------------------------------------------
# Module 1 — Opportunity Discovery
# Confirmed against studio.html: fetch('/api/phoenix/reports') (GET),
# fetch('/api/phoenix/reports', {method:'POST', body:{topic}}) —
# response must include `run_id` (openOpportunityDetail(data.run_id)).
# ---------------------------------------------------------------------


@phoenix_bp.route("/api/phoenix/reports", methods=["GET"])
def list_reports_route():
    return jsonify(list_reports()), 200


@phoenix_bp.route("/api/phoenix/reports", methods=["POST"])
def submit_opportunity_discovery_route():
    topic = request.json.get("topic", "") if request.is_json else ""
    try:
        run_id = submit_opportunity_discovery(topic)
        return jsonify({"run_id": run_id}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------
# Module 1/2 — report detail, themes
# Confirmed against studio.html: fetch(`/api/phoenix/reports/${runId}` +
# (themeVersion ? `?theme_version=${themeVersion}` : '')),
# fetch(`/api/phoenix/reports/${runId}/themes/versions`),
# fetch(`/api/phoenix/reports/${runId}/themes`, {method:'POST'}).
# ---------------------------------------------------------------------


@phoenix_bp.route("/api/phoenix/reports/<int:run_id>", methods=["GET"])
def get_report_route(run_id):
    theme_version = request.args.get("theme_version", type=int)
    try:
        report = get_report(run_id, theme_version=theme_version)
        return jsonify(report), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@phoenix_bp.route("/api/phoenix/reports/<int:run_id>/themes/versions", methods=["GET"])
def list_theme_versions_route(run_id):
    return jsonify(list_theme_versions(run_id)), 200


@phoenix_bp.route("/api/phoenix/reports/<int:run_id>/themes", methods=["POST"])
def theme_report_route(run_id):
    try:
        report = theme_report(run_id)
        return jsonify(report), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# ---------------------------------------------------------------------
# Module 3 — Commercial Opportunity Scoring
# Unchanged from the confirmed fragment: POST/GET .../score,
# GET .../score/versions.
# ---------------------------------------------------------------------


@phoenix_bp.route("/api/phoenix/reports/<int:run_id>/score", methods=["POST"])
def score_report_route(run_id):
    batch_size = request.json.get("batch_size", 5) if request.is_json else 5
    try:
        report = submit_opportunity_scoring(run_id, batch_size=batch_size)
        return jsonify(report), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@phoenix_bp.route("/api/phoenix/reports/<int:run_id>/score", methods=["GET"])
def get_score_route(run_id):
    scoring_version = request.args.get("scoring_version", type=int)
    try:
        report = get_score(run_id, scoring_version=scoring_version)
        return jsonify(report), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@phoenix_bp.route("/api/phoenix/reports/<int:run_id>/score/versions", methods=["GET"])
def list_score_versions_route(run_id):
    return jsonify(list_scoring_versions(run_id)), 200


# ---------------------------------------------------------------------
# Module 4 — Solution Generation Engine
# ---------------------------------------------------------------------


@phoenix_bp.route(
    "/api/phoenix/reports/<int:run_id>/opportunities/<int:cluster_id>/solutions",
    methods=["POST"],
)
def generate_solutions_route(run_id, cluster_id):
    scoring_version = request.json.get("scoring_version") if request.is_json else None
    try:
        result = submit_solution_generation(run_id, cluster_id, scoring_version=scoring_version)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@phoenix_bp.route(
    "/api/phoenix/reports/<int:run_id>/opportunities/<int:cluster_id>/solutions",
    methods=["GET"],
)
def get_solutions_route(run_id, cluster_id):
    scoring_version = request.args.get("scoring_version", type=int)
    try:
        result = get_solutions(run_id, cluster_id, scoring_version=scoring_version)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    if result is None:
        return jsonify({"blueprints": [], "generation_version": None}), 200
    return jsonify(result), 200


@phoenix_bp.route(
    "/api/phoenix/reports/<int:run_id>/opportunities/<int:cluster_id>/solutions/versions",
    methods=["GET"],
)
def list_solution_versions_route(run_id, cluster_id):
    scoring_version = request.args.get("scoring_version", type=int)
    try:
        return jsonify(get_solution_versions(run_id, cluster_id, scoring_version=scoring_version)), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@phoenix_bp.route("/api/phoenix/solutions/<string:public_id>/approve", methods=["POST"])
def approve_solution_route(public_id):
    approved = request.json.get("approved", True) if request.is_json else True
    try:
        result = approve_solution_blueprint(public_id, approved=approved)
        return jsonify(result), 200
    except BlueprintNotFoundError as e:
        return jsonify({"error": str(e)}), 404
