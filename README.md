# ResearchPilot AI — Phase 1

Phase 1 is a small Python application that searches the public [OpenAlex](https://openalex.org) catalog for scientific papers on a research topic and shows the results in a Streamlit page.

It does not call a language model, and it does not use RAG, LangGraph, or extra agents. OpenAlex does not require an API key.

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
Up to 10 Paper cards
```

The browser page only collects a topic and renders cards. All OpenAlex details live in the `researchpilot` package, so the same search function can be tested without starting Streamlit.

OpenAlex stores abstracts as an inverted index (`word -> [positions]`), not as a paragraph. `reconstruct_abstract()` puts each word back at its position and joins them in order.

Missing fields stay empty. The page prints **Not available** for a missing author list, year, DOI, abstract, or source URL. A failed request (timeout, no connection, HTTP error, or invalid JSON) is shown as an error. A successful search with zero hits is shown as an empty result, separate from an error.

## Project layout

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit page: topic box, Search button, result cards, and error messages. |
| `researchpilot/__init__.py` | Package marker and the public names (`Paper`, `OpenAlexClient`, `OpenAlexError`). |
| `researchpilot/models.py` | `Paper` dataclass: title, authors, year, DOI, abstract, source URL. |
| `researchpilot/abstracts.py` | Rebuilds a plain-text abstract from OpenAlex's inverted index. |
| `researchpilot/openalex.py` | HTTP client, timeouts, error translation, and JSON-to-`Paper` parsing. |
| `tests/test_abstracts.py` | Unit tests for abstract reconstruction. No network. |
| `tests/test_openalex.py` | Unit tests for parsing and for timeout, HTTP, empty, and bad-JSON handling. No network. |
| `requirements.txt` | Install list for the app and the tests. |
| `pytest.ini` | Tells pytest where the tests are and puts the project root on the import path. |
| `.gitignore` | Keeps the virtual environment, caches, and secret files out of git. |
| `README.md` | This document. |

## Dependencies

| Package | Used by | Why it is here |
| --- | --- | --- |
| `requests` | `researchpilot/openalex.py` | Sends the HTTP GET to OpenAlex and raises clear timeout and connection errors. |
| `streamlit` | `app.py` | Renders the topic input, Search button, and paper cards in a local browser page. |
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

There is no API key in this phase.

## What a result contains

Each card shows:

- title
- authors
- publication year
- DOI, when OpenAlex has one
- abstract, when OpenAlex has an inverted index
- a source link, chosen in this order: landing page, PDF, open-access URL, DOI, OpenAlex work page

The search asks for at most 10 works, sorted by OpenAlex relevance for the topic text.

<img width="960" height="504" alt="image" src="https://github.com/user-attachments/assets/eccbe11a-b76d-4d24-9340-99526dfd6981" />

