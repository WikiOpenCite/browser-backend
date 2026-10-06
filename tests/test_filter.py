import pytest

from browser.api.filter import (
    MAX_DEPTH,
    MAX_FILTER_LENGTH,
    MAX_TERMS,
    BoolOp,
    FilterError,
    Term,
    parse_filter,
    tokenise,
    validate_doi,
    validate_openaccess,
    validate_openalex,
    validate_orcid,
    validate_wiki,
)

VALID_ORCID = "0000-0002-1825-0097"
VALID_ORCID_X = "0000-0002-9079-593X"  # checksum digit is X


# --------------------------------------------------------------------------
# Validators
# --------------------------------------------------------------------------
class TestValidateDoi:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("10.1038/nature12373", "10.1038/nature12373"),
            ("  10.1038/nature12373  ", "10.1038/nature12373"),
            ("doi:10.1038/NATURE12373", "10.1038/nature12373"),
            ("DOI:10.1038/nature12373", "10.1038/nature12373"),
            ("https://doi.org/10.1038/nature12373", "10.1038/nature12373"),
            ("http://dx.doi.org/10.1038/nature12373", "10.1038/nature12373"),
            ("10.1016/S0022-2836(05)80360-2", "10.1016/s0022-2836(05)80360-2"),
        ],
    )
    def test_valid(self, raw, expected):
        assert validate_doi(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "nope",
            "10.123/abc",
            "10.1038/",
            "11.1038/abc",
            "10.1038/has space",
            "https://example.com/10.1038/abc",
        ],
    )
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            validate_doi(raw)


class TestValidateOrcid:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            (VALID_ORCID, VALID_ORCID),
            (VALID_ORCID_X, VALID_ORCID_X),
            (VALID_ORCID_X.lower(), VALID_ORCID_X),
            (f"https://orcid.org/{VALID_ORCID}", VALID_ORCID),
            (f"  {VALID_ORCID}  ", VALID_ORCID),
        ],
    )
    def test_valid(self, raw, expected):
        assert validate_orcid(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "0000-0002-1825",
            "0000000218250097",
            "0000-0002-1825-009",
            "abcd-0002-1825-0097",
            "0000-0002-1825-00977",
        ],
    )
    def test_bad_format(self, raw):
        with pytest.raises(ValueError, match="expected"):
            validate_orcid(raw)

    def test_bad_checksum(self):
        with pytest.raises(ValueError, match="checksum"):
            validate_orcid("0000-0002-1825-0098")


class TestValidateOpenalex:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("W2741809807", "W2741809807"),
            ("w2741809807", "W2741809807"),
            ("A5023888391", "A5023888391"),
            ("https://openalex.org/W2741809807", "W2741809807"),
            ("T10001", "T10001"),
        ],
    )
    def test_valid(self, raw, expected):
        assert validate_openalex(raw) == expected

    @pytest.mark.parametrize("raw", ["", "W", "2741809807", "X123", "W12a", "W-123"])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            validate_openalex(raw)


class TestValidateOpenaccess:
    @pytest.mark.parametrize("raw", ["true", "TRUE", "True", "1", " true "])
    def test_true(self, raw):
        assert validate_openaccess(raw) is True

    @pytest.mark.parametrize("raw", ["false", "FALSE", "0", " false "])
    def test_false(self, raw):
        assert validate_openaccess(raw) is False

    @pytest.mark.parametrize("raw", ["", "yes", "no", "2", "maybe"])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            validate_openaccess(raw)


# class TestValidateWiki:
#     @pytest.mark.parametrize(
#         "raw, expected",
#         [
#             ("Q42", "Q42"),
#             ("q42", "Q42"),
#             ("https://www.wikidata.org/wiki/Q42", "Q42"),
#             ("https://www.wikidata.org/entity/Q42", "Q42"),
#             (
#                 "https://en.wikipedia.org/wiki/Douglas_Adams",
#                 "https://en.wikipedia.org/wiki/Douglas_Adams",
#             ),
#             (
#                 "https://de.wikipedia.org/wiki/Berlin",
#                 "https://de.wikipedia.org/wiki/Berlin",
#             ),
#         ],
#     )
#     def test_valid(self, raw, expected):
#         assert validate_wiki(raw) == expected

#     @pytest.mark.parametrize(
#         "raw",
#         [
#             "",
#             "Q",
#             "Q0",
#             "Q-1",
#             "42",
#             "Douglas_Adams",
#             "https://example.com/wiki/Foo",
#             "https://en.wikipedia.org/",
#         ],
#     )
#     def test_invalid(self, raw):
#         with pytest.raises(ValueError):
#             validate_wiki(raw)


# --------------------------------------------------------------------------
# Tokeniser
# --------------------------------------------------------------------------
class TestTokenise:
    def kinds(self, text):
        return [t.kind for t in tokenise(text)]

    def test_single_term(self):
        toks = tokenise("doi:10.1038/x")
        assert [t.kind for t in toks] == ["TERM", "EOF"]
        assert (toks[0].field, toks[0].value, toks[0].pos) == ("doi", "10.1038/x", 0)

    def test_operators_and_parens(self):
        assert self.kinds("(wiki:Q1 AND wiki:Q2) OR wiki:Q3") == [
            "LPAREN",
            "TERM",
            "AND",
            "TERM",
            "RPAREN",
            "OR",
            "TERM",
            "EOF",
        ]

    def test_operators_case_insensitive(self):
        assert self.kinds("wiki:Q1 and wiki:Q2 Or wiki:Q3") == [
            "TERM",
            "AND",
            "TERM",
            "OR",
            "TERM",
            "EOF",
        ]

    def test_field_names_lowercased(self):
        assert tokenise("DOI:10.1038/x")[0].field == "doi"

    def test_field_starting_with_or_is_not_operator(self):
        toks = tokenise(f"orcid:{VALID_ORCID}")
        assert toks[0].kind == "TERM" and toks[0].field == "orcid"

    def test_quoted_value_keeps_spaces_and_parens(self):
        toks = tokenise('doi:"10.1016/S0022-2836(05)80360-2" AND wiki:Q1')
        assert toks[0].value == "10.1016/S0022-2836(05)80360-2"
        assert toks[1].kind == "AND"

    def test_unquoted_value_stops_at_close_paren(self):
        assert self.kinds("(wiki:Q1)") == ["LPAREN", "TERM", "RPAREN", "EOF"]
        assert tokenise("(wiki:Q1)")[1].value == "Q1"

    def test_positions(self):
        toks = tokenise("wiki:Q1 AND wiki:Q2")
        assert [t.pos for t in toks[:3]] == [0, 8, 12]

    @pytest.mark.parametrize(
        "text, fragment",
        [
            ("doi:", "missing value"),
            ('doi:""', "empty value"),
            ('doi:"unterminated', "unterminated"),
            ("justaword", "expected"),
            ("@@@", "unexpected character"),
            ("wiki:Q1 NOT wiki:Q2", "expected"),
        ],
    )
    def test_errors(self, text, fragment):
        with pytest.raises(FilterError, match=fragment):
            tokenise(text)


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------
class TestParser:
    def test_single_term(self):
        tree, errors = parse_filter("wiki:Q42")
        assert tree == Term("wiki", "Q42")
        assert errors == []

    def test_values_are_normalised(self):
        tree, _ = parse_filter("openaccess:TRUE")
        assert tree == Term("openaccess", True)

    def test_and_chain_is_flattened(self):
        tree, _ = parse_filter("wiki:Q1 AND wiki:Q2 AND wiki:Q3")
        assert tree == BoolOp(
            "and", [Term("wiki", "Q1"), Term("wiki", "Q2"), Term("wiki", "Q3")]
        )

    def test_or_chain_is_flattened(self):
        tree, _ = parse_filter("wiki:Q1 OR wiki:Q2 OR wiki:Q3")
        assert tree == BoolOp(
            "or", [Term("wiki", "Q1"), Term("wiki", "Q2"), Term("wiki", "Q3")]
        )

    def test_and_binds_tighter_than_or(self):
        tree, _ = parse_filter("wiki:Q1 OR wiki:Q2 AND wiki:Q3")
        assert tree == BoolOp(
            "or",
            [
                Term("wiki", "Q1"),
                BoolOp("and", [Term("wiki", "Q2"), Term("wiki", "Q3")]),
            ],
        )

    def test_parentheses_override_precedence(self):
        tree, _ = parse_filter("(wiki:Q1 OR wiki:Q2) AND wiki:Q3")
        assert tree == BoolOp(
            "and",
            [
                BoolOp("or", [Term("wiki", "Q1"), Term("wiki", "Q2")]),
                Term("wiki", "Q3"),
            ],
        )

    def test_redundant_parentheses_collapse(self):
        tree, _ = parse_filter("((wiki:Q1))")
        assert tree == Term("wiki", "Q1")

    def test_to_dict(self):
        tree, _ = parse_filter("wiki:Q1 AND openaccess:false")
        assert tree.to_dict() == {
            "op": "and",
            "children": [
                {"field": "wiki", "value": "Q1"},
                {"field": "openaccess", "value": False},
            ],
        }

    def test_all_fields_together(self):
        tree, errors = parse_filter(
            f"doi:10.1038/x AND orcid:{VALID_ORCID} AND openalex:W1 "
            "AND openaccess:true AND wiki:Q1"
        )
        assert errors == []
        assert [c.field for c in tree.children] == [
            "doi",
            "orcid",
            "openalex",
            "openaccess",
            "wiki",
        ]

    # --- validation errors are collected, not raised -----------------------
    def test_unknown_field_collected(self):
        _, errors = parse_filter("foo:bar")
        assert len(errors) == 1
        assert errors[0]["field"] == "foo" and "unknown field" in errors[0]["message"]

    def test_all_validation_errors_collected_with_positions(self):
        _, errors = parse_filter("doi:nope AND foo:bar AND orcid:0000-0002-1825-0098")
        assert [e["field"] for e in errors] == ["doi", "foo", "orcid"]
        assert [e["pos"] for e in errors] == [0, 13, 25]

    # --- syntax errors are raised ------------------------------------------
    @pytest.mark.parametrize(
        "text, fragment",
        [
            ("", "empty"),
            ("   ", "empty"),
            ("wiki:Q1 AND", "expected a term"),
            ("AND wiki:Q1", "expected a term"),
            ("wiki:Q1 OR OR wiki:Q2", "expected a term"),
            ("wiki:Q1 wiki:Q2", "unexpected"),
            ("(wiki:Q1", "closing parenthesis"),
            ("wiki:Q1)", "unexpected"),
            ("()", "expected a term"),
        ],
    )
    def test_syntax_errors(self, text, fragment):
        with pytest.raises(FilterError, match=fragment):
            parse_filter(text)

    def test_error_carries_position(self):
        with pytest.raises(FilterError) as exc:
            parse_filter("wiki:Q1 AND")
        assert exc.value.pos == 11

    # --- limits ------------------------------------------------------------
    def test_max_terms_allowed(self):
        text = " OR ".join(["wiki:Q1"] * MAX_TERMS)
        tree, errors = parse_filter(text)
        assert errors == [] and len(tree.children) == MAX_TERMS

    def test_too_many_terms(self):
        text = " OR ".join(["wiki:Q1"] * (MAX_TERMS + 1))
        with pytest.raises(FilterError, match="too many terms"):
            parse_filter(text)

    def test_max_depth_allowed(self):
        text = "(" * MAX_DEPTH + "wiki:Q1" + ")" * MAX_DEPTH
        tree, _ = parse_filter(text)
        assert tree == Term("wiki", "Q1")

    def test_too_deep(self):
        n = MAX_DEPTH + 1
        text = "(" * n + "wiki:Q1" + ")" * n
        with pytest.raises(FilterError, match="nested"):
            parse_filter(text)
