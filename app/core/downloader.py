from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
import re
import hashlib
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import cssutils
import httpx
from bs4 import BeautifulSoup

from .utils import slugify, ensure_unique_dir, guess_extension_from_mime, is_relative_url


cssutils.log.setLevel("FATAL")  # silence cssutils warnings


@dataclass
class DownloadResult:
    product_name: str
    slug: str
    root: Path
    folder: Path
    index_path: Path
    counts: Dict[str, int]


ASSET_FOLDERS = {
    "img": "img",
    "js": "js",
    "css": "css",
    "video": "video",
    "fonts": "fonts",
    "other": "other",
}


def ensure_subfolders(base: Path) -> None:
    for sub in ASSET_FOLDERS.values():
        (base / sub).mkdir(parents=True, exist_ok=True)


def normalize_filename(url: str, content_type: Optional[str]) -> str:
    parsed = urlparse(url)
    path = parsed.path
    name = os.path.basename(path) or "file"
    if "." not in name:
        ext = guess_extension_from_mime(content_type)
        if ext:
            name += ext
    # Avoid collisions for URLs that differ only by query (e.g., Google Fonts css2)
    if parsed.query:
        h = hashlib.sha1(parsed.query.encode("utf-8", errors="ignore")).hexdigest()[:8]
        if "." in name:
            base, extn = name.rsplit(".", 1)
            name = f"{base}-{h}.{extn}"
        else:
            name = f"{name}-{h}"
    return name


async def fetch_text(client: httpx.AsyncClient, url: str) -> Tuple[str, Optional[str]]:
    r = await client.get(url, follow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.text, r.headers.get("content-type")


async def fetch_bytes(client: httpx.AsyncClient, url: str) -> Tuple[bytes, Optional[str]]:
    r = await client.get(url, follow_redirects=True, timeout=None)
    r.raise_for_status()
    return r.content, r.headers.get("content-type")


def collect_assets(soup: BeautifulSoup, base_url: str) -> Dict[str, Set[str]]:
    assets: Dict[str, Set[str]] = {k: set() for k in ASSET_FOLDERS.keys()}

    # Images and <source> (picture vs video)
    for tag in soup.find_all(["img", "source"]):
        parent_name = tag.parent.name.lower() if tag.parent and hasattr(tag.parent, "name") and tag.parent.name else ""
        typ = (tag.get("type") or "").lower()
        is_video_source = (tag.name == "source" and (parent_name in {"video", "audio"} or typ.startswith("video/")))
        if is_video_source:
            if tag.has_attr("src"):
                assets["video"].add(urljoin(base_url, tag.get("src")))
            # Usually video <source> doesn't use srcset; ignore if present
            continue
        # Treat as image otherwise
        if tag.has_attr("src"):
            assets["img"].add(urljoin(base_url, tag.get("src")))
        if tag.has_attr("srcset"):
            parts = [p.strip() for p in tag.get("srcset").split(",") if p.strip()]
            for p in parts:
                u = p.split()[0]
                assets["img"].add(urljoin(base_url, u))

    # JS
    for tag in soup.find_all("script"):
        src = tag.get("src")
        if src:
            assets["js"].add(urljoin(base_url, src))

    # CSS and preload
    for tag in soup.find_all("link"):
        rels = [r.lower() for r in (tag.get("rel") or [""])]
        href = tag.get("href")
        if not href:
            continue
        if any(r == "stylesheet" for r in rels):
            assets["css"].add(urljoin(base_url, href))
            continue
        # Treat preload as CSS if as=style
        if "preload" in rels and (tag.get("as") or "").lower() == "style":
            assets["css"].add(urljoin(base_url, href))
            continue

    # Videos and tracks (exclude <source> here; handled above)
    for tag in soup.find_all(["video", "track"]):
        src = tag.get("src")
        if src:
            assets["video"].add(urljoin(base_url, src))

    # Icons / manifests (skip preconnect, dns-prefetch, etc.)
    for tag in soup.find_all("link"):
        rels = [r.lower() for r in (tag.get("rel") or [])]
        href = tag.get("href")
        if not href:
            continue
        if any(r in rels for r in ["stylesheet", "preload"]):
            continue
        if any(r in rels for r in ["preconnect", "dns-prefetch", "prefetch", "prerender", "modulepreload"]):
            continue
        if any(r in rels for r in ["icon", "shortcut icon", "apple-touch-icon", "manifest"]):
            assets["other"].add(urljoin(base_url, href))

    # Iframes as other assets
    for tag in soup.find_all("iframe"):
        src = tag.get("src")
        if src:
            assets["other"].add(urljoin(base_url, src))

    return assets


async def download_assets(
    client: httpx.AsyncClient,
    assets: Dict[str, Set[str]],
    base_folder: Path,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
    asset_cb: Optional[Callable[[str, str, str, Dict[str, int | str | None]], None]] = None,
    asset_cancel_cb: Optional[Callable[[str, str], bool]] = None,
) -> Dict[str, Dict[str, str]]:
    """
    Returns mapping per type: {url: relative_local_path}
    """
    url_to_rel_by_type: Dict[str, Dict[str, str]] = {k: {} for k in assets.keys()}

    sem = asyncio.Semaphore(10)
    assets_total = sum(len(urls) for urls in assets.values())
    completed = 0

    async def _dl(url: str, kind: str):
        try:
            if cancel_cb and cancel_cb():
                if log_cb:
                    log_cb(f"CANCELLED before request: [{kind}] {url}")
                return
            if log_cb:
                log_cb(f"Downloading [{kind}] {url}")
            # Stream the response to report progress and support per-asset cancel
            async with sem:
                async with client.stream("GET", url, follow_redirects=True, timeout=None) as r:
                    r.raise_for_status()
                    content_length = None
                    try:
                        content_length = int(r.headers.get("content-length")) if r.headers.get("content-length") else None
                    except Exception:
                        content_length = None
                    if asset_cb:
                        asset_cb("start", kind, url, {"total": content_length})

                    # Prepare output path
                    ctype = r.headers.get("content-type")
                    name = normalize_filename(url, ctype)
                    rel = f"{ASSET_FOLDERS[kind]}/{name}"
                    out = base_folder / rel
                    out.parent.mkdir(parents=True, exist_ok=True)

                    bytes_read = 0
                    cancelled_midway = False
                    try:
                        with open(out, "wb") as f:
                            async for chunk in r.aiter_bytes(chunk_size=65536):
                                # Check global or per-asset cancellation
                                if (cancel_cb and cancel_cb()) or (asset_cancel_cb and asset_cancel_cb(kind, url)):
                                    cancelled_midway = True
                                    break
                                if not chunk:
                                    continue
                                f.write(chunk)
                                bytes_read += len(chunk)
                                if asset_cb:
                                    asset_cb("progress", kind, url, {"read": bytes_read, "total": content_length})
                    finally:
                        if cancelled_midway:
                            try:
                                out.unlink(missing_ok=True)
                            except Exception:
                                pass

                    if cancelled_midway:
                        if asset_cb:
                            asset_cb("cancelled", kind, url, {})
                        if log_cb:
                            log_cb(f"CANCELLED during download: [{kind}] {url}")
                        return

            # Record mapping on success
            url_to_rel_by_type[kind][url] = rel
            if log_cb:
                log_cb(f"Saved     [{kind}] {rel}")
            if asset_cb:
                asset_cb("done", kind, url, {"rel": rel})
        except httpx.HTTPStatusError as e:
            # HTTP error with status code
            status = getattr(e.response, "status_code", None)
            if log_cb:
                log_cb(f"ERROR     [{kind}] {url} ({status})")
            if asset_cb:
                asset_cb("error", kind, url, {"status": status})
        except Exception as e:
            # Other failures
            if log_cb:
                log_cb(f"ERROR     [{kind}] {url} ({type(e).__name__})")
            if asset_cb:
                asset_cb("error", kind, url, {})
        finally:
            nonlocal completed
            completed += 1
            if progress_cb:
                progress_cb(completed, assets_total, "assets")

    tasks = []
    for kind, urls in assets.items():
        for url in urls:
            tasks.append(asyncio.create_task(_dl(url, kind)))

    if tasks:
        if progress_cb:
            progress_cb(0, assets_total, "assets")
        await asyncio.gather(*tasks)

    return url_to_rel_by_type


def is_font_url(url: str) -> bool:
    lower = url.lower()
    return any(lower.endswith(ext) for ext in [".woff", ".woff2", ".ttf", ".otf", ".eot"])


async def process_css_files(
    client: httpx.AsyncClient,
    css_map: Dict[str, str],  # url -> rel_path
    base_folder: Path,
    page_base_url: str,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
    limit_refs: Optional[int] = None,
    asset_cb: Optional[Callable[[str, str, str, Dict[str, int | str | None]], None]] = None,
    asset_cancel_cb: Optional[Callable[[str, str], bool]] = None,
) -> None:
    # For each CSS, parse url() and @import, download relative assets, rewrite paths
    # First pass: count total refs for progress
    total_refs = 0
    for _, rel_path in css_map.items():
        css_file_path = base_folder / rel_path
        try:
            css_text = css_file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            try:
                css_text = css_file_path.read_text(encoding="latin-1", errors="ignore")
            except Exception:
                continue

        sheet = cssutils.parseString(css_text)
        # Count refs in this CSS
        count_in_css = 0
        for rule in sheet:
            if rule.type == rule.IMPORT_RULE:
                count_in_css += 1
            if rule.type == rule.STYLE_RULE:
                for prop in rule.style:
                    if "url(" in prop.value:
                        for part in prop.value.split("url("):
                            if ")" in part:
                                count_in_css += 1
        if limit_refs is not None:
            total_refs += min(count_in_css, limit_refs)
        else:
            total_refs += count_in_css

    completed_refs = 0
    if progress_cb and total_refs > 0:
        progress_cb(0, total_refs, "css-assets")

    for css_url, rel_path in css_map.items():
        if cancel_cb and cancel_cb():
            if log_cb:
                log_cb("CANCELLED before CSS processing")
            break
        css_file_path = base_folder / rel_path
        try:
            css_text = css_file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            try:
                css_text = css_file_path.read_text(encoding="latin-1", errors="ignore")
            except Exception:
                continue

        sheet = cssutils.parseString(css_text)
        downloaded: Dict[str, str] = {}

        async def download_ref(ref_url: str) -> Optional[str]:
            abs_url = urljoin(css_url, ref_url)
            try:
                if cancel_cb and cancel_cb():
                    if log_cb:
                        log_cb(f"CANCELLED css ref: {ref_url}")
                    return None
                # Stream CSS ref
                async with client.stream("GET", abs_url, follow_redirects=True, timeout=None) as r:
                    r.raise_for_status()
                    total = None
                    try:
                        total = int(r.headers.get("content-length")) if r.headers.get("content-length") else None
                    except Exception:
                        total = None
                    if asset_cb:
                        asset_cb("start", "css", abs_url, {"total": total})

                    # Decide target folder by extension heuristic
                    # Only download fonts if the original ref was relative; otherwise skip fonts
                    if is_font_url(abs_url):
                        if not is_relative_url(ref_url):
                            return None
                        kind_folder = ASSET_FOLDERS["fonts"]
                    else:
                        kind_folder = ASSET_FOLDERS["img"]
                    ctype = r.headers.get("content-type")
                    name = normalize_filename(abs_url, ctype)
                    rel = f"{kind_folder}/{name}"
                    out = base_folder / rel

                    bytes_read = 0
                    cancelled_midway = False
                    with open(out, "wb") as f:
                        async for chunk in r.aiter_bytes(chunk_size=65536):
                            if (cancel_cb and cancel_cb()) or (asset_cancel_cb and asset_cancel_cb("css", abs_url)):
                                cancelled_midway = True
                                break
                            if not chunk:
                                continue
                            f.write(chunk)
                            bytes_read += len(chunk)
                            if asset_cb:
                                asset_cb("progress", "css", abs_url, {"read": bytes_read, "total": total})

                    if cancelled_midway:
                        try:
                            out.unlink(missing_ok=True)
                        except Exception:
                            pass
                        if asset_cb:
                            asset_cb("cancelled", "css", abs_url, {})
                        if log_cb:
                            log_cb(f"CANCELLED css ref: {ref_url}")
                        return None

                    downloaded[abs_url] = rel
                    if log_cb:
                        log_cb(f"Saved     [css] {rel}")
                    if asset_cb:
                        asset_cb("done", "css", abs_url, {"rel": rel})
                    return rel
            except Exception:
                if log_cb:
                    log_cb(f"ERROR     [css] {ref_url}")
                if asset_cb:
                    asset_cb("error", "css", abs_url, {})
                return None

        # Collect refs
        refs: List[str] = []
        for rule in sheet:
            if rule.type == rule.IMPORT_RULE:
                href = rule.href
                if href:
                    refs.append(href)
            if rule.type == rule.STYLE_RULE:
                for prop in rule.style:
                    if "url(" in prop.value:
                        val = prop.value
                        # naive extract: url(xxx)
                        parts = val.split("url(")
                        for part in parts[1:]:
                            end = part.find(")")
                            if end != -1:
                                url_candidate = part[:end].strip("\"'")
                                refs.append(url_candidate)
        if limit_refs is not None:
            refs = refs[:limit_refs]

        # Download and rewrite
        for ref in refs:
            if ref.startswith("data:"):
                continue
            rel = await download_ref(ref)
            if rel:
                css_text = css_text.replace(ref, rel)
            completed_refs += 1
            if progress_cb and total_refs > 0:
                progress_cb(completed_refs, total_refs, "css-assets")

        css_file_path.write_text(css_text, encoding="utf-8", errors="ignore")


def rewrite_html_paths(
    soup: BeautifulSoup,
    base_url: str,
    mapping_by_type: Dict[str, Dict[str, str]],
) -> None:
    # Images
    for tag in soup.find_all(["img", "source"]):
        if tag.has_attr("src"):
            absu = urljoin(base_url, tag.get("src"))
            rel = mapping_by_type["img"].get(absu)
            if rel:
                tag["src"] = rel
        if tag.has_attr("srcset"):
            parts = [p.strip() for p in tag.get("srcset").split(",") if p.strip()]
            new_parts = []
            for p in parts:
                comps = p.split()
                u = comps[0]
                absu = urljoin(base_url, u)
                rel = mapping_by_type["img"].get(absu)
                if rel:
                    comps[0] = rel
                new_parts.append(" ".join(comps))
            if new_parts:
                tag["srcset"] = ", ".join(new_parts)

    # JS
    for tag in soup.find_all("script"):
        src = tag.get("src")
        if src:
            absu = urljoin(base_url, src)
            rel = mapping_by_type["js"].get(absu)
            if rel:
                tag["src"] = rel

    # CSS
    for tag in soup.find_all("link"):
        rels = (tag.get("rel") or [""])
        if any(r.lower() == "stylesheet" for r in rels):
            href = tag.get("href")
            if href:
                absu = urljoin(base_url, href)
                r = mapping_by_type["css"].get(absu)
                if r:
                    tag["href"] = r
        else:
            href = tag.get("href")
            if href:
                absu = urljoin(base_url, href)
                r = mapping_by_type["other"].get(absu)
                if r:
                    tag["href"] = r

    # Video / track
    for tag in soup.find_all(["video", "source", "track"]):
        src = tag.get("src")
        if src:
            absu = urljoin(base_url, src)
            r = mapping_by_type["video"].get(absu)
            if r:
                tag["src"] = r

    # Iframes
    for tag in soup.find_all("iframe"):
        src = tag.get("src")
        if src:
            absu = urljoin(base_url, src)
            r = mapping_by_type["other"].get(absu)
            if r:
                tag["src"] = r


async def download_site(
    url: str,
    product_name: str,
    download_root: Path,
    use_render: bool = False,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
    limit_per_type: Optional[int] = None,
    limit_css_refs: Optional[int] = None,
    asset_cb: Optional[Callable[[str, str, str, Dict[str, int | str | None]], None]] = None,
    asset_cancel_cb: Optional[Callable[[str, str], bool]] = None,
    verify_ssl: bool = True,
) -> DownloadResult:
    # Create folder structure
    slug = slugify(product_name)
    folder = ensure_unique_dir(download_root, slug)
    ensure_subfolders(folder)

    index_path = folder / "index.html"
    local_index_path = folder / "local-index.html"

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0", "Referer": url}, verify=verify_ssl) as client:
        html, ctype = await fetch_text(client, url)
        # Save the raw main page source immediately as index.html
        try:
            index_path.write_text(html, encoding="utf-8")
            if log_cb:
                log_cb(f"Saved main page source -> {index_path.name}")
        except Exception:
            # Best-effort; continue even if this initial write fails
            if log_cb:
                log_cb("WARNING  failed to write raw index.html; will continue")
        soup = BeautifulSoup(html, "html.parser")
        base_url = url

        assets = collect_assets(soup, base_url)
        # Optional limiting for preview/demo
        if limit_per_type is not None and limit_per_type > 0:
            limited: Dict[str, Set[str]] = {}
            for kind, urls in assets.items():
                limited[kind] = set(sorted(urls)[:limit_per_type])
            assets = limited
        if log_cb:
            total_assets = sum(len(v) for v in assets.values())
            log_cb(f"Collected {total_assets} primary assets")
        if cancel_cb and cancel_cb():
            if log_cb:
                log_cb("CANCELLED before asset downloads")
            raise asyncio.CancelledError()
        mapping_by_type = await download_assets(
            client,
            assets,
            folder,
            progress_cb,
            log_cb,
            cancel_cb,
            asset_cb,
            asset_cancel_cb,
        )

        # Process CSS secondary assets
        if cancel_cb and cancel_cb():
            if log_cb:
                log_cb("CANCELLED before CSS processing")
            raise asyncio.CancelledError()
        await process_css_files(
            client,
            mapping_by_type["css"],
            folder,
            base_url,
            progress_cb,
            log_cb,
            cancel_cb,
            limit_refs=limit_css_refs,
            asset_cb=asset_cb,
            asset_cancel_cb=asset_cancel_cb,
        )

        # Rewrite paths in HTML
        rewrite_html_paths(soup, base_url, mapping_by_type)

        # Save modified HTML to a separate localized file, do not overwrite the raw index.html
        try:
            local_index_path.write_text(soup.prettify(), encoding="utf-8")
            if log_cb:
                log_cb(f"Saved localized page -> {local_index_path.name}")
        except Exception:
            if log_cb:
                log_cb("WARNING  failed to write local-index.html")

        # Generate PHP content file based on localized or raw HTML
        try:
            _generate_content_php(folder, product_name, log_cb)
        except Exception:
            if log_cb:
                log_cb("WARNING  failed to generate content.php")

    counts = {k: len(v) for k, v in assets.items()}
    return DownloadResult(
        product_name=product_name,
        slug=slug,
        root=download_root,
        folder=folder,
        index_path=index_path,
        counts=counts,
    )


def _generate_content_php(folder: Path, product_name: str, log_cb: Optional[Callable[[str], None]] = None) -> Path:
    """
    Create content.php in the given folder by:
    - Replacing all occurrences of the product name with <?=$productName;?>
    - Updating <a> tags whose visible text contains 'order' (case-insensitive)
      so that href becomes <?php echo $ctaLink; ?>

    We avoid BeautifulSoup escaping PHP in attributes by first writing a placeholder
    in href and then string-replacing after serialization.
    """
    preferred = folder / "local-index.html"
    fallback = folder / "index.html"
    src = preferred if preferred.exists() else fallback
    # If neither exists, raise
    if not src.exists():
        raise FileNotFoundError("No HTML source found to generate content.php")

    html = src.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    PLACEHOLDER = "__PHPCTA_LINK__"

    # Modify only anchors with visible text containing 'order'
    for a in soup.find_all("a"):
        text = a.get_text(strip=True) or ""
        if "order" in text.lower():
            a["href"] = PLACEHOLDER

    # Serialize and apply textual replacements
    out_html = str(soup)
    if product_name:
        out_html = out_html.replace(product_name, "<?=$productName;?>")
    out_html = out_html.replace(PLACEHOLDER, "<?php echo $ctaLink; ?>")
    # Insert PHP headers snippet right after the </title> closing tag (case-insensitive)
    try:
        out_html = re.sub(r'(</title\s*>)', r'\1\n<?= $headers; ?>', out_html, count=1, flags=re.IGNORECASE)
    except Exception:
        pass

    out_path = folder / "content.php"
    out_path.write_text(out_html, encoding="utf-8")
    if log_cb:
        log_cb("Saved PHP content -> content.php")
    return out_path
