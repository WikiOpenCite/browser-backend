"""
Flask endpoint that accepts a filter string of AND / OR combined arguments.

    GET /api/works?filter=doi:10.1038/nature12373 AND (openaccess:true OR orcid:0000-0002-1825-0097)

Valid fields: doi, orcid, openalex, openaccess, wiki,
              added_after, added_before, removed_after, removed_before

Date fields take YYYY-MM-DD or YYYY-MM-DDTHH:MM[:SS] (UTC) and form a half-open
range: *_after is inclusive (>=), *_before is exclusive (<). For example
    added_after:2026-01-01 AND added_before:2026-02-01      (all of January)

Grammar (AND binds tighter than OR; parentheses override):
    expr   := and_ ( "OR" and_ )*
    and_   := atom ( "AND" atom )*
    atom   := "(" expr ")" | field ":" value
    value  := "quoted string" | unquoted-run-without-whitespace-or-parens

Values containing spaces or parentheses (some DOIs have them) must be quoted:
    doi:"10.1016/S0022-2836(05)80360-2"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Union

MAX_FILTER_LENGTH = 2000
MAX_TERMS = 25
MAX_DEPTH = 6


# --------------------------------------------------------------------------
# Field validators: each takes the raw string, returns a normalised value,
# or raises ValueError with a human-readable message.
# --------------------------------------------------------------------------
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
OPENALEX_RE = re.compile(
    r"^[WASICPFT]\d+$"
)  # works, authors, sources, institutions, concepts, publishers, funders, topics
WIKIDATA_RE = re.compile(r"^Q[1-9]\d*$")
WIKIPEDIA_URL_RE = re.compile(
    r"^https?://([a-z\-]{2,12})\.wikipedia\.org/wiki/\S+$", re.I
)


def validate_doi(value: str) -> str:
    v = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", value.strip(), flags=re.I)
    if not DOI_RE.match(v):
        raise ValueError("invalid DOI; expected the form 10.<registrant>/<suffix>")
    return v.lower()  # DOIs are case-insensitive


def _orcid_checksum_ok(orcid: str) -> bool:
    """ISO 7064 MOD 11-2 check, as used by ORCID."""
    digits = orcid.replace("-", "")
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    result = (12 - total % 11) % 11
    return digits[-1] == ("X" if result == 10 else str(result))


def validate_orcid(value: str) -> str:
    v = re.sub(r"^https?://orcid\.org/", "", value.strip(), flags=re.I).upper()
    if not ORCID_RE.match(v):
        raise ValueError("invalid ORCID; expected 0000-0000-0000-000X")
    if not _orcid_checksum_ok(v):
        raise ValueError("invalid ORCID; checksum digit does not match")
    return v


def validate_openalex(value: str) -> str:
    v = re.sub(r"^https?://openalex\.org/", "", value.strip(), flags=re.I).upper()
    if not OPENALEX_RE.match(v):
        raise ValueError(
            "invalid OpenAlex ID; expected a letter (W, A, S, I, C, P, F, T) followed by digits, e.g. W2741809807"
        )
    return v


def validate_openaccess(value: str) -> bool:
    v = value.strip().lower()
    if v in ("true", "1"):
        return True
    if v in ("false", "0"):
        return False
    raise ValueError("invalid openaccess value; expected true or false")


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?$")
_DATE_FORMATS = {10: "%Y-%m-%d", 16: "%Y-%m-%dT%H:%M", 19: "%Y-%m-%dT%H:%M:%S"}


def validate_date(value: str) -> str:
    """A UTC date or datetime; returned as ISO 8601 (YYYY-MM-DDTHH:MM:SS)."""
    v = value.strip()
    if not DATE_RE.match(v):
        raise ValueError(
            "invalid date; expected YYYY-MM-DD or YYYY-MM-DDTHH:MM[:SS] (UTC)"
        )
    try:
        return datetime.strptime(v, _DATE_FORMATS[len(v)]).isoformat()
    except ValueError:
        raise ValueError("invalid date; that day or time does not exist")


def validate_wiki(value: str) -> str:
    """Currently not validated"""
    return value.strip()


VALIDATORS: dict[str, Callable[[str], Union[str, bool]]] = {
    "doi": validate_doi,
    "orcid": validate_orcid,
    "openalex": validate_openalex,
    "openaccess": validate_openaccess,
    "wiki": validate_wiki,
    "added_after": validate_date,
    "added_before": validate_date,
    "removed_after": validate_date,
    "removed_before": validate_date,
}


# --------------------------------------------------------------------------
# AST
# --------------------------------------------------------------------------
@dataclass
class Term:
    field: str
    value: Union[str, bool]

    def to_dict(self):
        return {"field": self.field, "value": self.value}


@dataclass
class BoolOp:
    op: str  # "and" | "or"
    children: list

    def to_dict(self):
        return {"op": self.op, "children": [c.to_dict() for c in self.children]}


Node = Union[Term, BoolOp]


# --------------------------------------------------------------------------
# Tokeniser + recursive-descent parser
# --------------------------------------------------------------------------
class FilterError(Exception):
    def __init__(self, message: str, pos: int):
        super().__init__(message)
        self.message, self.pos = message, pos


@dataclass
class Token:
    kind: str  # LPAREN RPAREN AND OR TERM EOF
    pos: int
    field: str = ""
    value: str = ""


WORD_RE = re.compile(r"([A-Za-z_]+)(:)?")
UNQUOTED_RE = re.compile(r"[^\s()]+")


def tokenise(text: str) -> list[Token]:
    tokens, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == "(":
            tokens.append(Token("LPAREN", i))
            i += 1
        elif ch == ")":
            tokens.append(Token("RPAREN", i))
            i += 1
        else:
            m = WORD_RE.match(text, i)
            if not m:
                raise FilterError(f"unexpected character {ch!r}", i)
            word, colon = m.group(1), m.group(2)
            if not colon:
                if word.upper() in ("AND", "OR"):
                    tokens.append(Token(word.upper(), i))
                    i = m.end()
                    continue
                raise FilterError(
                    f"expected 'field:value', AND or OR but found {word!r}", i
                )
            start, i = i, m.end()
            if i < n and text[i] == '"':
                end = text.find('"', i + 1)
                if end == -1:
                    raise FilterError("unterminated quoted value", i)
                value, i = text[i + 1 : end], end + 1
            else:
                vm = UNQUOTED_RE.match(text, i)
                if not vm:
                    raise FilterError(f"missing value for {word!r}", start)
                value, i = vm.group(0), vm.end()
            if not value:
                raise FilterError(f"empty value for {word!r}", start)
            tokens.append(Token("TERM", start, field=word.lower(), value=value))
    tokens.append(Token("EOF", n))
    return tokens


class Parser:
    def __init__(self, text: str):
        self.tokens = tokenise(text)
        self.i = 0
        self.term_count = 0
        self.validation_errors: list[dict] = []

    def peek(self) -> Token:
        return self.tokens[self.i]

    def next(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def parse(self) -> Node:
        if self.peek().kind == "EOF":
            raise FilterError("filter is empty", 0)
        node = self.parse_or(depth=0)
        tok = self.peek()
        if tok.kind != "EOF":
            raise FilterError(f"unexpected {tok.kind}", tok.pos)
        return node

    def parse_or(self, depth: int) -> Node:
        if depth > MAX_DEPTH:
            raise FilterError(
                f"filter nested more than {MAX_DEPTH} levels deep", self.peek().pos
            )
        children = [self.parse_and(depth)]
        while self.peek().kind == "OR":
            self.next()
            children.append(self.parse_and(depth))
        return children[0] if len(children) == 1 else BoolOp("or", children)

    def parse_and(self, depth: int) -> Node:
        children = [self.parse_atom(depth)]
        while self.peek().kind == "AND":
            self.next()
            children.append(self.parse_atom(depth))
        return children[0] if len(children) == 1 else BoolOp("and", children)

    def parse_atom(self, depth: int) -> Node:
        tok = self.next()
        if tok.kind == "LPAREN":
            node = self.parse_or(depth + 1)
            close = self.next()
            if close.kind != "RPAREN":
                raise FilterError("missing closing parenthesis", close.pos)
            return node
        if tok.kind == "TERM":
            return self.make_term(tok)
        raise FilterError(f"expected a term or '(' but found {tok.kind}", tok.pos)

    def make_term(self, tok: Token) -> Term:
        self.term_count += 1
        if self.term_count > MAX_TERMS:
            raise FilterError(f"too many terms (max {MAX_TERMS})", tok.pos)
        validator = VALIDATORS.get(tok.field)
        if validator is None:
            self.validation_errors.append(
                {
                    "pos": tok.pos,
                    "field": tok.field,
                    "message": f"unknown field; valid fields are {', '.join(VALIDATORS)}",
                }
            )
            return Term(tok.field, tok.value)
        try:
            return Term(tok.field, validator(tok.value))
        except ValueError as e:
            self.validation_errors.append(
                {
                    "pos": tok.pos,
                    "field": tok.field,
                    "value": tok.value,
                    "message": str(e),
                }
            )
            return Term(tok.field, tok.value)


def parse_filter(text: str) -> tuple[Node, list[dict]]:
    parser = Parser(text)
    tree = parser.parse()
    return tree, parser.validation_errors
