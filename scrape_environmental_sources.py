"""
Download official environmental framework documents and extract concept seeds.

Step B of the green vocabulary pipeline. Does NOT overwrite the handoff
strict_green_vocabulary_full_audit.csv.

Outputs under data/sources/:
  - raw/          downloaded HTML/PDF files
  - text/         extracted plain text
  - manifest.csv  url, paths, sha256, fetch metadata
  - concept_seeds.csv  explicit regex-extracted seed phrases

Dependencies: Python 3.9+, pypdf (PDF text). Uses stdlib urllib for HTTP.
"""

from __future__ import annotations

import csv
import hashlib
import http.cookiejar
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pypdf is required. Install with:\n"
        "  module load python/3.12.13-aocl5.3 && python -m pip install --user pypdf"
    ) from exc


# =====================================================================
# PATHS
# =====================================================================

ROOT = Path(__file__).resolve().parent
SOURCES_DIR = ROOT / "data" / "sources"
RAW_DIR = SOURCES_DIR / "raw"
TEXT_DIR = SOURCES_DIR / "text"
MANIFEST_PATH = SOURCES_DIR / "manifest.csv"
SEEDS_PATH = SOURCES_DIR / "concept_seeds.csv"
REPORT_PATH = SOURCES_DIR / "scrape_report.txt"

USER_AGENT = (
    "Mozilla/5.0 (compatible; ESADE-green-startup-thesis-research/1.0; "
    "+academic non-commercial archival)"
)
REQUEST_TIMEOUT_S = 120
SLEEP_BETWEEN_REQUESTS_S = 1.5

_COOKIE_JAR = http.cookiejar.CookieJar()
_URL_OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_COOKIE_JAR)
)


# =====================================================================
# SOURCE CATALOGUE (handoff ENVIRONMENTAL_FRAMEWORK_SOURCES.md)
# =====================================================================

# Each entry: source_id, title, canonical_url, fetch_url (often PDF), objective_guess
SOURCES: list[dict[str, str]] = [
    {
        "source_id": "taxonomy_2020_852",
        "title": "Regulation (EU) 2020/852 — EU Taxonomy Regulation",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg/2020/852/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32020R0852",
        "objective_guess": "six environmental objectives (organising)",
    },
    {
        "source_id": "climate_da_2021_2139_20260101",
        "title": "Climate Delegated Act (EU) 2021/2139 consolidated 2026-01-01",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg_del/2021/2139/2026-01-01/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02021R2139-20260101",
        "objective_guess": "1 Climate change mitigation | 2 Climate change adaptation",
    },
    {
        "source_id": "env_da_2023_2486_20260101",
        "title": "Environmental Delegated Act (EU) 2023/2486 consolidated 2026-01-01",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg_del/2023/2486/2026-01-01/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02023R2486-20260101",
        "objective_guess": (
            "3 Water and marine resources | 4 Circular economy | "
            "5 Pollution prevention and control | 6 Biodiversity and ecosystems"
        ),
    },
    {
        "source_id": "cep_eurostat",
        "title": "Eurostat Classification of Environmental Purposes (CEP)",
        "canonical_url": (
            "https://ec.europa.eu/eurostat/documents/1798247/12177560/"
            "Classification%2Bof%2Benvironmental%2Bpurposes%2B%28CEP%29.pdf/"
            "7283e770-d10a-dd9a-b491-59661d2c9c42"
        ),
        "fetch_url": (
            "https://ec.europa.eu/eurostat/documents/1798247/12177560/"
            "Classification%2Bof%2Benvironmental%2Bpurposes%2B%28CEP%29.pdf/"
            "7283e770-d10a-dd9a-b491-59661d2c9c42"
        ),
        "objective_guess": "CEP cross-sector environmental purposes",
    },
    {
        "source_id": "nzia_2024_1735",
        "title": "Net-Zero Industry Act (EU) 2024/1735",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg/2024/1735/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1735",
        "objective_guess": "1 Climate change mitigation (net-zero technologies)",
    },
    {
        "source_id": "water_resilience_com_2025_280",
        "title": "European Water Resilience Strategy COM(2025) 280",
        "canonical_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52025DC0280",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:52025DC0280",
        "objective_guess": "3 Water and marine resources",
    },
    {
        "source_id": "espr_2024_1781",
        "title": "Ecodesign for Sustainable Products Regulation (EU) 2024/1781",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg/2024/1781/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1781",
        "objective_guess": "4 Transition to a circular economy",
    },
    {
        "source_id": "ppwr_2025_40",
        "title": "Packaging and Packaging Waste Regulation (EU) 2025/40",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg/2025/40/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32025R0040",
        "objective_guess": "4 Transition to a circular economy",
    },
    {
        "source_id": "crma_2024_1252",
        "title": "Critical Raw Materials Act (EU) 2024/1252",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg/2024/1252/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1252",
        "objective_guess": "4 Transition to a circular economy (recovery/recycling)",
    },
    {
        "source_id": "right_to_repair_2024_1799",
        "title": "Right-to-Repair Directive (EU) 2024/1799",
        "canonical_url": "https://eur-lex.europa.eu/eli/dir/2024/1799/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024L1799",
        "objective_guess": "4 Transition to a circular economy",
    },
    {
        "source_id": "waste_framework_2008_98_20251016",
        "title": "Waste Framework Directive 2008/98/EC consolidated 2025-10-16",
        "canonical_url": "https://eur-lex.europa.eu/eli/dir/2008/98/2025-10-16/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02008L0098-20251016",
        "objective_guess": "4 Transition to a circular economy",
    },
    {
        "source_id": "air_quality_2024_2881",
        "title": "Ambient Air Quality Directive (EU) 2024/2881",
        "canonical_url": "https://eur-lex.europa.eu/eli/dir/2024/2881/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024L2881",
        "objective_guess": "5 Pollution prevention and control",
    },
    {
        "source_id": "industrial_emissions_2024_1785",
        "title": "Industrial Emissions amendment Directive (EU) 2024/1785",
        "canonical_url": "https://eur-lex.europa.eu/eli/dir/2024/1785/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024L1785",
        "objective_guess": "5 Pollution prevention and control",
    },
    {
        "source_id": "nature_restoration_2024_1991",
        "title": "Nature Restoration Regulation (EU) 2024/1991",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg/2024/1991/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1991",
        "objective_guess": "6 Biodiversity and ecosystems",
    },
    {
        "source_id": "carbon_removals_2024_3012",
        "title": "Carbon removals certification framework (EU) 2024/3012",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg/2024/3012/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R3012",
        "objective_guess": "1 Climate change mitigation",
    },
    {
        "source_id": "taxonomy_amendment_2026_73",
        "title": "Taxonomy amendment Delegated Regulation (EU) 2026/73 (checked)",
        "canonical_url": "https://eur-lex.europa.eu/eli/reg_del/2026/73/oj/eng",
        "fetch_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32026R0073",
        "objective_guess": "Taxonomy technical updates (not a separate vocabulary framework)",
    },
]


# =====================================================================
# TEXT HELPERS
# =====================================================================

def normalise_phrase(value: str) -> str:
    """Same controlled normalisation used later for Description matching."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"_+", " ", value)
    return " ".join(value.split())


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data):
        if not self._skip and data and data.strip():
            self._chunks.append(data)

    def text(self) -> str:
        return "\n".join(self._chunks)


def html_to_text(raw: bytes) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return parser.text()


def pdf_to_text(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guess_extension(url: str, content_type: str) -> str:
    ct = (content_type or "").lower()
    if "pdf" in ct or url.lower().endswith(".pdf") or "TXT/PDF" in url:
        return ".pdf"
    if "html" in ct or "TXT/HTML" in url or url.lower().endswith(".html"):
        return ".html"
    if "pdf" in url.lower():
        return ".pdf"
    return ".bin"


# =====================================================================
# DOWNLOAD
# =====================================================================

def http_get(url: str) -> tuple[int, str, bytes, str]:
    """Return status, final_url, body, content_type."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,text/html,application/xhtml+xml,*/*",
        },
        method="GET",
    )
    try:
        with _URL_OPENER.open(request, timeout=REQUEST_TIMEOUT_S) as resp:
            body = resp.read()
            status = getattr(resp, "status", 200) or 200
            final_url = resp.geturl()
            content_type = resp.headers.get("Content-Type", "")
            return int(status), final_url, body, content_type
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return int(exc.code), url, body, exc.headers.get("Content-Type", "")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error fetching {url}: {exc}") from exc


def celex_html_url(fetch_url: str) -> str | None:
    """Derive an HTML TXT URL from a CELEX PDF fetch URL when possible."""
    match = re.search(r"uri=CELEX:([A-Z0-9\-]+)", fetch_url, flags=re.I)
    if not match:
        return None
    celex = match.group(1)
    return (
        "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/"
        f"?uri=CELEX:{celex}"
    )


def http_get_with_retries(
    url: str,
    *,
    retries: int = 4,
    backoff_s: float = 2.0,
) -> tuple[int, str, bytes, str]:
    """GET with retries; EUR-Lex often returns HTTP 202 while preparing PDFs."""
    last: tuple[int, str, bytes, str] = (0, url, b"", "")
    for attempt in range(retries):
        status, final_url, body, content_type = http_get(url)
        last = (status, final_url, body, content_type)
        if status == 200 and body and (
            body[:4] == b"%PDF"
            or b"<html" in body[:500].lower()
            or len(body) > 1000
        ):
            return last
        if status in {202, 429, 503} or not body:
            time.sleep(backoff_s * (attempt + 1))
            continue
        if status >= 400:
            time.sleep(backoff_s)
            continue
        return last
    return last


def existing_valid_pdf(source_id: str) -> Path | None:
    path = RAW_DIR / f"{source_id}.pdf"
    if not path.exists() or path.stat().st_size < 10_000:
        return None
    head = path.read_bytes()[:5]
    if head.startswith(b"%PDF"):
        return path
    return None


def existing_usable_html(source_id: str) -> Path | None:
    path = RAW_DIR / f"{source_id}.html"
    if not path.exists() or path.stat().st_size < 5_000:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")[:500].lower()
    if "captcha" in text or "<title></title>" in text:
        return None
    return path


def download_source(fetch_url: str) -> tuple[int, str, bytes, str, str]:
    """
    Download a source document.

    Tries the configured fetch_url (usually PDF). On EUR-Lex 202/empty PDF,
    falls back to the CELEX HTML rendering.
    Returns status, final_url, body, content_type, mode ('pdf'|'html'|'raw').
    """
    # Warm up EUR-Lex session cookie (reduces empty 202 responses)
    try:
        http_get("https://eur-lex.europa.eu/")
        time.sleep(1.0)
    except Exception:
        pass

    status, final_url, body, content_type = http_get(fetch_url)
    if status == 200 and body and (body[:4] == b"%PDF" or len(body) > 5000):
        mode = (
            "pdf"
            if body[:4] == b"%PDF" or "pdf" in (content_type or "").lower()
            else "raw"
        )
        return status, final_url, body, content_type, mode

    if status in {202, 429, 503} or not body:
        time.sleep(3.0)
        status, final_url, body, content_type = http_get_with_retries(
            fetch_url, retries=3, backoff_s=3.0
        )
        if status == 200 and body and (body[:4] == b"%PDF" or len(body) > 5000):
            mode = (
                "pdf"
                if body[:4] == b"%PDF" or "pdf" in (content_type or "").lower()
                else "raw"
            )
            return status, final_url, body, content_type, mode

    html_url = celex_html_url(fetch_url)
    if html_url and html_url != fetch_url:
        print(f"  fallback HTML: {html_url}", flush=True)
        time.sleep(2.0)
        status2, final2, body2, ct2 = http_get_with_retries(
            html_url, retries=3, backoff_s=2.0
        )
        if status2 == 200 and body2 and len(body2) > 5000:
            return status2, final2, body2, ct2, "html"

    if "TXT/HTML" in fetch_url or fetch_url.endswith(".html"):
        status_h, final_h, body_h, ct_h = http_get_with_retries(
            fetch_url, retries=3, backoff_s=2.0
        )
        return status_h, final_h, body_h, ct_h, "html"

    return status, final_url, body, content_type, "raw"


# =====================================================================
# SEED EXTRACTION (explicit regex rules — no LLM)
# =====================================================================

# CEP: lines like "01 Protection of ambient air and climate"
# or "0402 Recycling"
CEP_CODE_LABEL = re.compile(
    r"(?m)^(?P<code>\d{2}(?:\d{2})?(?:\d{2})?)\s+"
    r"(?P<label>[A-Z][^\n]{3,160})$"
)

# Taxonomy / DA annex activity titles, e.g. "4.1. Electricity generation using solar..."
# Allow start-of-line OR whitespace-bounded (WebFetch markdown often reflows lines).
ANNEX_ACTIVITY = re.compile(
    r"(?m)(?:^|\n|\s)(?P<code>\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\.?\s+"
    r"(?P<label>[A-Z][^.\n]{5,180})"
)

# Article / section headings that look like environmental concept phrases
CONCEPT_HEADING = re.compile(
    r"(?mi)\b(?P<label>("
    r"(?:climate change (?:mitigation|adaptation))"
    r"|(?:transition to a )?circular economy"
    r"|(?:pollution prevention(?: and control)?)"
    r"|(?:protection and restoration of )?biodiversity"
    r"|(?:ecosystem(?:s)?(?: restoration)?)"
    r"|(?:renewable energy|energy efficiency|carbon (?:capture|removal|storage|farming))"
    r"|(?:waste (?:prevention|recycling|recovery|management|hierarchy))"
    r"|(?:water (?:reuse|efficiency|resilience|leakage|stress))"
    r"|(?:right to repair|ecodesign|recyclability|remanufacturing)"
    r"|(?:net[- ]zero)"
    r"))\b"
)

# NZIA-style technology list items often appear as short capitalised phrases
TECH_LIST_ITEM = re.compile(
    r"(?mi)^(?:[-•*]|\d+[.)])\s*(?P<label>("
    r"(?:solar|wind|geothermal|hydropower|heat pump|battery|"
    r"electrolys(?:er|is)|carbon capture|grid|nuclear|"
    r"biogas|biomethane|biofuel)[^\n]{0,100}"
    r"))$"
)


def extract_seeds_from_text(
    source_id: str,
    source_url: str,
    objective_guess: str,
    text: str,
) -> list[dict[str, str]]:
    """Apply documented regex extractors; dedupe by normalised_phrase within source."""
    seeds: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(seed_phrase: str, rule_id: str, excerpt: str) -> None:
        phrase = " ".join((seed_phrase or "").split())
        if len(phrase) < 4:
            return
        norm = normalise_phrase(phrase)
        if len(norm) < 4 or norm in seen:
            return
        # Drop pure boilerplate
        if norm in {
            "european union",
            "official journal",
            "european commission",
            "member states",
        }:
            return
        seen.add(norm)
        seeds.append(
            {
                "seed_phrase": phrase,
                "normalised_phrase": norm,
                "source_id": source_id,
                "source_url": source_url,
                "objective_guess": objective_guess,
                "extraction_rule": rule_id,
                "excerpt": " ".join(excerpt.split())[:300],
            }
        )

    # CEP_CODE_LABEL is specific to the Eurostat Classification of Environmental
    # Purposes document, where a leading numeric code denotes an environmental
    # purpose class. In any other document a "<number> <Capitalised text>" line
    # is a table row, date, legal reference or HS/customs tariff code (e.g.
    # "42 Assets under management", "6301 Blankets and travelling rugs"), not an
    # environmental concept. Restricting the rule to the CEP source removes those
    # extraction artifacts at the root instead of denylisting them downstream.
    if source_id == "cep_eurostat":
        for match in CEP_CODE_LABEL.finditer(text):
            label = match.group("label").strip()
            code = match.group("code")
            add(label, "CEP_CODE_LABEL", f"{code} {label}")

    for match in ANNEX_ACTIVITY.finditer(text):
        label = match.group("label").strip()
        code = match.group("code")
        add(label, "ANNEX_ACTIVITY", f"{code} {label}")

    for match in CONCEPT_HEADING.finditer(text):
        label = match.group("label").strip()
        add(label, "CONCEPT_HEADING", match.group(0))

    for match in TECH_LIST_ITEM.finditer(text):
        label = match.group("label").strip(" .;:,")
        if len(label.split()) >= 2 or len(label) >= 8:
            add(label, "TECH_LIST_ITEM", match.group(0))

    return seeds


# =====================================================================
# MAIN
# =====================================================================

def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest_rows: list[dict[str, str]] = []
    all_seeds: list[dict[str, str]] = []
    report_lines: list[str] = [
        "ENVIRONMENTAL SOURCE SCRAPE REPORT",
        f"fetched_at_utc: {fetched_at}",
        f"sources_requested: {len(SOURCES)}",
        "",
    ]

    for index, source in enumerate(SOURCES, start=1):
        source_id = source["source_id"]
        fetch_url = source["fetch_url"]
        canonical_url = source["canonical_url"]
        print(f"[{index}/{len(SOURCES)}] {source_id} ...", flush=True)

        status = ""
        final_url = ""
        content_type = ""
        digest = ""
        raw_path = ""
        text_path = ""
        text_chars = 0
        n_seeds = 0
        error = ""
        reused = False

        try:
            raw_file: Path | None = existing_valid_pdf(source_id)
            mode = "pdf"
            body = b""

            if raw_file is not None:
                print(f"  reuse existing PDF ({raw_file.stat().st_size} bytes)", flush=True)
                body = raw_file.read_bytes()
                status = "200"
                final_url = fetch_url
                content_type = "application/pdf"
                reused = True
            else:
                html_existing = existing_usable_html(source_id)
                if html_existing is not None:
                    print(
                        f"  reuse existing HTML ({html_existing.stat().st_size} bytes)",
                        flush=True,
                    )
                    raw_file = html_existing
                    body = raw_file.read_bytes()
                    status = "200"
                    final_url = fetch_url
                    content_type = "text/html"
                    mode = "html"
                    reused = True
                else:
                    status_i, final_url, body, content_type, mode = download_source(
                        fetch_url
                    )
                    status = str(status_i)
                    if mode == "pdf" or (body and body[:4] == b"%PDF"):
                        ext = ".pdf"
                    elif mode == "html" or "html" in (content_type or "").lower():
                        ext = ".html"
                    else:
                        ext = guess_extension(final_url or fetch_url, content_type)
                    candidate = RAW_DIR / f"{source_id}{ext}"
                    # Never overwrite a good PDF with an empty/failed download
                    if body and len(body) >= 1000 and (
                        body[:4] == b"%PDF" or ext != ".pdf" or len(body) > 5000
                    ):
                        candidate.write_bytes(body)
                        raw_file = candidate
                    elif existing_valid_pdf(source_id) is not None:
                        raw_file = existing_valid_pdf(source_id)
                        body = raw_file.read_bytes()
                        mode = "pdf"
                        status = "200"
                        reused = True
                        print("  kept previous valid PDF after failed fetch", flush=True)
                    else:
                        error = f"HTTP {status} or empty/unusable body"
                        raw_file = candidate
                        candidate.write_bytes(body or b"")

            if raw_file is not None:
                raw_path = str(raw_file.relative_to(ROOT))
                digest = sha256_bytes(body if body else raw_file.read_bytes())

            text = ""
            if not error and raw_file is not None and raw_file.stat().st_size > 0:
                if raw_file.suffix.lower() == ".pdf" or (
                    body[:4] == b"%PDF" if body else False
                ):
                    text = pdf_to_text(raw_file)
                else:
                    text = html_to_text(body or raw_file.read_bytes())

            # EUR-Lex frequently answers HTML fetches with an empty HTTP 202
            # body. When the live fetch yields too little text, fall back to a
            # previously ingested WebFetch mirror so seed extraction stays
            # reproducible offline instead of silently dropping the source.
            if len(text.strip()) < 200:
                mirror = RAW_DIR / f"{source_id}.webfetch.txt"
                if mirror.exists():
                    mirror_text = mirror.read_text(encoding="utf-8", errors="ignore")
                    if len(mirror_text.strip()) >= 200:
                        text = mirror_text
                        reused = True
                        if not raw_path:
                            raw_path = str(mirror.relative_to(ROOT))

            if not error:
                if len(text.strip()) < 200:
                    error = error or "extracted text too short / empty"
                else:
                    text_file = TEXT_DIR / f"{source_id}.txt"
                    text_file.write_text(text, encoding="utf-8")
                    text_path = str(text_file.relative_to(ROOT))
                    text_chars = len(text)

                    seeds = extract_seeds_from_text(
                        source_id=source_id,
                        source_url=canonical_url,
                        objective_guess=source["objective_guess"],
                        text=text,
                    )
                    n_seeds = len(seeds)
                    all_seeds.extend(seeds)

        except Exception as exc:
            error = str(exc)
            print(f"  ERROR: {error}", flush=True)

        manifest_rows.append(
            {
                "source_id": source_id,
                "title": source["title"],
                "canonical_url": canonical_url,
                "fetch_url": fetch_url,
                "final_url": final_url,
                "http_status": status,
                "content_type": content_type,
                "sha256": digest,
                "raw_path": raw_path,
                "text_path": text_path,
                "text_chars": str(text_chars),
                "n_seeds": str(n_seeds),
                "fetched_at_utc": fetched_at,
                "reused_local": "1" if reused else "0",
                "error": error,
            }
        )
        report_lines.append(
            f"{source_id}: status={status or 'ERR'} "
            f"text_chars={text_chars} seeds={n_seeds} "
            f"{'reused ' if reused else ''}"
            f"{'ERROR=' + error if error else 'ok'}"
        )
        if not reused:
            time.sleep(SLEEP_BETWEEN_REQUESTS_S)

    # Write manifest
    manifest_fields = [
        "source_id",
        "title",
        "canonical_url",
        "fetch_url",
        "final_url",
        "http_status",
        "content_type",
        "sha256",
        "raw_path",
        "text_path",
        "text_chars",
        "n_seeds",
        "fetched_at_utc",
        "reused_local",
        "error",
    ]
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=manifest_fields)
        writer.writeheader()
        writer.writerows(manifest_rows)

    seed_fields = [
        "seed_phrase",
        "normalised_phrase",
        "source_id",
        "source_url",
        "objective_guess",
        "extraction_rule",
        "excerpt",
    ]
    with SEEDS_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=seed_fields)
        writer.writeheader()
        writer.writerows(all_seeds)

    ok = sum(1 for r in manifest_rows if not r["error"] and int(r["text_chars"] or 0) > 0)
    failed = len(manifest_rows) - ok
    report_lines.extend(
        [
            "",
            f"sources_ok: {ok}",
            f"sources_failed_or_empty: {failed}",
            f"total_seed_rows: {len(all_seeds)}",
            f"unique_normalised_phrases: "
            f"{len({s['normalised_phrase'] for s in all_seeds})}",
            f"manifest: {MANIFEST_PATH}",
            f"concept_seeds: {SEEDS_PATH}",
        ]
    )
    report = "\n".join(report_lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print()
    print(report)
    if failed:
        print(
            f"WARNING: {failed} source(s) failed or produced empty text.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
