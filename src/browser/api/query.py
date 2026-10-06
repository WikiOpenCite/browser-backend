"""
Translate a validated filter tree (see filter_api.py) into a parameterised SQL
query returning citations joined with their page, revisions and work.

The builder only relies on the *shape* of the tree, so it has no import
dependency on the parser:
    BoolOp -> has .op ("and" | "or") and .children
    Term   -> has .field and .value

All values are passed as bind parameters (? placeholders, DB-API "format"
style as used by PyMySQL / mysql-connector); nothing from the user is ever
interpolated into the SQL text.

Field mapping
    doi         Work.DOI
    orcid       an author of the work has Author.ORCID (stored without hyphens)
    openalex    W<n>: the work itself; A<n>: an author of the work;
                I<n>: an institution of the work
    openaccess  true  -> Work.OAStatus is diamond/gold/green/hybrid/bronze
                false -> Work.OAStatus is closed   (unspecified matches neither)
    wiki        Page.Wiki (wiki database name, e.g. enwiki)
+    added_*     Revision.Timestamp of Citation.RevisionAdded
+    removed_*   Revision.Timestamp of Citation.RevisionRemoved
+                *_after is inclusive (>=) and *_before exclusive (<), so
+                after+before is a half-open range [after, before). Citations
+                that were never removed never match a removed_* condition.

Author / institution conditions use EXISTS sub-queries rather than joins, so
combining them (orcid:A AND orcid:B) means "has both authors" and never
multiplies the citation rows.
"""

from __future__ import annotations

OPEN_ACCESS_STATUSES = (
    "OA_CATEGORY_DIAMOND",
    "OA_CATEGORY_GOLD",
    "OA_CATEGORY_GREEN",
    "OA_CATEGORY_HYBRID",
    "OA_CATEGORY_BRONZE",
)
CLOSED_STATUS = "OA_CATEGORY_CLOSED"

# Work is LEFT JOINed because Citation.Work is nullable (unresolved citations).
SELECT_CITATIONS = """\
SELECT
    c.CitationId,
    c.Page            AS PageId,
    p.PageTitle,
    p.Wiki,
    c.RevisionAdded,
    ra.Timestamp      AS AddedAt,
    ra.`User`         AS AddedBy,
    c.RevisionRemoved,
    rr.Timestamp      AS RemovedAt,
    rr.`User`         AS RemovedBy,
    w.OpenAlexId      AS WorkId,
    w.Title,
    w.PublicationDate,
    w.Language,
    w.OAStatus,
    w.OA_Url,
    w.DOI,
    w.ISBN,
    w.PMID,
    w.PMCID,
    w.ISSN
FROM Citation c
JOIN Page p           ON p.PageId = c.Page
JOIN Revision ra      ON ra.RevisionId = c.RevisionAdded
LEFT JOIN Revision rr ON rr.RevisionId = c.RevisionRemoved
LEFT JOIN Work w      ON w.OpenAlexId = c.Work"""


# filter field -> (SQL column, comparison operator)
DATE_FIELDS = {
    "added_after": ("ra.Timestamp", ">="),
    "added_before": ("ra.Timestamp", "<"),
    "removed_after": ("rr.Timestamp", ">="),
    "removed_before": ("rr.Timestamp", "<"),
}


class UnsupportedFilter(ValueError):
    """The tree contains something this schema cannot express."""


def _term_sql(field: str, value) -> tuple[str, list]:
    if field == "doi":
        return "w.DOI = ?", [value]

    if field == "orcid":
        return (
            "EXISTS (SELECT 1 FROM WorkAuthors wa "
            "JOIN Author a ON a.OpenAlexId = wa.AuthorId "
            "WHERE wa.WorkId = w.OpenAlexId AND a.ORCID = ?)",
            [value.replace("-", "")],
        )

    if field == "openalex":
        kind, number = value[0], int(value[1:])
        if kind == "W":
            return "w.OpenAlexId = ?", [number]
        if kind == "A":
            return (
                "EXISTS (SELECT 1 FROM WorkAuthors wa "
                "WHERE wa.WorkId = w.OpenAlexId AND wa.AuthorId = ?)",
                [number],
            )
        if kind == "I":
            return (
                "EXISTS (SELECT 1 FROM WorkInstitutions wi "
                "WHERE wi.WorkId = w.OpenAlexId AND wi.InstitutionId = ?)",
                [number],
            )
        raise UnsupportedFilter(f"OpenAlex IDs of type {kind!r} cannot be filtered on")

    if field == "openaccess":
        if value:
            marks = ", ".join(["?"] * len(OPEN_ACCESS_STATUSES))
            return f"w.OAStatus IN ({marks})", list(OPEN_ACCESS_STATUSES)
        return "w.OAStatus = ?", [CLOSED_STATUS]

    if field == "wiki":
        return "p.Wiki = ?", [value]

    if field in DATE_FIELDS:
        column, op = DATE_FIELDS[field]
        # validator yields ISO 8601 (...T...); MySQL DATETIME literals use a space
        return f"{column} {op} ?", [value.replace("T", " ")]

    raise UnsupportedFilter(f"unknown field {field!r}")


def build_where(node) -> tuple[str, list]:
    """Recursively convert a filter tree into (sql_fragment, params)."""
    if hasattr(node, "children"):
        parts, params = [], []
        for child in node.children:
            sql, p = build_where(child)
            parts.append(sql)
            params.extend(p)
        return "(" + f" {node.op.upper()} ".join(parts) + ")", params
    return _term_sql(node.field, node.value)


def build_citation_query(tree, limit: int, offset: int = 0) -> tuple[str, list]:
    """Full SELECT for the citations matching `tree`, paged and stably ordered."""
    where, params = build_where(tree)
    sql = (
        f"{SELECT_CITATIONS}\n"
        f"WHERE {where}\n"
        "ORDER BY c.CitationId\n"
        "LIMIT ? OFFSET ?"
    )
    return sql, params + [limit, offset]


def build_urls_query(citation_ids: list[int]) -> tuple[str, list] | None:
    """URLs for a page of citations (fetched separately to avoid row fan-out)."""
    if not citation_ids:
        return None
    marks = ", ".join(["?"] * len(citation_ids))
    sql = (
        "SELECT Citation AS CitationId, `Type`, `URL` "
        f"FROM URL WHERE Citation IN ({marks}) ORDER BY URLId"
    )
    return sql, list(citation_ids)
