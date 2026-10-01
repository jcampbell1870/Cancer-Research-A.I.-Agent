"""Render web service exposing the cancer research A.I. agent.

Endpoints
---------
GET  /              Service information.
GET  /healthz       Health check used by Render.
GET  /api/results   Latest research results (JSON).
POST /api/refresh   Run the agent now. Requires an Authorization bearer token equal to REFRESH_TOKEN.
"""

from __future__ import annotations

import hmac
import logging
import os
import threading

from flask import Flask, jsonify, request

from agent.research import all_sources_failed, load_results, run_research, save_results

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

RESULTS_PATH = os.environ.get("RESULTS_PATH", os.path.join(os.path.dirname(__file__), "docs", "data", "results.json"))
PAGES_URL = os.environ.get("PAGES_URL", "https://jcampbell1870.github.io/Cancer-Research-A.I.-Agent/")

app = Flask(__name__)
_refresh_lock = threading.Lock()


@app.after_request
def add_cors_headers(response):
    if request.path == "/api/results":
        response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.get("/")
def index():
    results = load_results(RESULTS_PATH) or {}
    return jsonify({
        "service": "Cancer Research A.I. Agent",
        "description": "Searches PubMed, preprint servers and ClinicalTrials.gov for cutting-edge cancer "
                       "treatment and cure research.",
        "last_refreshed": results.get("generated_at"),
        "findings": len(results.get("findings", [])),
        "results_page": PAGES_URL,
        "endpoints": {"results": "/api/results", "refresh": "POST /api/refresh", "health": "/healthz"},
    })


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.get("/api/results")
def results():
    data = load_results(RESULTS_PATH)
    if data is None:
        return jsonify({"error": "No results available yet. Trigger a refresh first."}), 404
    return jsonify(data)


def _authorized() -> bool:
    token = os.environ.get("REFRESH_TOKEN", "")
    header = request.headers.get("Authorization", "")
    supplied = header[7:] if header.startswith("Bearer ") else ""
    return bool(token) and hmac.compare_digest(supplied.encode(), token.encode())


@app.post("/api/refresh")
def refresh():
    if not os.environ.get("REFRESH_TOKEN"):
        return jsonify({"error": "Refresh is disabled: REFRESH_TOKEN is not configured."}), 403
    if not _authorized():
        return jsonify({"error": "Unauthorized"}), 401
    if not _refresh_lock.acquire(blocking=False):
        return jsonify({"error": "A refresh is already running."}), 409
    try:
        data = run_research()
        if all_sources_failed(data):
            return jsonify({"error": "All research sources failed.", "details": data["errors"]}), 502
        save_results(data, RESULTS_PATH)
        return jsonify(data)
    finally:
        _refresh_lock.release()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
