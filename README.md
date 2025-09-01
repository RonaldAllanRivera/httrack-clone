# HTTrack-like Clone (Tkinter Desktop)

Lightweight Python desktop app to clone a web page into a local folder, download assets, and rewrite paths. Includes a manual review tool to remove scripts and save a cleaned HTML.

## Features
- __Desktop UI (Tkinter)__: Product, URL, download location, progress, ETA, logs, and per-asset transfers with cancel.
- __Raw main page first__: Saves the server response immediately to `index.html`.
- __Localized copy__: Saves a rewritten version (local asset paths) to `local-index.html`.
- __CSS secondary assets__: Downloads `url()` and `@import` refs (images, relative fonts) and rewrites paths in CSS.
- __Preview mode__: When enabled, limits downloads to 1 asset per type (img/js/css/video/fonts/other) and 1 CSS ref per file for a quick sanity check.
- __Script Review__: Opens `local-index.html` by default (falls back to `index.html`) and can remove selected `<script>` tags to produce `clean-local-index.html` or `clean-index.html`.
- __Ignore SSL option__: Toggle to skip SSL verification for testing.

## Quick Start (Windows)
```powershell
# From repository root
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run the desktop app
python -m app.main
```

## Usage
1. Enter Product Name and the URL to clone.
2. Choose a download location (defaults to `e:\\Sites\\`).
3. Optionally enable Preview (faster, minimal assets) and/or Ignore SSL.
4. Click Download. The UI shows status, progress, elapsed/ETA, and per-asset rows.
5. After completion, click Open Review to remove scripts and save a clean HTML file.

## Output
- `index.html` – Raw HTML of the starting URL (exact server response).
- `local-index.html` – HTML with asset paths rewritten to local files.
- `clean-local-index.html` / `clean-index.html` – Saved by the Review tool after script removal.
- Asset folders: `img/`, `js/`, `css/`, `video/`, `fonts/`, `other/`.

## Notes
- Fonts: Absolute font URLs are left as-is; relative font URLs are downloaded to `fonts/`.
- Iframes and non-stylesheet links (icons, manifests) are saved under `other/`.
- No headless rendering yet (no Playwright). Some JS-driven content may not be captured.

## Known Issues / Next Up
- Script Review UX: improve labeling, multi-select ergonomics, and add a live preview of the cleaned page.
- Heuristics: better prioritization than “first per type” in Preview.

## Project Structure
```
app/
  main.py                # Tkinter UI (download controls, assets panel, logs, review window)
  core/
    downloader.py        # Download engine, CSS processing, path rewriting
    utils.py             # Helpers (slugify, unique folder, mime -> ext, etc.)
```
