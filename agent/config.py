"""Runtime configuration for the cancer research agent (overridable via environment variables)."""

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# How far back (in days) each weekly run looks for new research.
LOOKBACK_DAYS = _int_env("LOOKBACK_DAYS", 7)

# Maximum number of items fetched from each source per run.
MAX_RESULTS_PER_SOURCE = _int_env("MAX_RESULTS_PER_SOURCE", 40)

# Maximum number of findings kept in the published report.
MAX_FINDINGS = _int_env("MAX_FINDINGS", 60)

# HTTP settings.
HTTP_TIMEOUT = _int_env("HTTP_TIMEOUT", 30)
USER_AGENT = "Cancer-Research-AI-Agent/1.0 (+https://github.com/jcampbell1870/Cancer-Research-A.I.-Agent)"

# Optional API keys / contact details.
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
# Number of top-ranked findings sent to the language model for summarization.
AI_SUMMARY_LIMIT = _int_env("AI_SUMMARY_LIMIT", 25)

# Literature search focusing on new treatments and potential cures.
PUBMED_QUERY = (
    '(cancer[Title/Abstract] OR tumor[Title/Abstract] OR tumour[Title/Abstract] '
    'OR carcinoma[Title/Abstract] OR leukemia[Title/Abstract] OR lymphoma[Title/Abstract] '
    'OR melanoma[Title/Abstract] OR neoplasms[MeSH Terms]) '
    'AND (cure[Title/Abstract] OR curative[Title/Abstract] OR "complete response"[Title/Abstract] '
    'OR "complete remission"[Title/Abstract] OR "novel therapy"[Title/Abstract] '
    'OR immunotherapy[Title/Abstract] OR "CAR-T"[Title/Abstract] OR "cancer vaccine"[Title/Abstract] '
    'OR "gene therapy"[Title/Abstract] OR "targeted therapy"[Title/Abstract] '
    'OR "phase III"[Title/Abstract] OR "phase 3"[Title/Abstract]) '
    'AND (clinicaltrial[Filter] OR journal article[pt]) NOT review[pt]'
)

EUROPEPMC_PREPRINT_QUERY = (
    '(TITLE:cancer OR TITLE:tumor OR TITLE:tumour OR TITLE:carcinoma OR TITLE:leukemia '
    'OR TITLE:lymphoma OR TITLE:melanoma) '
    'AND (cure OR curative OR "complete response" OR "complete remission" OR immunotherapy '
    'OR "CAR-T" OR vaccine OR "gene therapy" OR "targeted therapy" OR "novel therapeutic")'
)
