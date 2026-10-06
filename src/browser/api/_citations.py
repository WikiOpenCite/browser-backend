# SPDX-FileCopyrightText: 2026 The University of St Andrews
# SPDX-License-Identifier: GPL-3.0-or-later
"""Citation filter API support."""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, current_app, Response

from browser.db.pool import get_pool

from .filter import FilterError, MAX_FILTER_LENGTH, parse_filter
from .query import (
    build_citation_query,
    build_urls_query,
    build_count_query,
    build_export_query,
)
from .export import stream_csv

MAX_LIMIT = 200
DEFAULT_LIMIT = 50
EXPORT_BATCH_SIZE = 1000

citations = Blueprint("admin", __name__, url_prefix="/citations")


def _attach_urls(cur, rows: list[dict]) -> None:
    """Add a 'URLs' list to each row (fetched separately to avoid row fan-out)."""
    urls: dict[int, list[dict]] = {}
    url_query = build_urls_query([r["CitationId"] for r in rows])
    if url_query:
        cur.execute(*url_query)
        for u in cur.fetchall():
            urls.setdefault(u["CitationId"], []).append(
                {"type": u["Type"], "url": u["URL"]}
            )
    for r in rows:
        r["URLs"] = urls.get(r["CitationId"], [])


def fetch_citations(tree: Node, limit: int, offset: int) -> tuple[list[dict], int]:
    """Run the filter; returns (one page of citations, total matches)."""

    sql, params = build_citation_query(tree, limit, offset)
    count_sql, count_params = build_count_query(tree)
    conn = get_pool().acquire()  # type: ignore
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(count_sql, count_params)
            total = int(cur.fetchone()["Total"])
            cur.execute(sql, params)
            rows = cur.fetchall()
            _attach_urls(cur, rows)
    finally:
        conn.close()
    return rows, total


def iter_citations(tree: Node, batch_size: int = EXPORT_BATCH_SIZE) -> Iterator[dict]:
    """Yield *every* citation matching the filter, a batch at a time (keyset paged)."""
    conn = get_pool().acquire()  # type: ignore
    try:
        with conn.cursor(dictionary=True) as cur:
            after_id = 0
            while True:
                sql, params = build_export_query(tree, batch_size, after_id)
                cur.execute(sql, params)
                rows = cur.fetchall()
                if not rows:
                    return
                _attach_urls(cur, rows)
                yield from rows
                if len(rows) < batch_size:
                    return
                after_id = rows[-1]["CitationId"]
    finally:
        conn.close()


def _jsonable(row: dict) -> dict:
    return {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in row.items()}


def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"'{name}' must be an integer")
    if not lo <= value <= hi:
        raise ValueError(f"'{name}' must be between {lo} and {hi}")
    return value


def _parse_request_filter():
    """Read and parse ?filter=. Returns (raw, tree, None) or (None, None, error_response)."""
    raw = request.args.get("filter", "").strip()
    if not raw:
        return (
            None,
            None,
            (jsonify(error="missing required query parameter 'filter'"), 400),
        )
    if len(raw) > MAX_FILTER_LENGTH:
        return (
            None,
            None,
            (jsonify(error=f"filter exceeds {MAX_FILTER_LENGTH} characters"), 400),
        )

    try:
        tree, validation_errors = parse_filter(raw)
    except FilterError as e:
        return (
            None,
            None,
            (
                jsonify(
                    error="invalid filter syntax",
                    details=[{"pos": e.pos, "message": e.message}],
                ),
                400,
            ),
        )
    if validation_errors:
        return (
            None,
            None,
            (jsonify(error="invalid filter values", details=validation_errors), 400),
        )
    return raw, tree, None


@citations.get("")
def get_citations():
    raw, tree, error = _parse_request_filter()
    if error:
        return error

    try:
        limit = _int_arg("limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _int_arg("offset", 0, 0, 10**9)
    except ValueError as e:
        return jsonify(error=str(e)), 400

    rows, total = fetch_citations(tree, limit, offset)
    return (
        jsonify(
            filter=raw,
            parsed=tree.to_dict(),
            limit=limit,
            offset=offset,
            count=len(rows),  # rows in this page
            total=total,  # all matches, ignoring limit/offset
            citations=[_jsonable(r) for r in rows],
        ),
        200,
    )


@citations.get("export")
def citations_csv():
    """Download every citation matching ?filter= as CSV (no paging), streamed."""
    _, tree, error = _parse_request_filter()
    if error:
        return error

    filename = f"citations-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.csv"
    return Response(
        stream_csv(iter_citations(tree)),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",  # stop nginx buffering the stream
        },
    )
