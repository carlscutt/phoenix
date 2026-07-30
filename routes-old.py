"""
ADDITIONS FOR: the existing `phoenix_bp` Flask blueprint (routes.py),
alongside the existing POST /api/phoenix/reports/<run_id>/themes,
GET /api/phoenix/reports/<run_id>/versions, and
GET /api/phoenix/reports/<run_id>?theme_version=N routes.

Same caveat as phoenix_actions_additions.py — no filesystem access to the
live routes.py this session, so this is provided as additions to paste
in, using the same blueprint/response conventions already established
for Module 1/2's routes.
"""

from flask import jsonify, request

# Assumes `phoenix_bp` is already defined in the real routes.py and these
# decorators get added to it directly.
#
# from . import phoenix_bp
# from .phoenix_actions import submit_opportunity_scoring, get_score, list_scoring_versions


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
