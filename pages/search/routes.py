"""Unified search: /search page + /api/search."""
from flask import Blueprint, jsonify, render_template, request

from pages.search import models

search_bp = Blueprint("search", __name__)


@search_bp.route("/search")
def search_page():
    q = request.args.get("q", "")
    return render_template("search.html", q=q, results=models.search(q) if q else None)


@search_bp.route("/api/search", methods=["GET"])
def search_api():
    return jsonify(models.search(request.args.get("q", "")))
