# ResearchPilot AI

ResearchPilot searches the public [OpenAlex](https://openalex.org) catalog for scientific papers, analyses one selected abstract with Google Gemini, and compares three to five abstracts to explore author-reported limits and possible research gaps.

OpenAlex does not require an API key. Gemini reads `GEMINI_API_KEY` from a local `.env` file. That file is gitignored. The key is never written into the source code.

## What the app does

**Phase 1 — Search.** Enter a research topic. The app asks OpenAlex for up to 10 relevant works and shows each one as an expandable card: title, authors, year, DOI, abstract, and a source link.

**Phase 2 — Analyse one paper.** On a card that has an abstract, **Analyse with AI** sends that title and abstract to Gemini once. The result has four sections: Research Objective, Methodology, Key Findings, and Limitations. Limitations separate author-reported limits from AI hypotheses.

**Phase 3 — Compare 3 to 5 papers.** Each card with an abstract has **Select for comparison**. Papers without an abstract cannot be selected. When 3 to 5 valid papers are selected, **Compare Selected Papers** sends those abstracts in one Gemini request. The report has six sections:

1. Research Objectives
2. Methodologies
3. Key Findings
4. Author-Reported Limitations
5. Author-Reported Research Gaps
6. AI-Inferred Potential Research Gaps

Author-reported limitations and gaps include only statements the abstracts support. If the abstracts do not state a limitation or a gap, that section says so and does not cite papers for the absence. AI-inferred gaps are hypotheses grounded in the selected abstracts. They are not findings reported by the authors and they are not gaps established across the research literature.

## Architecture

```
Research topic
      │
      ▼
Streamlit page (app.py)
      │
      ▼
OpenAlexClient.search_papers()
      │
      ▼
GET https://api.openalex.org/works?search=...&per-page=10
      │
      ▼
parse_work()  +  reconstruct_abstract()
      │
      ▼
Up to 10 expandable paper cards
      │
      ├── Analyse with AI  →  analyze_paper()  →  Gemini
      │
      └── Select 3 to 5 abstracts
                │
                ▼
          compare_papers()  →  one Gemini request
                │
                ▼
          present_comparison()  →  six labelled sections
```

The browser page collects a topic and renders expandable cards. It asks Gemini for a single-paper analysis only when you click **Analyse with AI**. It asks Gemini for a comparison only when you click **Compare Selected Papers**. Changing a checkbox does not send a request. Search, parsing, analysis, and comparison live in the `researchpilot` package, so they can be tested without starting Streamlit.

OpenAlex stores abstracts as an inverted index (`word -> [positions]`), not as a paragraph. `reconstruct_abstract()` puts each word back at its position and joins them in order.

Missing fields stay empty. The page prints **Not available** for a missing author list, year, DOI, abstract, or source URL. A failed request (timeout, no connection, HTTP error, or invalid JSON) is shown as an error. A successful search with zero hits is shown as an empty result, separate from an error.

## Paper identity, selection, and duplicates

Each paper has a stable `analysis_key()`. OpenAlex id is preferred, then DOI, then title and year. Card position is not used, so a saved analysis or comparison cannot appear on a different paper that happens to occupy the same slot.

A comparison requires 3 to 5 papers. Each selected paper must have a non-empty abstract and its own identifier. Two selected papers that share an identifier are rejected. A paper with no abstract shows a notice on that card, `"Title" has no abstract, so it cannot be selected for comparison.`, and has no checkbox.

Search results are collapsed only when two records are the same publication by identifier: the same OpenAlex id, or the same DOI. The first record is kept. Papers that share a title and authors but have different OpenAlex ids, DOIs, and years stay separate, because those can be distinct publications.

## Comparison cache and a new search

A successful comparison is stored with the exact selected papers and a hash of their abstract text. The same set is reused in any order, and returning to an earlier selection shows that saved report without another Gemini request. A different set of papers, or the same papers after an abstract changes, does not show the old report.

A new search clears the checkboxes and hides the current report. Single-paper analyses for papers that are still in the new results are kept. Comparison results whose papers or abstracts are no longer current are dropped.

## API errors and retry

Gemini errors are shown without the API key and without the provider's raw error text. The message distinguishes:

- a missing API key
- an exhausted quota
- rate limiting
- a rejected API key
- a missing model
- an invalid or oversized request
- a timeout
- a temporary server error
- a malformed comparison response

A failed comparison stays on the current selection. Click **Compare Selected Papers** again to retry. The app does not retry Gemini in a loop. A successful comparison is not requested again until the selection or the abstract text changes.

## Project layout

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit page: search, expandable cards, single-paper analysis, and multi-paper comparison. |
| `researchpilot/__init__.py` | Package marker and the public names (`Paper`, `OpenAlexClient`, `OpenAlexError`, `analyze_paper`). |
| `researchpilot/models.py` | `Paper` dataclass: title, authors, year, DOI, abstract, source URL, and a stable `analysis_key()`. |
| `researchpilot/abstracts.py` | Rebuilds a plain-text abstract from OpenAlex's inverted index. |
| `researchpilot/openalex.py` | HTTP client, timeouts, error translation, JSON-to-`Paper` parsing, and identifier deduplication. |
| `researchpilot/analyzer.py` | Single-paper Gemini call, prompt, API error messages, and analysis cache filtering. |
| `researchpilot/comparison.py` | Selection rules, one comparison request, response validation, display sections, and comparison cache identity. |
| `tests/test_abstracts.py` | Unit tests for abstract reconstruction. No network. |
| `tests/test_openalex.py` | Unit tests for parsing, duplicates, and timeout, HTTP, empty, and bad-JSON handling. No network. |
| `tests/test_analyzer.py` | Unit tests for Gemini analysis with a mocked client. No network and no API key. |
| `tests/test_comparison.py` | Unit tests for selection, mocked comparison, absence statements, and cache identity. No network. |
| `tests/test_app.py` | Streamlit checks for analysis, selection, cache reuse, search resets, and retry. No network. |
| `requirements.txt` | Install list for the app and the tests. |
| `pytest.ini` | Tells pytest where the tests are and puts the project root on the import path. |
| `.gitignore` | Keeps the virtual environment, caches, and secret files out of git. |
| `README.md` | This document. |

## Dependencies

| Package | Used by | Why it is here |
| --- | --- | --- |
| `requests` | `researchpilot/openalex.py` | Sends the HTTP GET to OpenAlex and raises clear timeout and connection errors. |
| `streamlit` | `app.py` | Renders the topic input, Search button, paper cards, analysis, and comparison. |
| `google-genai` | `researchpilot/analyzer.py` | Calls the Gemini model `gemini-3.5-flash-lite`. Comparison uses the same client. |
| `python-dotenv` | `researchpilot/analyzer.py` | Loads `GEMINI_API_KEY` from `.env` into the environment. |
| `pytest` | `tests/` | Runs the unit tests. The running app does not import pytest. |

Python 3.10 or newer is required. These commands were written for Windows PowerShell.

## Setup and run (Windows PowerShell)

From the project folder:

```powershell
Set-Location D:\ResearchPilot-AI
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest
streamlit run app.py
```

If activation is blocked by the execution policy, allow scripts for the current window only and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Streamlit opens a local page (usually http://localhost:8501). Type a topic such as `graph neural networks` and click **Search**. Leave the terminal running while you use the page. Stop it with Ctrl+C.

You can run the app without activating the environment:

```powershell
D:\ResearchPilot-AI\.venv\Scripts\python.exe -m pytest
D:\ResearchPilot-AI\.venv\Scripts\streamlit.exe run app.py
```

## Optional contact email

OpenAlex serves anonymous requests. Adding your email puts the app in the [polite pool](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication), which has a higher rate limit. Set it in the shell for the current session. Do not commit it and do not put it in the code.

```powershell
$env:OPENALEX_MAILTO = "you@university.edu"
streamlit run app.py
```

## Gemini API key

Create `.env` in the project folder. Do not commit it.

```text
GEMINI_API_KEY=your-key-here
```

Restart the app after changing `.env`. A missing key, a quota limit, a rate limit, or a Gemini server error is shown in the app. The message does not include the key or the provider's raw error text.

## What a result contains

Each result is an expandable card inside its own border. The card title shows the index, title, publication year, and authors. Expand **Abstract, source, and analysis** for the complete details:

- title
- authors
- publication year
- DOI, when OpenAlex has one
- abstract, when OpenAlex has an inverted index
- a source link, chosen in this order: landing page, PDF, open-access URL, DOI, OpenAlex work page

**View source** opens the original article or publisher page in a new browser tab. Clicking **Analyse with AI** or **Compare Selected Papers** does not redirect away from ResearchPilot.

<img width="960" height="504" alt="image" src="https://github.com/user-attachments/assets/eccbe11a-b76d-4d24-9340-99526dfd6981" />

The search asks for at most 10 works, sorted by OpenAlex relevance for the topic text.

On a paper that has an abstract, **Analyse with AI** asks Gemini for four sections:

1. Research Objective
2. Methodology
3. Key Findings
4. Limitations

Limitations has two parts:

- **Author-reported limitations:** only limits the abstract explicitly states. If none are stated, the analysis says "Not specified in the abstract."
- **Potential limitations to investigate:** up to three methodological questions grounded in the abstract. These are labeled as AI-generated hypotheses, not established weaknesses or claims made by the authors.

The model uses only the title and abstract. It does not invent datasets, sample sizes, results, or experiments. If the abstract is too thin for a meaningful hypothesis, the analysis says so instead of offering generic criticism. The card shows this disclaimer:

> AI-generated analysis based on the title and abstract only. Verify important claims against the full research paper.

A successful analysis stays on that paper when the card is collapsed or opened again. A new search does not show it under a different paper. A failed analysis can be retried with **Retry analysis**.

Below the cards, a counter shows how many papers are selected. **Compare Selected Papers** is enabled only for 3 to 5 papers with abstracts and distinct identifiers. The report lists each claim with the titles of the papers it cites and states that the claim is AI-generated from the selected abstracts. The comparison always shows this disclaimer, independent of the model text:

> AI-generated comparison based only on the selected titles and abstracts. Verify claims against the full papers. This comparison cannot establish gaps across the entire research literature.

## Research limitations

- Analysis and comparison use titles and abstracts only. They do not read the full papers.
- AI-generated interpretations need to be checked against the full papers.
- AI-inferred gaps are hypotheses. They are not proven gaps in the research literature.
- Gemini availability, quota, and rate limits can block or delay a request. Retry from the button after the message shown in the app.

## Testing

The project includes automated unit tests using `pytest`.

Tests cover:

- Abstract reconstruction from OpenAlex inverted indexes.
- Paper metadata parsing.
- HTTP errors, timeouts and connection failures.
- Invalid JSON responses and empty search results.
- Keeping distinct papers that share a title, and collapsing records that share an OpenAlex id or DOI.
- Gemini analysis with a mocked client, including a missing API key, quota, rate limits, authentication failures, and temporary server errors.
- Keeping an analysis attached to the correct paper after the result order changes.
- Comparison selection, mocked Gemini comparison, absence statements, cache identity, selection changes, new searches, and retry.

Run the tests using:

<img width="960" height="504" alt="image" src="https://github.com/user-attachments/assets/a3230ae8-e9f0-475f-bf80-19f8c4dae93a" />

**Latest verified result:** 65 tests passed.

The tests use mocked API responses and do not require a live network connection or a Gemini API key.
