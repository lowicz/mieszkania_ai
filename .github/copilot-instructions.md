# Copilot instructions (mieszkania_ai)

## Repo purpose
- This repo is **content-first**: it stores Polish, critical Markdown reports comparing apartment listings in Poznań.
- Inputs are typically a list of Otodom links in `mieszkania.txt`.
- Output reports live at repo root (examples: `analiza_mieszkan_poznan_gpt52.md`, `analiza_mieszkan_poznan_gemini.md`, `analiza_mieszkan_poznan_opus.md`).

## Writing style (must match existing reports)
- Write in **Polish**, factual and critical; avoid marketing tone.
- **Do not invent data**. If the listing doesn’t provide something, write `brak danych` and add it to questions.
- Call out red flags directly (budget overrun, missing parking cost, legal uncertainty, noise risks, last floor/no elevator, etc.).

## Report structure (preferred)
- Header with **date** (ISO ok) and decision goal (family/couple, 3 rooms, budget).
- Standardized extraction per listing (same fields across rows): price, price/m², size, rooms, year, floor/elevator, finish state, layout, outdoor space, parking + cost, fees, legal status, pros/cons, missing data.
- Required comparison table and a **0–10 weighted score** per listing.
- Required **TOP 3** shortlist (only among listings that meet hard constraints).
- Required seller questions + viewing checklist.

## Hard constraints used in this repo
- Hard requirement: **3-4 rooms** (offers that are not 3-room or 4-room should be explicitly marked as rejected).
- Budget is **all-in** (price + finish/remodel + transaction costs like PCC/notary/fees + parking/storage if required).
- Primary + secondary market are allowed; explicitly note when PCC likely applies (secondary) vs not (primary).

## Conventions for files/edits
- Keep reports as single Markdown files at repo root; avoid adding extra docs unless requested.
- Always write each new analysis to a **new** Markdown file (do not append to or overwrite existing reports).
- Naming pattern: `analiza_mieszkan_poznan_<tag>.md` (keep `<tag>` unique per run; optionally include date like `2026-01-03_gpt52`).

## Directory structure
- `mieszkania.txt` — input list of links (Otodom + ronson.pl supported).
- `analiza1/`, `analiza2/`, `analiza3/` — archived analysis batches (Markdown reports).
- `tools/` — Python scraping utilities (e.g., `generate_ronson_grunwald_report.py` for Ronson developer listings).

## Tools & automation
- `tools/generate_ronson_grunwald_report.py` scrapes https://ronson.pl/inwestycja/grunwald-miedzy-drzewami/, extracts unit cards, parses details pages, and writes a scored Markdown report.
- Run with: `python tools/generate_ronson_grunwald_report.py` (requires `requests`, `beautifulsoup4`, `lxml`).
- The script uses dataclass `Unit` to normalize listing data; scoring logic is in `_score_unit()`.
