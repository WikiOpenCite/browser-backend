import sqlite3

import pytest

from browser.api.query import (
    CLOSED_STATUS,
    OPEN_ACCESS_STATUSES,
    UnsupportedFilter,
    build_citation_query,
    build_urls_query,
    build_where,
)

from browser.api.filter import Term, parse_filter


def where(text):
    tree, errors = parse_filter(text)
    assert errors == []
    return build_where(tree)


# --------------------------------------------------------------------------
# SQL shape
# --------------------------------------------------------------------------
class TestBuildWhere:
    def test_doi(self):
        assert where("doi:10.1038/x") == ("w.DOI = ?", ["10.1038/x"])

    def test_wiki(self):
        assert where("wiki:enwiki") == ("p.Wiki = ?", ["enwiki"])

    def test_orcid_hyphens_stripped(self):
        sql, params = where("orcid:0000-0002-1825-0097")
        assert "a.ORCID = ?" in sql and sql.startswith("EXISTS")
        assert params == ["0000000218250097"]

    @pytest.mark.parametrize(
        "value, fragment, param",
        [
            ("W42", "w.OpenAlexId = ?", 42),
            ("A42", "wa.AuthorId = ?", 42),
            ("I42", "wi.InstitutionId = ?", 42),
        ],
    )
    def test_openalex_kinds(self, value, fragment, param):
        sql, params = where(f"openalex:{value}")
        assert fragment in sql
        assert params == [param]

    def test_openaccess_true(self):
        sql, params = where("openaccess:true")
        assert sql == "w.OAStatus IN (?, ?, ?, ?, ?)"
        assert params == list(OPEN_ACCESS_STATUSES)

    def test_openaccess_false(self):
        assert where("openaccess:false") == ("w.OAStatus = ?", [CLOSED_STATUS])

    def test_and_or_nesting_and_param_order(self):
        sql, params = where("doi:10.1001/a AND (wiki:enwiki OR wiki:dewiki)")
        assert sql == "(w.DOI = ? AND (p.Wiki = ? OR p.Wiki = ?))"
        assert params == ["10.1001/a", "enwiki", "dewiki"]

    def test_placeholder_count_matches_params(self):
        sql, params = where(
            "(openaccess:true OR orcid:0000-0002-1825-0097) AND openalex:I5 AND wiki:enwiki"
        )
        assert sql.count("?") == len(params)

    def test_values_never_interpolated(self):
        evil = "x'; DROP TABLE Work; --"
        sql, params = build_where(Term("doi", evil))
        assert evil not in sql and params == [evil]

    def test_unsupported_openalex_kind(self):
        with pytest.raises(UnsupportedFilter):
            build_where(Term("openalex", "S123"))

    def test_unknown_field(self):
        with pytest.raises(UnsupportedFilter):
            build_where(Term("nope", "x"))


class TestBuildCitationQuery:
    def test_structure(self):
        sql, params = build_citation_query(Term("wiki", "enwiki"), limit=10, offset=20)
        assert "FROM Citation c" in sql
        assert "LEFT JOIN Work w" in sql  # Citation.Work is nullable
        assert "LEFT JOIN Revision rr" in sql  # RevisionRemoved is nullable
        assert "WHERE p.Wiki = ?" in sql
        assert sql.rstrip().endswith("ORDER BY c.CitationId\nLIMIT ? OFFSET ?")
        assert params == ["enwiki", 10, 20]

    def test_selects_work_details(self):
        sql, _ = build_citation_query(Term("wiki", "enwiki"), 1)
        for col in (
            "w.Title",
            "w.DOI",
            "w.OAStatus",
            "p.PageTitle",
            "AddedAt",
            "RemovedAt",
        ):
            assert col in sql


class TestBuildUrlsQuery:
    def test_empty(self):
        assert build_urls_query([]) is None

    def test_ids_are_parameters(self):
        sql, params = build_urls_query([3, 5, 9])
        assert "IN (?, ?, ?)" in sql and params == [3, 5, 9]


# --------------------------------------------------------------------------
# Execute the generated SQL on sample data
# --------------------------------------------------------------------------
DDL = """
CREATE TABLE Author (OpenAlexId INT PRIMARY KEY, Name TEXT, ORCID TEXT);
CREATE TABLE Work (OpenAlexId INT PRIMARY KEY, Title TEXT, PublicationDate TEXT, Language TEXT,
                   OAStatus TEXT, OA_Url TEXT, DOI TEXT, ISBN TEXT, PMID INT, PMCID INT, ISSN TEXT);
CREATE TABLE WorkAuthors (AuthorId INT, WorkId INT);
CREATE TABLE WorkInstitutions (InstitutionId INT, WorkId INT);
CREATE TABLE Revision (RevisionId INT PRIMARY KEY, ParentId INT, User TEXT, Timestamp TEXT);
CREATE TABLE Page (PageId INT PRIMARY KEY, PageTitle TEXT, Wiki TEXT);
CREATE TABLE Citation (CitationId INTEGER PRIMARY KEY, Page INT, RevisionAdded INT,
                       RevisionRemoved INT, Work INT);
CREATE TABLE URL (URLId INTEGER PRIMARY KEY, Citation INT, Type TEXT, URL TEXT);

INSERT INTO Author VALUES (100, 'Ann', '0000000218250097'), (200, 'Bob', '0000000290795930');
INSERT INTO Work (OpenAlexId, Title, DOI, OAStatus) VALUES
  (1, 'Gold paper',   '10.1001/a', 'OA_CATEGORY_GOLD'),
  (2, 'Closed paper', '10.1001/b', 'OA_CATEGORY_CLOSED'),
  (3, 'Green paper',  '10.1001/c', 'OA_CATEGORY_GREEN'),
  (4, 'Unknown OA',   '10.1001/d', 'OA_CATEGORY_UNSPECIFIED');
INSERT INTO WorkAuthors VALUES (100, 1), (200, 1), (200, 2);
INSERT INTO WorkInstitutions VALUES (900, 3);
INSERT INTO Revision VALUES (1, NULL, 'alice', '2026-01-01'), (2, 1, 'bob', '2026-02-01');
INSERT INTO Page VALUES (10, 'Page EN', 'enwiki'), (20, 'Seite DE', 'dewiki');
INSERT INTO Citation VALUES
  (1, 10, 1, NULL, 1),
  (2, 10, 1, 2,    2),
  (3, 20, 1, NULL, 3),
  (4, 20, 1, NULL, 1),
  (5, 10, 1, NULL, NULL),
  (6, 10, 1, NULL, 4);
"""


@pytest.fixture(scope="module")
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    yield conn
    conn.close()


def run(db, text, limit=100, offset=0):
    tree, errors = parse_filter(text)
    assert errors == []
    sql, params = build_citation_query(tree, limit, offset)
    rows = db.execute(sql, params).fetchall()
    return rows


def ids(db, text, **kw):
    return [r["CitationId"] for r in run(db, text, **kw)]


class TestAgainstSampleData:
    def test_doi(self, db):
        assert ids(db, "doi:10.1001/a") == [1, 4]

    def test_work_id(self, db):
        assert ids(db, "openalex:W2") == [2]

    def test_orcid(self, db):
        assert ids(db, "orcid:0000-0002-1825-0097") == [1, 4]

    def test_author_id(self, db):
        assert ids(db, "openalex:A200") == [1, 2, 4]

    def test_institution_id(self, db):
        assert ids(db, "openalex:I900") == [3]

    def test_two_authors_means_both_and_no_duplicate_rows(self, db):
        assert ids(db, "openalex:A100 AND openalex:A200") == [1, 4]

    def test_author_or(self, db):
        assert ids(db, "openalex:A100 OR openalex:I900") == [1, 3, 4]

    def test_open_access_true(self, db):
        assert ids(db, "openaccess:true") == [1, 3, 4]

    def test_open_access_false_is_closed_only(self, db):
        assert ids(db, "openaccess:false") == [2]  # unspecified (6) matches neither

    def test_wiki(self, db):
        assert ids(db, "wiki:dewiki") == [3, 4]

    def test_wiki_only_keeps_citations_without_a_work(self, db):
        rows = run(db, "wiki:enwiki")
        assert [r["CitationId"] for r in rows] == [1, 2, 5, 6]
        unresolved = next(r for r in rows if r["CitationId"] == 5)
        assert unresolved["WorkId"] is None and unresolved["Title"] is None

    def test_work_filters_exclude_unresolved_citations(self, db):
        assert 5 not in ids(db, "openaccess:true OR openaccess:false")

    def test_and_or_precedence(self, db):
        assert ids(db, "wiki:dewiki OR wiki:enwiki AND openaccess:false") == [2, 3, 4]

    def test_parentheses(self, db):
        assert ids(db, "(wiki:dewiki OR wiki:enwiki) AND openaccess:false") == [2]

    def test_joined_columns(self, db):
        row = run(db, "doi:10.1001/b")[0]
        assert row["Title"] == "Closed paper"
        assert row["PageTitle"] == "Page EN" and row["Wiki"] == "enwiki"
        assert row["AddedBy"] == "alice" and row["RemovedBy"] == "bob"
        assert row["RemovedAt"] == "2026-02-01"

    def test_not_removed_has_null_removal(self, db):
        row = run(db, "doi:10.1001/a")[0]
        assert row["RemovedAt"] is None and row["RemovedBy"] is None

    def test_no_matches(self, db):
        assert ids(db, "doi:10.9999/zzz") == []

    def test_paging(self, db):
        assert ids(db, "wiki:enwiki", limit=2) == [1, 2]
        assert ids(db, "wiki:enwiki", limit=2, offset=2) == [5, 6]
        assert ids(db, "wiki:enwiki", limit=2, offset=4) == []

    def test_urls_query_runs(self, db):
        db.execute(
            "INSERT INTO URL (Citation, Type, URL) VALUES (1, 'URL_TYPE_DEFAULT', 'http://x'), (1, 'URL_TYPE_ARCHIVE', 'http://a')"
        )
        sql, params = build_urls_query([1, 2])
        rows = db.execute(sql, params).fetchall()
        assert [(r["CitationId"], r["URL"]) for r in rows] == [
            (1, "http://x"),
            (1, "http://a"),
        ]
