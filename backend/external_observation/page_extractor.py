"""Deterministic, local-only extraction of already fetched response bytes."""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from typing import NamedTuple

import trafilatura

from .safe_fetcher import SafeFetchError, SafeFetchResponse


class PageExtractionError(SafeFetchError):
    pass


class ExtractedPage(NamedTuple):
    content_type: str
    charset: str | None
    title: str | None
    extracted_text: str
    extractor_id: str
    content_sha256: str


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._inside_title = False
        self.rows: list[str] = []

    def handle_starttag(self, tag, attrs):
        self._inside_title = tag.casefold() == "title"

    def handle_endtag(self, tag):
        if tag.casefold() == "title":
            self._inside_title = False

    def handle_data(self, data):
        if self._inside_title:
            self.rows.append(data)


def extract_page(response: SafeFetchResponse, *, max_chars: int = 8_000) -> ExtractedPage:
    raw_content_type = response.headers.get("content-type", "")
    content_type, charset = _content_type(raw_content_type)
    digest = hashlib.sha256(response.body).hexdigest()
    decoded = _decode(response.body, charset)
    if content_type == "text/html":
        title_parser = _TitleParser()
        title_parser.feed(decoded)
        try:
            text = trafilatura.extract(
                decoded,
                output_format="txt",
                include_comments=False,
                include_images=False,
                include_links=False,
                favor_precision=True,
                no_fallback=False,
            ) or ""
        except Exception as error:
            raise PageExtractionError("page_unreadable_or_dynamic") from error
        extractor_id = "trafilatura-2"
        title = _normalize(" ".join(title_parser.rows)) or None
    elif content_type == "text/plain":
        text = decoded
        extractor_id = "plain-text"
        title = None
    else:
        try:
            text = json.dumps(json.loads(decoded), ensure_ascii=False, indent=2, sort_keys=True)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise PageExtractionError("invalid_json") from error
        extractor_id = "json-local"
        title = None
    normalized = _normalize(text)
    if len(normalized) < 24:
        raise PageExtractionError("page_unreadable_or_dynamic")
    return ExtractedPage(
        content_type=content_type,
        charset=charset,
        title=title,
        extracted_text=normalized[:max_chars],
        extractor_id=extractor_id,
        content_sha256=digest,
    )


def _content_type(value: str) -> tuple[str, str | None]:
    media, *parameters = value.split(";")
    content_type = media.strip().casefold()
    charset = next((part.split("=", 1)[1].strip().strip('"') for part in parameters if "=" in part and part.split("=", 1)[0].strip().casefold() == "charset"), None)
    if content_type == "text/html" or content_type == "text/plain" or content_type == "application/json" or content_type.endswith("+json"):
        return content_type, charset
    raise PageExtractionError("unsupported_content_type")


def _decode(value: bytes, charset: str | None) -> str:
    if charset:
        try:
            return value.decode(charset, errors="replace")
        except LookupError:
            pass
    return value.decode("utf-8", errors="replace")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
