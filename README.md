# Cancer-Research-A.I.-Agent

An A.I. research agent that searches for cutting-edge cancer research and potential new cures, runs as a
[Render](https://render.com) web service, and publishes a weekly digest to **GitHub Pages**. Results are
refreshed automatically **every Monday at 7 p.m. Eastern Time**.

## How it works

| Piece | Location | What it does |
| --- | --- | --- |
| Research agent | `agent/` | Queries **PubMed** (peer-reviewed papers), **Europe PMC** (bioRxiv/medRxiv and other preprints) and **ClinicalTrials.gov** (newly registered interventional trials) for the past week, de-duplicates, ranks findings by "toward a cure" signals (complete response/remission, curative intent, phase 3, overall survival…), tags research areas and cancer types, and — when `OPENAI_API_KEY` is set — uses an LLM to write plain-language summaries, significance scores and a weekly overview. |
| Render web service | `app.py`, `render.yaml` | Flask app served with gunicorn. `GET /api/results` returns the latest results, `POST /api/refresh` (bearer token = `REFRESH_TOKEN`) runs the agent, `GET /healthz` is the health check. |
| GitHub Pages site | `docs/` | Static page that renders `docs/data/results.json` with search and filters. |
| Weekly refresh | `.github/workflows/weekly-research.yml` | Every Monday 7 p.m. ET it asks the Render service to run the agent (falling back to running the agent in the workflow), commits `docs/data/results.json` and deploys GitHub Pages. |

### Schedule and daylight saving time

GitHub Actions cron schedules are UTC-only, so the workflow is triggered at both `23:00 UTC Monday`
(7 p.m. EDT) and `00:00 UTC Tuesday` (7 p.m. EST). `agent/schedule.py` checks the current
`America/New_York` offset and only lets the run that equals Monday 7 p.m. Eastern proceed.

## Setup

1. **GitHub Pages** – *Settings → Pages → Build and deployment → Source:* **GitHub Actions**.
2. **Render** – *New → Blueprint* and select this repository; `render.yaml` creates the
   `cancer-research-ai-agent` web service and generates a `REFRESH_TOKEN`. Optionally set
   `OPENAI_API_KEY` (A.I. summaries), `NCBI_API_KEY` and `NCBI_EMAIL` (higher PubMed rate limits).
3. **Repository secrets** (*Settings → Secrets and variables → Actions*):
   - `RENDER_SERVICE_URL` – e.g. `https://cancer-research-ai-agent.onrender.com`
   - `RENDER_REFRESH_TOKEN` – the `REFRESH_TOKEN` value from Render
   - Optional: `OPENAI_API_KEY`, `NCBI_API_KEY`, `NCBI_EMAIL` (used if the workflow has to run the agent itself)
4. Run the **Weekly cancer research refresh** workflow manually once (*Actions → Run workflow*) to publish the
   first results. After that it runs automatically every Monday at 7 p.m. Eastern.

### Configuration (environment variables)

| Variable | Default | Description |
| --- | --- | --- |
| `LOOKBACK_DAYS` | `7` | Days of research to search each run |
| `MAX_RESULTS_PER_SOURCE` | `40` | Items fetched per source |
| `MAX_FINDINGS` | `60` | Findings kept in the report |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | – / `gpt-4o-mini` / OpenAI | Optional LLM summaries (any OpenAI-compatible API) |
| `AI_SUMMARY_LIMIT` | `25` | Top findings sent to the LLM |
| `NCBI_API_KEY`, `NCBI_EMAIL` | – | Optional PubMed E-utilities credentials |
| `REFRESH_TOKEN` | – | Required to enable `POST /api/refresh` on the web service |
| `RESULTS_PATH` | `docs/data/results.json` | Where the web service stores results |

## Local development

```bash
pip install -r requirements-dev.txt
python -m pytest -q                                   # run tests
python -m agent --output docs/data/results.json       # run the agent once
REFRESH_TOKEN=dev python app.py                       # start the web service on :5000
python -m http.server -d docs 8000                    # preview the GitHub Pages site
```

> **Disclaimer:** This project aggregates research automatically for informational purposes only. It is not
> medical advice. Preprints are not peer reviewed and early results may not hold up.
