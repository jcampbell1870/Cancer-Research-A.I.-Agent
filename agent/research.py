"""Orchestrates a full research run: fetch, deduplicate, rank, summarize and save."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests

from . import analyzer, config, sources

log = logging.getLogger(__name__)

SOURCES: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "PubMed": sources.fetch_pubmed,
    "Europe PMC preprints": sources.fetch_preprints,
    "ClinicalTrials.gov": sources.fetch_clinical_trials,
}


def _dedupe_key(item: dict[str, Any]) -> str:
    if item.get("doi"):
        return "doi:" + item["doi"].lower()
    return "title:" + re.sub(r"[^a-z0-9]", "", item.get("title", "").lower())


def run_research(session: requests.Session | None = None, lookback_days: int | None = None,
                 max_per_source: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    session = session or sources.make_session()
    lookback_days = lookback_days or config.LOOKBACK_DAYS
    max_per_source = max_per_source or config.MAX_RESULTS_PER_SOURCE
    now = now or datetime.now(timezone.utc)

    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for name, fetch in SOURCES.items():
        try:
            fetched = fetch(session, lookback_days, max_per_source)
            log.info("%s: %d items", name, len(fetched))
            items.extend(fetched)
        except (requests.RequestException, ET.ParseError, ValueError, KeyError) as exc:
            # Strip query strings so API keys never end up in (public) logs.
            log.warning("%s failed: %s", name, re.sub(r"\?\S*", "", str(exc)))
            errors.append(f"{name}: {exc.__class__.__name__}")

    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        unique.setdefault(_dedupe_key(item), item)
    findings = analyzer.enrich(list(unique.values()))[: config.MAX_FINDINGS]

    overview = analyzer.ai_summarize(findings, session)
    ai_model = config.OPENAI_MODEL if overview else None
    if overview is None:
        overview = analyzer.heuristic_overview(findings)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "period_start": (now - timedelta(days=lookback_days)).date().isoformat(),
        "period_end": now.date().isoformat(),
        "lookback_days": lookback_days,
        "ai_model": ai_model,
        "overview": overview,
        "stats": {
            "total": len(findings),
            "by_type": dict(Counter(f["type"] for f in findings)),
            "by_category": dict(Counter(c for f in findings for c in f["categories"]).most_common()),
            "sources_queried": list(SOURCES),
        },
        "errors": errors,
        "findings": findings,
    }


def all_sources_failed(results: dict[str, Any]) -> bool:
    return len(results.get("errors", [])) >= len(SOURCES)


def save_results(results: dict[str, Any], path: str) -> None:
    """Atomically write results JSON to ``path``."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_results(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def is_valid_results(data: Any) -> bool:
    return (isinstance(data, dict) and isinstance(data.get("findings"), list)
            and isinstance(data.get("generated_at"), str))
