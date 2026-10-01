import json
from datetime import datetime, timezone

import pytest
import requests

from agent import analyzer, config, research, sources

PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <Journal><Title>The New England Journal of Medicine</Title></Journal>
        <ArticleTitle>CAR-T therapy achieves <i>complete remission</i> in refractory leukemia: a phase 3 trial</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Relapsed leukemia has poor outcomes.</AbstractText>
          <AbstractText Label="CONCLUSIONS">CAR-T therapy produced durable complete remission and may be curative.</AbstractText>
        </Abstract>
        <AuthorList><Author><LastName>Smith</LastName><Initials>J</Initials></Author></AuthorList>
        <ArticleDate><Year>2026</Year><Month>09</Month><Day>28</Day></ArticleDate>
      </Article>
    </MedlineCitation>
    <PubmedData><ArticleIdList><ArticleId IdType="doi">10.1000/ABC</ArticleId></ArticleIdList></PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""

EUROPEPMC_JSON = {"resultList": {"result": [
    {"id": "PPR1", "source": "PPR", "title": "An mRNA <i>vaccine</i> for pancreatic cancer",
     "abstractText": "<p>A novel neoantigen vaccine.</p>", "authorString": "Doe A, Roe B.",
     "firstPublicationDate": "2026-09-29", "doi": "10.1101/xyz",
     "bookOrReportDetails": {"publisher": "bioRxiv"}},
    # Duplicate of the PubMed item (same DOI, different case) should be dropped.
    {"id": "PPR2", "source": "PPR", "title": "Duplicate", "doi": "10.1000/abc"},
]}}

CT_JSON = {"studies": [{"protocolSection": {
    "identificationModule": {"nctId": "NCT01234567", "briefTitle": "Radioligand therapy for prostate cancer"},
    "statusModule": {"overallStatus": "NOT_YET_RECRUITING", "studyFirstPostDateStruct": {"date": "2026-09-30"}},
    "descriptionModule": {"briefSummary": "A randomized phase 2 study."},
    "designModule": {"phases": ["PHASE2"]},
    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example University"}},
    "conditionsModule": {"conditions": ["Prostate Cancer"]},
    "armsInterventionsModule": {"interventions": [{"name": "177Lu-PSMA"}]},
}}]}


class FakeResponse:
    def __init__(self, payload=None, text="", status=200):
        self._payload, self.text, self.status_code = payload, text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, fail=(), ai_payload=None):
        self.fail, self.ai_payload, self.calls = set(fail), ai_payload, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        for key in self.fail:
            if key in url:
                return FakeResponse(status=503)
        if "esearch" in url:
            return FakeResponse({"esearchresult": {"idlist": ["12345"]}})
        if "efetch" in url:
            return FakeResponse(text=PUBMED_XML)
        if "europepmc" in url:
            return FakeResponse(EUROPEPMC_JSON)
        if "clinicaltrials" in url:
            return FakeResponse(CT_JSON)
        raise AssertionError(url)

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, json))
        return FakeResponse(self.ai_payload)


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")


def test_parse_pubmed_xml():
    [item] = sources.parse_pubmed_xml(PUBMED_XML)
    assert item["id"] == "pubmed:12345"
    assert item["title"].startswith("CAR-T therapy achieves complete remission")
    assert "CONCLUSIONS: CAR-T therapy" in item["abstract"]
    assert item["date"] == "2026-09-28"
    assert item["doi"] == "10.1000/ABC"
    assert item["authors"] == ["Smith J"]
    assert item["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345/"


def test_parse_europepmc_and_trials():
    first = sources.parse_europepmc(EUROPEPMC_JSON)[0]
    assert first["title"] == "An mRNA vaccine for pancreatic cancer"
    assert first["venue"] == "bioRxiv"
    assert first["url"] == "https://doi.org/10.1101/xyz"
    [trial] = sources.parse_clinical_trials(CT_JSON)
    assert trial["url"] == "https://clinicaltrials.gov/study/NCT01234567"
    assert trial["phases"] == ["Phase 2"]
    assert trial["status"] == "Not Yet Recruiting"


def test_run_research_ranks_dedupes_and_classifies():
    now = datetime(2026, 10, 5, 23, 0, tzinfo=timezone.utc)
    results = research.run_research(session=FakeSession(), lookback_days=7, max_per_source=5, now=now)
    assert results["errors"] == []
    assert results["period_start"] == "2026-09-28"
    assert results["stats"]["total"] == 3
    top = results["findings"][0]
    assert top["id"] == "pubmed:12345"
    assert "Cell Therapy" in top["categories"]
    assert "Leukemia" in top["cancer_types"]
    assert top["summary"].startswith("CAR-T therapy produced durable complete remission")
    assert results["ai_model"] is None
    assert "reviewed" in results["overview"]
    assert json.loads(json.dumps(results)) == results


def test_run_research_tolerates_source_failure():
    results = research.run_research(session=FakeSession(fail={"europepmc"}), lookback_days=7)
    assert results["errors"] == ["Europe PMC preprints: HTTPError"]
    assert results["stats"]["total"] == 2
    assert not research.all_sources_failed(results)


def test_all_sources_failed():
    results = research.run_research(session=FakeSession(fail={"eutils", "europepmc", "clinicaltrials"}))
    assert research.all_sources_failed(results)
    assert results["findings"] == []


def test_ai_summaries_applied(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    ai = {"choices": [{"message": {"content": json.dumps({
        "overview": "Promising CAR-T results.",
        "items": [{"id": "pubmed:12345", "summary": "CAR-T cured many patients.", "significance": 42}],
    })}}]}
    results = research.run_research(session=FakeSession(ai_payload=ai))
    assert results["overview"] == "Promising CAR-T results."
    assert results["ai_model"] == config.OPENAI_MODEL
    top = results["findings"][0]
    assert top["ai_summary"] == "CAR-T cured many patients."
    assert top["ai_significance"] == 10


def test_ai_failure_falls_back(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    results = research.run_research(session=FakeSession(ai_payload={"unexpected": True}))
    assert results["ai_model"] is None
    assert "reviewed" in results["overview"]


def test_save_and_load_results(tmp_path):
    path = tmp_path / "nested" / "results.json"
    data = {"generated_at": "2026-10-05T23:00:00+00:00", "findings": []}
    research.save_results(data, str(path))
    assert research.load_results(str(path)) == data
    assert research.is_valid_results(data)
    assert not research.is_valid_results({"findings": "nope"})


def test_extractive_summary_truncates():
    text = "First sentence is here. " * 50
    summary = analyzer.extractive_summary(text, max_chars=100)
    assert len(summary) <= 100
