from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from urllib.parse import urlparse


WINDOWS = True


def slugify(value: str, allow_unicode: bool = False) -> str:
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[\\/]+", "-", value)
    value = re.sub(r"[^\w\s-]", "", value.lower())
    value = re.sub(r"[\s-]+", "-", value).strip("-")
    return value or "site"


def ensure_unique_dir(base: Path, name: str) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    candidate = base / name
    i = 2
    while candidate.exists():
        candidate = base / f"{name}-{i}"
        i += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def safe_join(base: Path, target: Path) -> Path:
    base = base.resolve()
    target = target.resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("Path escapes base root")
    return target


def is_relative_url(url: str) -> bool:
    p = urlparse(url)
    return not p.scheme and not p.netloc and not url.startswith("//")


def guess_extension_from_mime(mime: Optional[str]) -> str:
    if not mime:
        return ""
    mapping = {
        "text/css": ".css",
        "text/javascript": ".js",
        "application/javascript": ".js",
        "application/x-javascript": ".js",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "font/woff": ".woff",
        "font/woff2": ".woff2",
        "font/ttf": ".ttf",
        "font/otf": ".otf",
        "application/font-woff": ".woff",
    }
    return mapping.get(mime.split(";")[0].strip(), "")
