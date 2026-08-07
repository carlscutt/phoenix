"""
phoenix/routes.py — Flask blueprint for all Phoenix API routes
(Modules 1-5).

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

MODULE 5 ADDITION (2026-08-01): three new routes at the bottom, same
URL-nesting convention as Module 4's own opportunity-scoped routes
(/api/phoenix/reports/<run_id>/opportunities/<cluster_id>/...). These
are NEW — there was no prior studio.html fetch() call to confirm them
against, since the UI for them doesn't exist yet either (that's Step
10, right after this). Verify these against the real UI once Step 10's
studio.html changes are wired up, same as every other route here was
originally verified against a real caller.

MODULE 6 ADDITION (2026-08-04): three new routes at the bottom, below
Module 5's. Different URL shape on purpose — flat
/api/phoenix/solutions/<public_id>/blueprint..., same convention as
Module 4's own /api/phoenix/solutions/<public_id>/approve route just
above it, not nested under reports/opportunities like Modules 3-5's
routes are. This is a per-blueprint action scoped to one specific
solution_public_id (Decision 3), not an opportunity-level listing —
run_id/cluster_id go in the POST body instead of the URL, same place
Module 4's approve route puts its own `approved` flag, since
generate_business_blueprint() needs both to resolve the right
ValidationVersion but the URL itself only needs to identify the
blueprint. Verified against real studio.html changes delivered in the
same batch as these routes — not a guess.
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
    submit_solution_validation,
    get_validations,
    get_validation_versions,
    submit_business_blueprint_generation,
    get_business_blueprint,
    get_business_blueprint_versions,
)
from phoenix.solution_generation.exceptions import BlueprintNotFoundError
from phoenix.business_blueprint.exceptions import (
    ValidatedBlueprintNotFoundError,
    SolutionNotFoundError,
    SectionGenerationError,
)

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


# ---------------------------------------------------------------------
# Module 5 — Commercial Validation Engine
# Same URL-nesting convention as Module 4's opportunity-scoped routes
# directly above. NEW routes — not yet confirmed against a real
# studio.html fetch() call (Step 10 wires that up next); verify these
# against the real UI once that's in place.
# ---------------------------------------------------------------------


@phoenix_bp.route(
    "/api/phoenix/reports/<int:run_id>/opportunities/<int:cluster_id>/validations",
    methods=["POST"],
)
def validate_solutions_route(run_id, cluster_id):
    scoring_version = request.json.get("scoring_version") if request.is_json else None
    try:
        result = submit_solution_validation(run_id, cluster_id, scoring_version=scoring_version)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@phoenix_bp.route(
    "/api/phoenix/reports/<int:run_id>/opportunities/<int:cluster_id>/validations",
    methods=["GET"],
)
def get_validations_route(run_id, cluster_id):
    try:
        result = get_validations(run_id, cluster_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    if result is None:
        return jsonify({"validated_blueprints": [], "validation_version": None}), 200
    return jsonify(result), 200


@phoenix_bp.route(
    "/api/phoenix/reports/<int:run_id>/opportunities/<int:cluster_id>/validations/versions",
    methods=["GET"],
)
def list_validation_versions_route(run_id, cluster_id):
    try:
        return jsonify(get_validation_versions(run_id, cluster_id)), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# ---------------------------------------------------------------------
# Module 6 — Business Blueprint Engine
# Scoped to one specific solution_public_id (Decision 3), same flat
# /api/phoenix/solutions/<public_id>/... shape as Module 4's own
# approve route above — this is a per-blueprint action, not an
# opportunity-scoped listing, unlike Modules 3-5's routes. run_id and
# cluster_id go in the POST body (same place Module 4's approve route
# puts its own `approved` flag) since generate_business_blueprint()
# needs both to resolve the right ValidationVersion, even though the
# URL itself only needs to identify the blueprint. The two GET routes
# below don't need run_id/cluster_id at all — get_business_blueprint()
# and get_business_blueprint_versions() key only on solution_public_id.
# ---------------------------------------------------------------------


@phoenix_bp.route("/api/phoenix/solutions/<string:public_id>/blueprint", methods=["POST"])
def generate_business_blueprint_route(public_id):
    run_id = request.json.get("run_id") if request.is_json else None
    cluster_id = request.json.get("cluster_id") if request.is_json else None
    if run_id is None or cluster_id is None:
        return jsonify({"error": "run_id and cluster_id are both required"}), 400
    try:
        result = submit_business_blueprint_generation(run_id, cluster_id, public_id)
        return jsonify(result), 201
    except (ValidatedBlueprintNotFoundError, SolutionNotFoundError) as e:
        return jsonify({"error": str(e)}), 404
    except SectionGenerationError as e:
        return jsonify({"error": str(e)}), 422


@phoenix_bp.route("/api/phoenix/solutions/<string:public_id>/blueprint", methods=["GET"])
def get_business_blueprint_route(public_id):
    result = get_business_blueprint(public_id)
    if result is None:
        return jsonify({"sections": {}, "blueprint_version": None}), 200
    return jsonify(result), 200


@phoenix_bp.route("/api/phoenix/solutions/<string:public_id>/blueprint/versions", methods=["GET"])
def list_business_blueprint_versions_route(public_id):
    return jsonify(get_business_blueprint_versions(public_id)), 200
