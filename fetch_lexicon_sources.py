"""
Fetch the multi-source inputs for the green-tech anchor lexicon and archive them
with per-file SHA-256 checksums.

Sources (families): see STRONG_TERMS_PROTOCOL.md
  - gemet            : GEMET full SKOS RDF export (EEA / Eionet)
  - cpc_y02          : CPC Y02/Y04S climate-change-mitigation subclass schemes (USPTO HTML)
  - wikidata         : Wikidata Query Service SPARQL (pinned query file)
  - taxonomy_compass : EU Taxonomy Compass activity/sector list (webgate JSON API)
  - egss             : EGSS indicative compendium, Reg (EU) 2015/2174 (EUR-Lex mirror)
  - eu_reg           : already local (concept_seeds.csv); not re-fetched here

Outputs:
  - data/sources/lexicon_raw/*                 (raw bytes, archived)
  - data/sources/lexicon_sources_registry.csv  (url, sha256, status, license, ...)

"""

from __future__ import annotations

import csv
import hashlib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "sources" / "lexicon_raw"
QUERY_DIR = ROOT / "data" / "sources" / "lexicon_queries"
REGISTRY_PATH = ROOT / "data" / "sources" / "lexicon_sources_registry.csv"
WIKIDATA_QUERY_PATH = QUERY_DIR / "wikidata_green_tech.rq"

USER_AGENT = "mas-green-lexicon/1.0 (academic research; contact: repo owner)"
TIMEOUT = 120

GEMET_URL = "https://www.eionet.europa.eu/gemet/exports/latest/gemet.rdf.gz"
GEMET_LICENSE = "CC BY 4.0"

# CPC Y02 (climate change mitigation) + Y04S (smart grids) subclass schemes.
CPC_SUBCLASSES = ("Y02A", "Y02B", "Y02C", "Y02D", "Y02E", "Y02P", "Y02T", "Y02W", "Y04S")
CPC_URL_TMPL = "https://www.uspto.gov/web/patents/classification/cpc/html/cpc-{sc}.html"
CPC_LICENSE = "Public (USPTO/EPO CPC)"

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIDATA_LICENSE = "CC0"

# EU Taxonomy Compass (EU Taxonomy Navigator) REST API. The site is an Angular
# SPA; the backing service exposes language-prefixed JSON endpoints. Activities
# carry name + sector + description; sectors carry the sector vocabulary.
COMPASS_API = "https://webgate.ec.europa.eu/sft/api/v1"
COMPASS_ACTIVITIES_URL = COMPASS_API + "/en/activities"
COMPASS_SECTORS_URL = COMPASS_API + "/en/sectors"
COMPASS_LICENSE = "(c) European Union, reuse under Decision 2011/833/EU (CC BY 4.0)"

# EGSS indicative compendium = Commission Implementing Reg (EU) 2015/2174.
# EUR-Lex serves a JavaScript anti-bot challenge (HTTP 202) to non-interactive
# clients, so the ANNEX text is archived as a checksum-pinned mirror file and
# a live fetch is only attempted to record the current EUR-Lex status.
EGSS_CELEX = "32015R2174"
EGSS_URL = f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{EGSS_CELEX}"
EGSS_MIRROR = RAW_DIR / "egss_2015_2174.txt"
EGSS_LICENSE = "(c) European Union, EUR-Lex reuse under Decision 2011/833/EU"


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def http_get(url: str, headers: dict[str, str] | None = None) -> tuple[int, str, str, bytes]:
    """Return (status, final_url, content_type, body). Never raises on HTTP error."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            body = resp.read()
            return (
                getattr(resp, "status", 200) or 200,
                resp.geturl(),
                resp.headers.get_content_type(),
                body,
            )
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return (exc.code, url, exc.headers.get_content_type() if exc.headers else "", exc.read() or b"")


def fetch_to(
    url: str, out_path: Path, headers: dict[str, str] | None = None, retries: int = 1
) -> dict:
    status, final_url, ctype, body = http_get(url, headers=headers)
    attempt = 0
    # Retry transient gateway errors (e.g. WDQS 502/503/504) with backoff.
    while status in (429, 500, 502, 503, 504) and attempt < retries:
        attempt += 1
        time.sleep(5 * attempt)
        status, final_url, ctype, body = http_get(url, headers=headers)
    error = ""
    if status != 200 or not body:
        error = f"http_status={status} bytes={len(body)}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if body:
        out_path.write_bytes(body)
    return {
        "url": url,
        "final_url": final_url,
        "http_status": str(status),
        "content_type": ctype,
        "sha256": sha256_bytes(body) if body else "",
        "raw_path": str(out_path.relative_to(ROOT)) if body else "",
        "bytes": str(len(body)),
        "error": error,
    }


def fetch_with_mirror(url: str, mirror_path: Path, headers: dict[str, str] | None = None) -> dict:
    """Attempt a live fetch; if it fails or returns no usable body, fall back to a
    pre-archived mirror file (recording the observed live status for provenance)."""
    status, final_url, ctype, body = http_get(url, headers=headers)
    live_ok = status == 200 and bool(body) and b"not a robot" not in body[:4000].lower()
    if live_ok:
        mirror_path.parent.mkdir(parents=True, exist_ok=True)
        mirror_path.write_bytes(body)
        return {
            "url": url,
            "final_url": final_url,
            "http_status": str(status),
            "content_type": ctype,
            "sha256": sha256_bytes(body),
            "raw_path": str(mirror_path.relative_to(ROOT)),
            "bytes": str(len(body)),
            "error": "",
        }
    if mirror_path.exists():
        data = mirror_path.read_bytes()
        return {
            "url": url,
            "final_url": final_url,
            "http_status": f"mirror(live={status})",
            "content_type": "text/plain",
            "sha256": sha256_bytes(data),
            "raw_path": str(mirror_path.relative_to(ROOT)),
            "bytes": str(len(data)),
            "error": "",
        }
    return {
        "url": url,
        "final_url": final_url,
        "http_status": str(status),
        "content_type": ctype,
        "sha256": "",
        "raw_path": "",
        "bytes": str(len(body)),
        "error": f"live_failed status={status} and no mirror at {mirror_path.name}",
    }


def build_wikidata_url() -> str:
    query = WIKIDATA_QUERY_PATH.read_text(encoding="utf-8")
    return WIKIDATA_ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict] = []

    def record(source_id: str, family: str, title: str, license_: str, meta: dict) -> None:
        rows.append(
            {
                "source_id": source_id,
                "family": family,
                "title": title,
                "license": license_,
                "fetched_at_utc": now,
                **meta,
            }
        )
        status = meta.get("http_status")
        err = meta.get("error")
        print(f"[{source_id}] status={status} bytes={meta.get('bytes')} sha={meta.get('sha256')[:12]} {err}")

    # 1) GEMET SKOS
    record(
        "gemet_skos",
        "gemet",
        "GEMET General Multilingual Environmental Thesaurus (full SKOS)",
        GEMET_LICENSE,
        fetch_to(GEMET_URL, RAW_DIR / "gemet.rdf.gz"),
    )

    # 2) CPC Y02 / Y04S subclass schemes
    for sc in CPC_SUBCLASSES:
        url = CPC_URL_TMPL.format(sc=sc)
        record(
            f"cpc_{sc.lower()}",
            "cpc_y02",
            f"CPC {sc} climate-change-mitigation scheme",
            CPC_LICENSE,
            fetch_to(url, RAW_DIR / f"cpc-{sc}.html"),
        )
        time.sleep(0.5)

    # 3) Wikidata SPARQL
    record(
        "wikidata_green_tech",
        "wikidata",
        "Wikidata green-technology subclasses (pinned SPARQL)",
        WIKIDATA_LICENSE,
        fetch_to(
            build_wikidata_url(),
            RAW_DIR / "wikidata_green_tech.json",
            headers={"Accept": "application/sparql-results+json"},
            retries=3,
        ),
    )

    # 4) EU Taxonomy Compass (activities + sectors), JSON API
    record(
        "taxonomy_compass_activities",
        "taxonomy_compass",
        "EU Taxonomy Compass activity list (name, sector, description)",
        COMPASS_LICENSE,
        fetch_to(
            COMPASS_ACTIVITIES_URL,
            RAW_DIR / "taxonomy_compass_activities.json",
            headers={"Accept": "application/json"},
            retries=3,
        ),
    )
    time.sleep(0.5)
    record(
        "taxonomy_compass_sectors",
        "taxonomy_compass",
        "EU Taxonomy Compass sector list",
        COMPASS_LICENSE,
        fetch_to(
            COMPASS_SECTORS_URL,
            RAW_DIR / "taxonomy_compass_sectors.json",
            headers={"Accept": "application/json"},
            retries=3,
        ),
    )

    # 5) EGSS indicative compendium (Reg (EU) 2015/2174), EUR-Lex mirror
    record(
        "egss_2015_2174",
        "egss",
        "EGSS indicative compendium of environmental goods and services (Reg (EU) 2015/2174)",
        EGSS_LICENSE,
        fetch_with_mirror(EGSS_URL, EGSS_MIRROR),
    )

    fieldnames = [
        "source_id",
        "family",
        "title",
        "license",
        "url",
        "final_url",
        "http_status",
        "content_type",
        "sha256",
        "raw_path",
        "bytes",
        "fetched_at_utc",
        "error",
    ]
    with REGISTRY_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    ok = sum(1 for r in rows if r.get("http_status") == "200" and not r.get("error"))
    print(f"\nWrote {REGISTRY_PATH.relative_to(ROOT)} ({len(rows)} rows, {ok} ok).")
    failed = [r["source_id"] for r in rows if r.get("error")]
    if failed:
        print(f"WARNING: {len(failed)} source(s) failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
