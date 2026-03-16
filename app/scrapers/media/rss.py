from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from app.core.enums import NewsType, SourceName
from app.normalizers.text import html_to_text
from app.schemas.news import NewsRecord
from app.utils.time import utcnow


ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"


def _find_text(node: ET.Element, tag: str, namespace: str | None = None) -> str | None:
    search = f"{{{namespace}}}{tag}" if namespace else tag
    found = node.find(search)
    if found is None or found.text is None:
        return None
    text = found.text.strip()
    return text or None


def _collect_rss_categories(item: ET.Element) -> list[str]:
    categories = [category.text.strip() for category in item.findall("category") if category.text]
    subject = _find_text(item, "subject", DC_NAMESPACE)
    if subject:
        categories.append(subject)
    return [value for value in dict.fromkeys(categories) if value]


def _collect_atom_categories(entry: ET.Element) -> list[str]:
    categories = []
    for category in entry.findall(f"{{{ATOM_NAMESPACE}}}category"):
        value = (category.attrib.get("term") or category.attrib.get("label") or "").strip()
        if value:
            categories.append(value)
    return [value for value in dict.fromkeys(categories) if value]


def _pick_atom_link(entry: ET.Element) -> str:
    links = entry.findall(f"{{{ATOM_NAMESPACE}}}link")
    for relation in ("alternate", ""):
        for link in links:
            if (link.attrib.get("rel", "") or "") == relation:
                href = (link.attrib.get("href") or "").strip()
                if href:
                    return href
    return ""


class RSSParser:
    def parse(self, xml_text: str, source_name: SourceName) -> list[NewsRecord]:
        root = ET.fromstring(xml_text)
        if root.tag.endswith("feed"):
            return self._parse_atom(root, source_name)
        return self._parse_rss(root, source_name)

    def _parse_rss(self, root: ET.Element, source_name: SourceName) -> list[NewsRecord]:
        channel = root.find("channel")
        if channel is None:
            return []
        items: list[NewsRecord] = []
        for item in channel.findall("item"):
            title = html_to_text(_find_text(item, "title"))
            source_url = _find_text(item, "link") or _find_text(item, "guid") or ""
            if not title or not source_url:
                continue
            published_raw = _find_text(item, "pubDate")
            categories = _collect_rss_categories(item)
            items.append(
                NewsRecord(
                    source_name=source_name,
                    source_url=source_url,
                    title=title,
                    summary=html_to_text(_find_text(item, "description")),
                    raw_category=" | ".join(categories) if categories else None,
                    published_at=parsedate_to_datetime(published_raw) if published_raw else None,
                    scraped_at=utcnow(),
                    news_type=NewsType.OTHER,
                    raw_payload={"categories": categories},
                )
            )
        return items

    def _parse_atom(self, root: ET.Element, source_name: SourceName) -> list[NewsRecord]:
        entries = root.findall(f"{{{ATOM_NAMESPACE}}}entry")
        items: list[NewsRecord] = []
        for entry in entries:
            title = html_to_text(_find_text(entry, "title", ATOM_NAMESPACE))
            source_url = _pick_atom_link(entry) or _find_text(entry, "id", ATOM_NAMESPACE) or ""
            if not title or not source_url:
                continue
            updated = _find_text(entry, "updated", ATOM_NAMESPACE) or _find_text(
                entry, "published", ATOM_NAMESPACE
            )
            categories = _collect_atom_categories(entry)
            summary = html_to_text(_find_text(entry, "summary", ATOM_NAMESPACE))
            content = html_to_text(_find_text(entry, "content", ATOM_NAMESPACE))
            items.append(
                NewsRecord(
                    source_name=source_name,
                    source_url=source_url,
                    title=title,
                    summary=summary or content,
                    raw_category=" | ".join(categories) if categories else None,
                    published_at=datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    if updated
                    else None,
                    scraped_at=utcnow(),
                    news_type=NewsType.OTHER,
                    raw_payload={"categories": categories},
                )
            )
        return items
