#!/usr/bin/env python3
"""
Extracts employer primary brand color from their careers page.
Falls back to the default brand colour (#1e3a8a) on any failure.
"""
import re, sys

import requests
from bs4 import BeautifulSoup

FALLBACK_COLOR = "#1e3a8a"   # theme.css --brand


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    def _lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _is_legible(hex_color: str) -> bool:
    """WCAG AA contrast ratio ≥ 4.5 against white."""
    try:
        lum = _relative_luminance(hex_color)
        ratio = (1.0 + 0.05) / (lum + 0.05)
        return ratio >= 4.5
    except Exception:
        return False


def extract_employer_ci(careers_url: str, timeout: int = 10) -> str:
    """
    Attempt to extract employer's primary brand color.
    Returns a CSS hex color or FALLBACK_COLOR.
    """
    if not careers_url or not careers_url.startswith("http"):
        return FALLBACK_COLOR
    try:
        resp = requests.get(
            careers_url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code >= 400:
            return FALLBACK_COLOR

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. <meta name="theme-color">
        meta = soup.find("meta", attrs={"name": "theme-color"})
        if meta and meta.get("content"):
            color = meta["content"].strip()
            if re.match(r"^#[0-9a-fA-F]{3,6}$", color) and _is_legible(color):
                return color

        # 2. CSS :root custom properties
        for style_tag in soup.find_all("style"):
            m = re.search(
                r"--(?:primary|brand|color-primary|accent)[^:]*:\s*(#[0-9a-fA-F]{3,6})",
                style_tag.string or ""
            )
            if m and _is_legible(m.group(1)):
                return m.group(1)

        # 3. Dominant logo color via colorthief
        logo = soup.find("img", src=re.compile(r"logo", re.I))
        if logo and logo.get("src"):
            try:
                from colorthief import ColorThief
                import io
                logo_url = logo["src"]
                if logo_url.startswith("//"):
                    logo_url = "https:" + logo_url
                elif logo_url.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(careers_url)
                    logo_url = f"{parsed.scheme}://{parsed.netloc}{logo_url}"
                img_resp = requests.get(logo_url, timeout=5,
                                        headers={"User-Agent": "Mozilla/5.0"})
                ct = ColorThief(io.BytesIO(img_resp.content))
                r, g, b = ct.get_color(quality=1)
                color = f"#{r:02x}{g:02x}{b:02x}"
                if _is_legible(color):
                    return color
            except Exception:
                pass

    except Exception:
        pass

    return FALLBACK_COLOR


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    print(extract_employer_ci(url))
