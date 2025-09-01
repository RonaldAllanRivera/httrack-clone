# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [2025-09-01]

- Added: Save raw server response immediately as `index.html` on first download.
- Added: Save localized HTML (with rewritten local asset paths) as `local-index.html`.
- Added: Automatically generate `content.php` from localized/raw HTML. Replaces product name with `<?=$productName;?>` and sets anchors whose text contains "order" to `<?php echo $ctaLink; ?>`.
- Added: Preview mode limits to 1 asset per type and 1 CSS reference per CSS file for faster sanity checks.
- Added: Per-asset progress rows with individual Cancel buttons in the UI.
- Added: "Ignore SSL errors (insecure)" option for testing.
- Changed: Tkinter UI layout to match the design (full-width status/progress, separators, aligned scrollbars, improved status colors).
- Fixed: UnboundLocalError arising from `total` shadowing in downloader progress math.
- Fixed: Preview now targets localized HTML (`local-index.html`) instead of raw.
- Removed: Manual Script Review feature and related outputs (`clean-local-index.html`, `clean-index.html`).
