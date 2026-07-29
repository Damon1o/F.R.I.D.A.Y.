"""Unified search: /api/search. No page — the assistant is the search surface."""
from flask import Blueprint, jsonify, request

from pages.search import models

search_bp = Blueprint("search", __name__)


@search_bp.route("/api/search", methods=["GET"])
def search_api():
    return jsonify(models.search(request.args.get("q", "")))
