# ResearchPilot AI

ResearchPilot searches the public [OpenAlex](https://openalex.org) catalog for scientific papers and can analyse one selected abstract with Google Gemini.

OpenAlex does not require an API key. Gemini reads `GEMINI_API_KEY` from a local `.env` file. That file is gitignored. The key is never written into the source code.

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
      ▼
Analyse with AI  (only when the paper has an abstract)
      │
      ▼
analyze_paper(title, abstract)  →  Gemini
      │
      ▼
Objective, methodology, findings, limitations
```

The browser page collects a topic and renders expandable cards. It asks Gemini for an analysis only when you click **Analyse with AI** on that card. Search, parsing, and analysis live in the `researchpilot` package, so they can be tested without starting Streamlit. An analysis is saved under the paper's OpenAlex id (or DOI, if that id is missing), so a later search cannot show it on a different paper.

OpenAlex stores abstracts as an inverted index (`word -> [positions]`), not as a paragraph. `reconstruct_abstract()` puts each word back at its position and joins them in order.

Missing fields stay empty. The page prints **Not available** for a missing author list, year, DOI, abstract, or source URL. A failed request (timeout, no connection, HTTP error, or invalid JSON) is shown as an error. A successful search with zero hits is shown as an empty result, separate from an error.

## Project layout

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit page: topic box, Search button, expandable result cards, and Analyse with AI. |
| `researchpilot/__init__.py` | Package marker and the public names (`Paper`, `OpenAlexClient`, `OpenAlexError`, `analyze_paper`). |
| `researchpilot/models.py` | `Paper` dataclass: title, authors, year, DOI, abstract, source URL, and a stable `analysis_key()`. |
| `researchpilot/abstracts.py` | Rebuilds a plain-text abstract from OpenAlex's inverted index. |
| `researchpilot/openalex.py` | HTTP client, timeouts, error translation, and JSON-to-`Paper` parsing. |
| `researchpilot/analyzer.py` | Gemini call, prompt, API error messages, and analysis cache filtering. |
| `tests/test_abstracts.py` | Unit tests for abstract reconstruction. No network. |
| `tests/test_openalex.py` | Unit tests for parsing and for timeout, HTTP, empty, and bad-JSON handling. No network. |
| `tests/test_analyzer.py` | Unit tests for Gemini analysis with a mocked client. No network and no API key. |
| `tests/test_app.py` | Checks that the Streamlit page starts and keeps an analysis on the correct paper. No network. |
| `requirements.txt` | Install list for the app and the tests. |
| `pytest.ini` | Tells pytest where the tests are and puts the project root on the import path. |
| `.gitignore` | Keeps the virtual environment, caches, and secret files out of git. |
| `README.md` | This document. |

## Dependencies

| Package | Used by | Why it is here |
| --- | --- | --- |
| `requests` | `researchpilot/openalex.py` | Sends the HTTP GET to OpenAlex and raises clear timeout and connection errors. |
| `streamlit` | `app.py` | Renders the topic input, Search button, paper cards, and AI analysis. |
| `google-genai` | `researchpilot/analyzer.py` | Calls the Gemini model `gemini-3.5-flash-lite`. |
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

Restart the app after changing `.env`. A missing key, a rate limit, or a Gemini server error is shown on that paper's card. The message does not include the key.

## What a result contains

Each result is an expandable card. The closed summary shows the title, publication year, and authors. Expand a card for the complete details:

- title
- authors
- publication year
- DOI, when OpenAlex has one
- abstract, when OpenAlex has an inverted index
- a source link, chosen in this order: landing page, PDF, open-access URL, DOI, OpenAlex work page

**View source** opens the original article or publisher page in a new browser tab. Clicking **Analyse with AI** does not redirect away from ResearchPilot.

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

A successful analysis stays on that paper when the card is collapsed or opened again. A new search does not show it under a different paper.

## Testing

The project includes automated unit tests using `pytest`.

Tests cover:

- Abstract reconstruction from OpenAlex inverted indexes.
- Paper metadata parsing.
- HTTP errors, timeouts and connection failures.
- Invalid JSON responses and empty search results.
- Gemini analysis with a mocked client, including a missing API key, rate limits, and temporary server errors.
- Keeping an analysis attached to the correct paper after the result order changes.

Run the tests using: python -m pytest -v

<img width="960" height="504" alt="image" src="https://github.com/user-attachments/assets/a3230ae8-e9f0-475f-bf80-19f8c4dae93a" />

**Latest verified result:** 32 tests passed.

The tests use mocked API responses and do not require a live network connection or a Gemini API key.
