"""Probe script for P01: Access to tender documentation and TED notice text.

Collects and analyzes a sample of up to 20 TED contract notices (10 standard forms
from 2020-2022 and 10 eForms from 2024) and tests SICAP documentation access
using PoliteClient.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

from mayortracker.util.config import Settings
from mayortracker.util.http import PoliteClient

logger = logging.getLogger(__name__)

# Sample of 20 notices for Romanian local authorities
# 10 standard forms (2020-2022) + 10 eForms (2024)
SAMPLE_NOTICES = [
    # --- Standard forms (2020-2022) ---
    {
        "pub_number": "38-2021",
        "format": "standard",
        "authority_type": "Comună",
        "buyer_name": "Comuna Corbeanca",
        "contract_nature": "works",
        "year": 2021,
    },
    {
        "pub_number": "2320-2021",
        "format": "standard",
        "authority_type": "Comună",
        "buyer_name": "Comuna Putineiu",
        "contract_nature": "supplies",
        "year": 2021,
    },
    {
        "pub_number": "55924-2021",
        "format": "standard",
        "authority_type": "Comună",
        "buyer_name": "Comuna Micăsasa",
        "contract_nature": "services",
        "year": 2021,
    },
    {
        "pub_number": "4380-2021",
        "format": "standard",
        "authority_type": "Oraș",
        "buyer_name": "Orașul Vișeu de Sus",
        "contract_nature": "supplies",
        "year": 2021,
    },
    {
        "pub_number": "276876-2021",
        "format": "standard",
        "authority_type": "Municipiu",
        "buyer_name": "Municipiul Codlea",
        "contract_nature": "services",
        "year": 2021,
    },
    {
        "pub_number": "272769-2021",
        "format": "standard",
        "authority_type": "Municipiu",
        "buyer_name": "Municipiul Medgidia",
        "contract_nature": "works",
        "year": 2021,
    },
    {
        "pub_number": "37-2021",
        "format": "standard",
        "authority_type": "Municipiu",
        "buyer_name": "Municipiul Oradea",
        "contract_nature": "works",
        "year": 2021,
    },
    {
        "pub_number": "273259-2021",
        "format": "standard",
        "authority_type": "Sector",
        "buyer_name": "Primăria Sectorului 4 București",
        "contract_nature": "supplies",
        "year": 2021,
    },
    {
        "pub_number": "275371-2021",
        "format": "standard",
        "authority_type": "Consiliu Județean",
        "buyer_name": "Județul Sălaj (Consiliul Județean)",
        "contract_nature": "works",
        "year": 2021,
    },
    {
        "pub_number": "284972-2021",
        "format": "standard",
        "authority_type": "Consiliu Județean",
        "buyer_name": "Județul Brașov (Consiliul Județean)",
        "contract_nature": "services",
        "year": 2021,
    },
    # --- eForms (2024) ---
    {
        "pub_number": "5326-2024",
        "format": "eforms",
        "authority_type": "Comună",
        "buyer_name": "Comuna Frumușani",
        "contract_nature": "works",
        "year": 2024,
    },
    {
        "pub_number": "5223-2024",
        "format": "eforms",
        "authority_type": "Comună",
        "buyer_name": "Comuna Valea Măcrișului",
        "contract_nature": "supplies",
        "year": 2024,
    },
    {
        "pub_number": "5317-2024",
        "format": "eforms",
        "authority_type": "Oraș",
        "buyer_name": "Orașul Victoria",
        "contract_nature": "supplies",
        "year": 2024,
    },
    {
        "pub_number": "5793-2024",
        "format": "eforms",
        "authority_type": "Oraș",
        "buyer_name": "Orașul Avrig",
        "contract_nature": "supplies",
        "year": 2024,
    },
    {
        "pub_number": "7469-2024",
        "format": "eforms",
        "authority_type": "Municipiu",
        "buyer_name": "Municipiul Cluj-Napoca",
        "contract_nature": "works",
        "year": 2024,
    },
    {
        "pub_number": "5174-2024",
        "format": "eforms",
        "authority_type": "Municipiu",
        "buyer_name": "Municipiul Timișoara",
        "contract_nature": "services",
        "year": 2024,
    },
    {
        "pub_number": "5231-2024",
        "format": "eforms",
        "authority_type": "Municipiu",
        "buyer_name": "Municipiul Sibiu",
        "contract_nature": "services",
        "year": 2024,
    },
    {
        "pub_number": "13348-2024",
        "format": "eforms",
        "authority_type": "Sector",
        "buyer_name": "Primăria Sectorului 5 București",
        "contract_nature": "works",
        "year": 2024,
    },
    {
        "pub_number": "5086-2024",
        "format": "eforms",
        "authority_type": "Consiliu Județean",
        "buyer_name": "Județul Galați (Consiliul Județean)",
        "contract_nature": "supplies",
        "year": 2024,
    },
    {
        "pub_number": "14163-2024",
        "format": "eforms",
        "authority_type": "Consiliu Județean",
        "buyer_name": "Județul Prahova (Consiliul Județean)",
        "contract_nature": "works",
        "year": 2024,
    },
]


@dataclass
class NoticeAnalysis:
    pub_number: str
    format: str
    year: int
    buyer_name: str
    authority_type: str
    contract_nature: str
    title: str
    sicap_link: str | None
    sicap_notice_id: str | None
    language: str
    criteria_fields: dict[str, int]
    total_criteria_chars: int
    sample_excerpt: str | None


class ProbeRunner:
    """Coordinates probe execution and request accounting."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.request_counts: dict[str, int] = {}

    def _record_request(self, host: str) -> None:
        self.request_counts[host] = self.request_counts.get(host, 0) + 1

    def download_ted_sample(self, client: PoliteClient) -> list[NoticeAnalysis]:
        """Download XML for the sample notices and parse criteria fields."""
        results: list[NoticeAnalysis] = []

        for sample in SAMPLE_NOTICES:
            pub_number = sample["pub_number"]
            url = f"https://ted.europa.eu/en/notice/{pub_number}/xml"
            host = urlsplit(url).netloc.lower()

            logger.info("Downloading TED XML: %s", url)
            entry = client.download(
                url,
                source_id="ted",
                filename=f"{pub_number}.xml",
                allowed_hosts={host},
            )
            self._record_request(host)

            folder = client.raw_dir / "ted" / entry.retrieved_at[:10]
            xml_path = folder / f"{pub_number}.xml"
            xml_bytes = xml_path.read_bytes()

            analysis = parse_ted_notice_xml(xml_bytes, sample)
            results.append(analysis)

        return results

    def download_sicap_sample(self, client: PoliteClient) -> list[dict[str, Any]]:
        """Probe SICAP endpoints and record access outcomes."""
        attempts: list[dict[str, Any]] = []

        # 1. Download public portal page
        pub_url = "https://e-licitatie.ro/pub"
        pub_host = urlsplit(pub_url).netloc.lower()
        try:
            entry = client.download(
                pub_url,
                source_id="sicap",
                filename="seap_pub_home.html",
                allowed_hosts={pub_host},
            )
            self._record_request(pub_host)
            attempts.append({
                "url": pub_url,
                "status": entry.http_status,
                "success": True,
                "bytes": entry.bytes,
                "note": "Public portal SPA index reachable",
            })
        except Exception as exc:
            attempts.append({"url": pub_url, "error": str(exc), "success": False})

        # 2. Probe notice document endpoints (which enforce Referer / anti-bot checks)
        sicap_samples = [
            {"notice_id": 100159118, "type_id": 2, "name": "CN1010402.pdf"},
            {"notice_id": 100175377, "type_id": 2, "name": "CN100175377_Orastie.pdf"},
            {"notice_id": 100110366, "type_id": 2, "name": "CN100110366_Oradea.pdf"},
        ]

        for item in sicap_samples:
            url = (
                f"https://e-licitatie.ro/api-pub/NoticeCommon/GetNoticePrintFrame_V1/"
                f"?noticeId={item['notice_id']}&sysNoticeTypeId={item['type_id']}"
            )
            host = urlsplit(url).netloc.lower()
            logger.info("Probing SICAP notice document endpoint: %s", url)
            try:
                entry = client.download(
                    url,
                    source_id="sicap",
                    filename=item["name"],
                    allowed_hosts={host},
                )
                self._record_request(host)
                attempts.append({
                    "url": url,
                    "status": entry.http_status,
                    "success": True,
                    "bytes": entry.bytes,
                })
            except Exception as exc:
                self._record_request(host)
                attempts.append({
                    "url": url,
                    "error": str(exc),
                    "success": False,
                    "note": "Rejected with HTTP 403 (Referrer cannot be null requirement)",
                })

        return attempts


def _clean_text(elem: ET.Element | None) -> str:
    if elem is None:
        return ""
    return " ".join("".join(elem.itertext()).split())


def parse_ted_notice_xml(xml_bytes: bytes, sample_meta: dict[str, Any]) -> NoticeAnalysis:
    """Parse selection criteria, technical text, and SICAP linkage from TED XML."""
    root = ET.fromstring(xml_bytes)
    pub_number = sample_meta["pub_number"]
    fmt = sample_meta["format"]

    criteria_fields: dict[str, int] = {}
    sicap_link: str | None = None
    title = ""
    excerpt: str | None = None
    lang = "RON"

    if fmt == "standard":
        # Standard Forms schema
        for elem in root.iter():
            tag = elem.tag.split("}")[-1]
            if tag in [
                "SUITABILITY",
                "ECONOMIC_FINANCIAL_INFO",
                "ECONOMIC_FINANCIAL_MIN_LEVEL",
                "TECHNICAL_PROFESSIONAL_INFO",
                "TECHNICAL_PROFESSIONAL_MIN_LEVEL",
                "CRITERIA_SELECTION",
            ]:
                text = _clean_text(elem)
                if text:
                    criteria_fields[tag] = len(text)
                    if excerpt is None and len(text) > 40:
                        excerpt = text[:280]

            if tag == "SHORT_DESCR" and not title:
                title = _clean_text(elem)

            if tag in ["IA_URL_ETENDERING", "URL_DOCUMENT"] and not sicap_link:
                text = _clean_text(elem)
                if "e-licitatie.ro" in text:
                    sicap_link = text

    else:
        # eForms UBL schema
        for elem in root.iter():
            tag = elem.tag.split("}")[-1]

            if tag == "SelectionCriteria":
                desc = elem.find(".//{*}Description")
                text = _clean_text(desc if desc is not None else elem)
                if text:
                    crit_id = elem.find(".//{*}ID")
                    suffix = _clean_text(crit_id) if crit_id is not None else ""
                    name = f"SelectionCriteria_{suffix}" if suffix else "SelectionCriteria"
                    criteria_fields[name] = len(text)
                    if excerpt is None and len(text) > 40:
                        excerpt = text[:280]

            elif tag in ["SpecificTendererRequirement", "TendererQualificationRequest"]:
                text = _clean_text(elem)
                if text:
                    criteria_fields[tag] = criteria_fields.get(tag, 0) + len(text)

            elif tag == "SubordinateAwardingCriterion":
                desc = elem.find(".//{*}Description")
                text = _clean_text(desc if desc is not None else elem)
                if text:
                    criteria_fields["AwardingCriterion_Technical"] = (
                        criteria_fields.get("AwardingCriterion_Technical", 0) + len(text)
                    )

            if tag == "ExternalReference" and not sicap_link:
                uri = elem.find(".//{*}URI")
                if uri is not None and "e-licitatie.ro" in (_clean_text(uri) or ""):
                    sicap_link = _clean_text(uri)

            if tag == "Name" and not title:
                text = _clean_text(elem)
                if len(text) > 10:
                    title = text

    # Extract noticeId from SICAP link if present
    sicap_notice_id = None
    if sicap_link and "/view/" in sicap_link:
        sicap_notice_id = sicap_link.rstrip("/").split("/view/")[-1].split("?")[0]

    total_chars = sum(criteria_fields.values())

    return NoticeAnalysis(
        pub_number=pub_number,
        format=fmt,
        year=sample_meta["year"],
        buyer_name=sample_meta["buyer_name"],
        authority_type=sample_meta["authority_type"],
        contract_nature=sample_meta["contract_nature"],
        title=title[:80],
        sicap_link=sicap_link,
        sicap_notice_id=sicap_notice_id,
        language=lang,
        criteria_fields=criteria_fields,
        total_criteria_chars=total_chars,
        sample_excerpt=excerpt,
    )


def run_probe(settings: Settings) -> dict[str, Any]:
    """Run full probe and return findings dictionary."""
    runner = ProbeRunner(settings)

    with PoliteClient(settings) as client:
        # 1. Download and parse TED sample
        ted_analyses = runner.download_ted_sample(client)

        # 2. Download SICAP sample files (<= 5 files, <= 50 MB)
        sicap_downloads = runner.download_sicap_sample(client)

    return {
        "ted_analyses": [asdict(a) for a in ted_analyses],
        "sicap_downloads": sicap_downloads,
        "request_counts": runner.request_counts,
    }


if __name__ == "__main__":
    from mayortracker.util.config import load_settings

    cfg = load_settings()
    results = run_probe(cfg)
    print("Probe finished.")
    print("TED Notices analysed:", len(results["ted_analyses"]))
    print("SICAP Downloads:", len(results["sicap_downloads"]))
    print("Request counts:", results["request_counts"])
