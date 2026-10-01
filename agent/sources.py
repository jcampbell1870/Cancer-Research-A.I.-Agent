"""Data source clients: PubMed, Europe PMC (preprints) and ClinicalTrials.gov."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any

import requests

from . import config

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CLINICALTRIALS_STUDIES = "https://clinicaltrials.gov/api/v2/studies"

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})
    return session


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _text(element: ET.Element | None) -> str:
    return _clean("".join(element.itertext())) if element is not None else ""


# --------------------------------------------------------------------------- PubMed

def _pubmed_params(**params: Any) -> dict[str, Any]:
    params["tool"] = "cancer-research-ai-agent"
    if config.NCBI_EMAIL:
        params["email"] = config.NCBI_EMAIL
    if config.NCBI_API_KEY:
        params["api_key"] = config.NCBI_API_KEY
    return params


def _pubmed_date(article: ET.Element) -> str:
    """Return the best available publication date as YYYY-MM-DD (or YYYY-MM / YYYY)."""
    for path in (".//ArticleDate", ".//PubMedPubDate[@PubStatus='pubmed']", ".//JournalIssue/PubDate"):
        node = article.find(path)
        if node is None:
            continue
        year = _text(node.find("Year"))
        if not year:
            continue
        month = _text(node.find("Month"))
        day = _text(node.find("Day"))
        if month and not month.isdigit():
            month = str(_MONTHS.get(month[:3].lower(), ""))
        if month:
            if day.isdigit():
                return f"{year}-{int(month):02d}-{int(day):02d}"
            return f"{year}-{int(month):02d}"
        return year
    return ""


def parse_pubmed_xml(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _text(article.find(".//MedlineCitation/PMID"))
        title = _text(article.find(".//Article/ArticleTitle"))
        if not pmid or not title:
            continue
        sections = []
        for part in article.findall(".//Article/Abstract/AbstractText"):
            label = part.get("Label")
            body = _text(part)
            if body:
                sections.append(f"{label}: {body}" if label else body)
        authors = []
        for author in article.findall(".//AuthorList/Author"):
            last = _text(author.find("LastName"))
            initials = _text(author.find("Initials"))
            collective = _text(author.find("CollectiveName"))
            if last:
                authors.append(f"{last} {initials}".strip())
            elif collective:
                authors.append(collective)
        doi = ""
        for aid in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)
        items.append({
            "id": f"pubmed:{pmid}",
            "source": "PubMed",
            "type": "publication",
            "title": title,
            "abstract": " ".join(sections),
            "authors": authors,
            "venue": _text(article.find(".//Article/Journal/Title")),
            "date": _pubmed_date(article),
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })
    return items


def fetch_pubmed(session: requests.Session, lookback_days: int, max_results: int) -> list[dict[str, Any]]:
    search = session.get(
        f"{PUBMED_BASE}/esearch.fcgi",
        params=_pubmed_params(db="pubmed", term=config.PUBMED_QUERY, datetype="edat",
                              reldate=lookback_days, retmax=max_results, sort="relevance",
                              retmode="json"),
        timeout=config.HTTP_TIMEOUT,
    )
    search.raise_for_status()
    ids = search.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    fetch = session.get(
        f"{PUBMED_BASE}/efetch.fcgi",
        params=_pubmed_params(db="pubmed", id=",".join(ids), retmode="xml"),
        timeout=config.HTTP_TIMEOUT,
    )
    fetch.raise_for_status()
    return parse_pubmed_xml(fetch.text)


# --------------------------------------------------------------------------- Europe PMC preprints

def parse_europepmc(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for result in data.get("resultList", {}).get("result", []):
        pid = result.get("id")
        title = _clean(re.sub(r"<[^>]+>", "", result.get("title", "")))
        if not pid or not title:
            continue
        doi = result.get("doi", "")
        publisher = (result.get("bookOrReportDetails") or {}).get("publisher", "") or "Preprint"
        authors = [a.strip() for a in (result.get("authorString") or "").rstrip(".").split(",") if a.strip()]
        items.append({
            "id": f"europepmc:{result.get('source', 'PPR')}:{pid}",
            "source": "Europe PMC",
            "type": "preprint",
            "title": title,
            "abstract": _clean(re.sub(r"<[^>]+>", " ", result.get("abstractText", ""))),
            "authors": authors,
            "venue": publisher,
            "date": result.get("firstPublicationDate", ""),
            "doi": doi,
            "url": f"https://doi.org/{doi}" if doi else f"https://europepmc.org/article/{result.get('source', 'PPR')}/{pid}",
        })
    return items


def fetch_preprints(session: requests.Session, lookback_days: int, max_results: int,
                    today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    start = today - timedelta(days=lookback_days)
    query = (f"{config.EUROPEPMC_PREPRINT_QUERY} AND SRC:PPR "
             f"AND FIRST_PDATE:[{start.isoformat()} TO {today.isoformat()}]")
    response = session.get(
        EUROPEPMC_SEARCH,
        params={"query": query, "format": "json", "resultType": "core", "pageSize": max_results},
        timeout=config.HTTP_TIMEOUT,
    )
    response.raise_for_status()
    return parse_europepmc(response.json())


# --------------------------------------------------------------------------- ClinicalTrials.gov

def parse_clinical_trials(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for study in data.get("studies", []):
        protocol = study.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        nct_id = ident.get("nctId")
        title = _clean(ident.get("briefTitle") or ident.get("officialTitle"))
        if not nct_id or not title:
            continue
        status = protocol.get("statusModule", {})
        design = protocol.get("designModule", {})
        sponsor = protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
        interventions = [i.get("name", "") for i in
                         protocol.get("armsInterventionsModule", {}).get("interventions", []) if i.get("name")]
        phases = [p.replace("PHASE", "Phase ").replace("EARLY_", "Early ").strip()
                  for p in design.get("phases", []) if p and p != "NA"]
        items.append({
            "id": f"nct:{nct_id}",
            "source": "ClinicalTrials.gov",
            "type": "clinical_trial",
            "title": title,
            "abstract": _clean(protocol.get("descriptionModule", {}).get("briefSummary")),
            "authors": [sponsor] if sponsor else [],
            "venue": sponsor,
            "date": status.get("studyFirstPostDateStruct", {}).get("date", ""),
            "doi": "",
            "url": f"https://clinicaltrials.gov/study/{nct_id}",
            "phases": phases,
            "status": (status.get("overallStatus") or "").replace("_", " ").title(),
            "conditions": protocol.get("conditionsModule", {}).get("conditions", []),
            "interventions": interventions,
        })
    return items


def fetch_clinical_trials(session: requests.Session, lookback_days: int, max_results: int,
                          today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    start = today - timedelta(days=lookback_days)
    response = session.get(
        CLINICALTRIALS_STUDIES,
        params={
            "query.cond": "cancer OR neoplasm OR tumor OR carcinoma OR leukemia OR lymphoma",
            "filter.advanced": (f"AREA[StudyFirstPostDate]RANGE[{start.isoformat()},MAX] "
                                "AND AREA[StudyType]INTERVENTIONAL"),
            "pageSize": max_results,
            "format": "json",
        },
        timeout=config.HTTP_TIMEOUT,
    )
    response.raise_for_status()
    return parse_clinical_trials(response.json())
