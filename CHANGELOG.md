# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [2025-09-01]

- Added: Save raw server response immediately as `index.html` on first download.
- Added: Save localized HTML (with rewritten local asset paths) as `local-index.html`.
- Added: Script Review opens `local-index.html` by default (falls back to `index.html`) and saves cleaned output as `clean-local-index.html` or `clean-index.html`.
- Added: Preview mode limits to 1 asset per type and 1 CSS reference per CSS file for faster sanity checks.
- Added: Per-asset progress rows with individual Cancel buttons in the UI.
- Added: "Ignore SSL errors (insecure)" option for testing.
- Changed: Tkinter UI layout to match the design (full-width status/progress, separators, aligned scrollbars, improved status colors).
- Fixed: UnboundLocalError arising from `total` shadowing in downloader progress math.
- Fixed: Preview/Review now targets localized HTML (`local-index.html`) instead of raw.
