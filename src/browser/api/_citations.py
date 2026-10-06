# SPDX-FileCopyrightText: 2026 The University of St Andrews
# SPDX-License-Identifier: GPL-3.0-or-later
"""Citation filter API support."""

from flask import Blueprint, jsonify, request, current_app

from browser.db.pool import get_pool

from .filter import FilterError, MAX_FILTER_LENGTH, parse_filter
from .query import build_citation_query, build_urls_query

MAX_LIMIT = 200
DEFAULT_LIMIT = 50

citations = Blueprint("admin", __name__, url_prefix="/citations")


def fetch_citations(tree: Node, limit: int, offset: int) -> list[dict]:
    """Run the filter against the database; each citation gets a 'URLs' list."""
    sql, params = build_citation_query(tree, limit, offset)
    conn = get_pool().acquire()  # type: ignore
    try:
        with conn.cursor(dictionary=True) as cur:
            current_app.logger.debug(
                "Executing SQL: %s with arguments: %s",
                sql,
                ", ".join(str(p) for p in params),
            )
            cur.execute(sql, params)
            rows = cur.fetchall()
            print(rows)
            urls: dict[int, list[dict]] = {}
            url_query = build_urls_query([r["CitationId"] for r in rows])
            if url_query:
                current_app.logger.debug(
                    "Executing SQL: %s with arguments: %s",
                    url_query[0],
                    ", ".join(str(p) for p in url_query[1]),
                )
                cur.execute(*url_query)
                for u in cur.fetchall():
                    urls.setdefault(u["CitationId"], []).append(
                        {"type": u["Type"], "url": u["URL"]}
                    )
    finally:
        conn.close()
    for r in rows:
        r["URLs"] = urls.get(r["CitationId"], [])
    return rows


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


@citations.get("")
def get_citations():
    raw = request.args.get("filter", "").strip()
    if not raw:
        return jsonify(error="missing required query parameter 'filter'"), 400
    if len(raw) > MAX_FILTER_LENGTH:
        return jsonify(error=f"filter exceeds {MAX_FILTER_LENGTH} characters"), 400

    try:
        limit = _int_arg("limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _int_arg("offset", 0, 0, 10**9)
    except ValueError as e:
        return jsonify(error=str(e)), 400

    try:
        tree, validation_errors = parse_filter(raw)
    except FilterError as e:
        return (
            jsonify(
                error="invalid filter syntax",
                details=[{"pos": e.pos, "message": e.message}],
            ),
            400,
        )

    if validation_errors:
        return jsonify(error="invalid filter values", details=validation_errors), 400

    rows = fetch_citations(tree, limit, offset)
    return (
        jsonify(
            filter=raw,
            parsed=tree.to_dict(),
            limit=limit,
            offset=offset,
            count=len(rows),
            citations=[_jsonable(r) for r in rows],
        ),
        200,
    )
