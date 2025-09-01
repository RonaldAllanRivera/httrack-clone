# HTTrack-like Clone (Tkinter Desktop)

Lightweight Python desktop app to clone a web page into a local folder, download assets, and rewrite paths. Includes automatic generation of `content.php` with product name placeholder and CTA link updates.

## Features
- __Desktop UI (Tkinter)__: Product, URL, download location, progress, ETA, logs, and per-asset transfers with cancel.
- __Raw main page first__: Saves the server response immediately to `index.html`.
- __Localized copy__: Saves a rewritten version (local asset paths) to `local-index.html`.
- __CSS secondary assets__: Robust resolver for `url()` and `@import` refs (tries CSS URL, page URL, and host roots). Saves non-font CSS assets to `css_img/` and rewrites CSS paths (relative fonts only).
- __Preview mode__: When enabled, limits downloads to 1 asset per type (img/js/css/video/fonts/other) and 1 CSS ref per file for a quick sanity check.
- __Automatic PHP content__: Generates `content.php` with product name placeholder and CTA link updates.
- __Error Summary + Copy__: Aggregates `ERROR`/`WARNING` lines and provides a "Copy Errors" button to copy them to clipboard.
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
5. After completion, `content.php` is generated automatically using your Product Name and CTA link placeholders.
6. Use the "Copy Errors" button to copy a consolidated error list for quick sharing.

## Output
- `index.html` – Raw HTML of the starting URL (exact server response).
- `local-index.html` – HTML with asset paths rewritten to local files.
- `content.php` – HTML with product name replaced by `<?=$productName;?>` and anchors with text containing "order" pointing href to `<?php echo $ctaLink; ?>`.
  Also inserts `<?= $headers; ?>` on the next line after the closing `</title>` tag.
- Asset folders: `img/`, `js/`, `css/`, `video/`, `fonts/`, `css_img/`, `other/`.

## Notes
- Fonts: Absolute font URLs are left as-is; relative font URLs are downloaded to `fonts/`.
- CSS images/sprites/backgrounds referenced from CSS are saved under `css_img/` and CSS files are rewritten to point to these local paths.
- Iframes and non-stylesheet links (icons, manifests) are saved under `other/`.
- No headless rendering yet (no Playwright). Some JS-driven content may not be captured.
- Error Summary collects log lines that begin with `ERROR` or `WARNING` and appends them at the end of each run for easy copying.

## Known Issues / Next Up
- Heuristics: better prioritization than “first per type” in Preview.

## Project Structure
```
app/
  main.py                # Tkinter UI (download controls, assets panel, logs)
  core/
    downloader.py        # Download engine, CSS processing, path rewriting
    utils.py             # Helpers (slugify, unique folder, mime -> ext, etc.)
```
