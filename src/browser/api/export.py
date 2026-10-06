"""Stream citation rows (as returned by filter_api.iter_citations) as CSV."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Iterable, Iterator

# (CSV header, row key). URLs is special-cased: a list of {"type", "url"} dicts.
COLUMNS = [
    ("CitationId", "CitationId"),
    ("Wiki", "Wiki"),
    ("PageId", "PageId"),
    ("PageTitle", "PageTitle"),
    ("RevisionAdded", "RevisionAdded"),
    ("AddedAt", "AddedAt"),
    ("AddedBy", "AddedBy"),
    ("RevisionRemoved", "RevisionRemoved"),
    ("RemovedAt", "RemovedAt"),
    ("RemovedBy", "RemovedBy"),
    ("WorkId", "WorkId"),
    ("Title", "Title"),
    ("PublicationDate", "PublicationDate"),
    ("Language", "Language"),
    ("OAStatus", "OAStatus"),
    ("OA_Url", "OA_Url"),
    ("DOI", "DOI"),
    ("ISBN", "ISBN"),
    ("ISSN", "ISSN"),
    ("PMID", "PMID"),
    ("PMCID", "PMCID"),
    ("URLs", "URLs"),
]
HEADERS = [h for h, _ in COLUMNS]

URL_SEPARATOR = " | "
BOM = "\ufeff"  # lets Excel open the file as UTF-8
FLUSH_EVERY = 500  # rows per chunk sent to the client

# A cell beginning with one of these can be executed as a formula by Excel / Sheets.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe(text: str) -> str:
    """Neutralise spreadsheet formula injection (titles and URLs are user-controlled)."""
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def _cell(key: str, value) -> str | int | float:
    if value is None:
        return ""
    if key == "URLs":
        return _safe(URL_SEPARATOR.join(u["url"] for u in value))
    if isinstance(value, datetime):
        return value.isoformat(" ")
    if hasattr(value, "isoformat"):  # date
        return value.isoformat()
    if isinstance(value, str):
        return _safe(value)
    return value


def format_row(row: dict) -> list:
    return [_cell(key, row.get(key)) for _, key in COLUMNS]


def stream_csv(rows: Iterable[dict], flush_every: int = FLUSH_EVERY) -> Iterator[str]:
    """Yield the CSV in chunks so the whole result set is never held in memory."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    buf.write(BOM)
    writer.writerow(HEADERS)
    for n, row in enumerate(rows, start=1):
        writer.writerow(format_row(row))
        if n % flush_every == 0:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
    yield buf.getvalue()
