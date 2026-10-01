"""Ranking, categorization and (optional) AI summarization of research findings."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)

# Signals that a finding may represent a meaningful step toward a cure.
SIGNAL_WEIGHTS: dict[str, float] = {
    r"\bcur(e|es|ed|ative)\b": 5,
    r"complete (response|remission)": 4,
    r"\bbreakthrough\b": 3,
    r"\bremission\b": 2,
    r"phase (iii|3)\b": 3,
    r"phase (ii|2)\b": 1.5,
    r"overall survival": 2,
    r"progression-free survival": 1.5,
    r"\brandomi[sz]ed\b": 1,
    r"first-in-human": 2,
    r"\bnovel\b": 1,
    r"\bfda\b|approv(al|ed)": 2,
    r"durable": 1.5,
    r"eradicat": 2,
}

CATEGORIES: dict[str, str] = {
    "Immunotherapy": r"immunotherap|checkpoint|pd-1|pd-l1|ctla-4|bispecific",
    "Cell Therapy": r"car-?t\b|car t-cell|cell therapy|til therapy|nk cell",
    "Cancer Vaccines": r"vaccine|neoantigen|mrna",
    "Gene Therapy & Editing": r"gene therapy|crispr|gene editing|oncolytic vir",
    "Targeted Therapy": r"targeted therap|inhibitor|antibody-drug conjugate|\badc\b|kras|egfr|her2|braf",
    "Radiotherapy & Radiopharmaceuticals": r"radiotherap|radiation|radioligand|radiopharm|proton",
    "Early Detection & Diagnostics": r"early detection|screening|liquid biopsy|biomarker|diagnos",
    "AI & Computational": r"artificial intelligence|machine learning|deep learning|\bai\b",
}

CANCER_TYPES: dict[str, str] = {
    "Breast": r"breast", "Lung": r"lung|nsclc|sclc", "Colorectal": r"colorectal|colon|rectal",
    "Prostate": r"prostate", "Pancreatic": r"pancrea", "Leukemia": r"leuk(a)?emia|\baml\b|\bcll\b",
    "Lymphoma": r"lymphoma", "Myeloma": r"myeloma", "Melanoma": r"melanoma", "Brain": r"glioma|glioblastoma|brain",
    "Ovarian": r"ovarian", "Liver": r"hepatocellular|liver", "Gastric": r"gastric|stomach",
    "Kidney": r"renal|kidney", "Bladder": r"bladder|urothelial", "Head & Neck": r"head and neck|oral cavity|oropharyn|nasopharyn",
    "Cervical": r"cervical", "Pediatric": r"pediatric|paediatric|childhood|neuroblastoma",
    "Sarcoma": r"sarcoma",
}


def _haystack(item: dict[str, Any]) -> str:
    parts = [item.get("title", ""), item.get("abstract", "")]
    parts += item.get("phases", []) + item.get("conditions", []) + item.get("interventions", [])
    return " ".join(parts).lower()


def score_finding(item: dict[str, Any]) -> float:
    text = _haystack(item)
    title = item.get("title", "").lower()
    score = 0.0
    for pattern, weight in SIGNAL_WEIGHTS.items():
        if re.search(pattern, text):
            score += weight
            if re.search(pattern, title):
                score += weight / 2  # signals in the title matter more
    if item.get("abstract"):
        score += 1
    return round(score, 2)


def classify(item: dict[str, Any]) -> tuple[list[str], list[str]]:
    text = _haystack(item)
    categories = [name for name, pattern in CATEGORIES.items() if re.search(pattern, text)]
    cancers = [name for name, pattern in CANCER_TYPES.items() if re.search(pattern, text)]
    return categories or ["Other"], cancers


def extractive_summary(text: str, max_chars: int = 420) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    # Prefer the conclusions section of structured abstracts.
    match = re.search(r"(CONCLUSIONS?|INTERPRETATION|SIGNIFICANCE)\s*:\s*(.+)", text, flags=re.I)
    if match:
        text = match.group(2)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = ""
    for sentence in sentences:
        if summary and len(summary) + len(sentence) + 1 > max_chars:
            break
        summary = f"{summary} {sentence}".strip()
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return summary


def enrich(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in items:
        item["score"] = score_finding(item)
        item["categories"], item["cancer_types"] = classify(item)
        item["summary"] = extractive_summary(item.get("abstract", ""))
    items.sort(key=lambda i: (i["score"], i.get("date", "")), reverse=True)
    return items


def heuristic_overview(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No new cancer treatment research matched the agent's search criteria during this period."
    types = Counter(i["type"] for i in items)
    categories = Counter(c for i in items for c in i["categories"] if c != "Other")
    cancers = Counter(c for i in items for c in i["cancer_types"])
    labels = {"publication": "peer-reviewed publications", "preprint": "preprints",
              "clinical_trial": "newly registered clinical trials"}
    parts = ", ".join(f"{n} {labels.get(t, t)}" for t, n in types.most_common())
    text = f"This week the agent reviewed {parts}."
    if categories:
        text += " Leading research themes: " + ", ".join(c for c, _ in categories.most_common(3)) + "."
    if cancers:
        text += " Most-studied cancers: " + ", ".join(c for c, _ in cancers.most_common(3)) + "."
    text += f" Top-ranked finding: \u201c{items[0]['title']}\u201d."
    return text


def ai_summarize(items: list[dict[str, Any]], session: requests.Session) -> str | None:
    """Use an OpenAI-compatible chat model to summarize the top findings.

    Adds ``ai_summary`` and ``ai_significance`` to the summarized items and returns a weekly
    overview. Returns ``None`` when no API key is configured or the call fails.
    """
    if not config.OPENAI_API_KEY or not items:
        return None
    top = items[: config.AI_SUMMARY_LIMIT]
    payload = [{"id": i["id"], "type": i["type"], "title": i["title"],
                "text": (i.get("abstract") or "")[:1500]} for i in top]
    prompt = (
        "You are an oncology research analyst. Review these new cancer research items and respond "
        "with JSON of the form {\"overview\": str, \"items\": [{\"id\": str, \"summary\": str, "
        "\"significance\": int}]}. 'overview' is a 3-5 sentence plain-language digest of the most "
        "promising developments toward curing cancer this week. For each item give a 1-2 sentence "
        "plain-language summary and a significance score from 1 (incremental) to 10 (potential cure). "
        "Do not overstate results; note when evidence is early-stage.\n\n" + json.dumps(payload)
    )
    try:
        response = session.post(
            f"{config.OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": "Bearer " + config.OPENAI_API_KEY},
            json={"model": config.OPENAI_MODEL, "temperature": 0.2,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=max(config.HTTP_TIMEOUT, 120),
        )
        response.raise_for_status()
        content = json.loads(response.json()["choices"][0]["message"]["content"])
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError) as exc:
        log.warning("AI summarization failed: %s", exc)
        return None

    by_id = {i["id"]: i for i in top}
    for entry in content.get("items", []):
        item = by_id.get(entry.get("id")) if isinstance(entry, dict) else None
        if not item:
            continue
        if entry.get("summary"):
            item["ai_summary"] = str(entry["summary"]).strip()
        try:
            item["ai_significance"] = max(1, min(10, int(entry.get("significance"))))
        except (TypeError, ValueError):
            pass
    overview = content.get("overview")
    return str(overview).strip() if overview else None
