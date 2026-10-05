"""Query expressions: parse what the operator typed, compile it per provider.

A keyword like ``"Sunstar" OR サンスター OR (GUM AND toothpaste) -recall``
carries phrases, alternatives, conjunctions and exclusions. Before this
module the NewsData collector stripped the quotes and brackets, kept the
first two words, and fell back to the literal query ``news`` when nothing
survived. The meaning of the search was lost and the run looked successful.

``parse_expression`` turns the text into a small tree. ``compile_for`` renders
that tree in one provider's syntax and says whether the meaning survived:
``exact`` (everything expressed), ``expanded`` (a declared, bounded rewrite
that keeps the meaning) or ``unsupported`` (do not send; report
``unsupported_query``). Nothing is ever substituted silently and Unicode is
passed through untouched.

Grammar (precedence low to high): OR, AND, NOT.

- ``OR`` or ``|`` or ``,`` separates alternatives.
- ``AND`` or ``+`` joins terms; two terms side by side are also AND.
- ``NOT`` or a leading ``-`` on a term excludes it.
- ``"..."`` (straight or curly quotes) is an exact phrase.
- ``( ... )`` groups.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work package 9.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Union

STATUS_EXACT = "exact"
STATUS_EXPANDED = "expanded"
STATUS_UNSUPPORTED = "unsupported"


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Term:
    text: str
    phrase: bool = False

    def render(self) -> str:
        if self.phrase or _needs_quotes(self.text):
            return '"' + self.text.replace('"', "") + '"'
        return self.text


@dataclass(frozen=True)
class And:
    children: "tuple[Node, ...]"


@dataclass(frozen=True)
class Or:
    children: "tuple[Node, ...]"


@dataclass(frozen=True)
class Not:
    child: "Node"


Node = Union[Term, And, Or, Not]


@dataclass
class Expression:
    """The parsed query. ``root`` is None for empty input."""

    original: str
    root: Optional[Node]

    @property
    def empty(self) -> bool:
        return self.root is None

    def terms(self) -> List[Term]:
        """Every positive term, in order. Exclusions are left out."""
        out: List[Term] = []
        _collect_terms(self.root, out, positive=True)
        return out

    def excluded_terms(self) -> List[Term]:
        out: List[Term] = []
        _collect_terms(self.root, out, positive=False)
        return out

    def render(self) -> str:
        """Canonical text with explicit operators."""
        return _render(self.root) if self.root is not None else ""


def _collect_terms(node: Optional[Node], out: List[Term], *, positive: bool, negated: bool = False) -> None:
    if node is None:
        return
    if isinstance(node, Term):
        if negated != positive:
            out.append(node)
        return
    if isinstance(node, Not):
        _collect_terms(node.child, out, positive=positive, negated=not negated)
        return
    for child in node.children:
        _collect_terms(child, out, positive=positive, negated=negated)


def _needs_quotes(text: str) -> bool:
    return bool(re.search(r"\s", text)) or text.upper() in ("AND", "OR", "NOT")


def _render(node: Node, parent: Optional[str] = None) -> str:
    if isinstance(node, Term):
        return node.render()
    if isinstance(node, Not):
        inner = _render(node.child, "NOT")
        if not isinstance(node.child, Term):
            inner = f"({inner})"
        return f"NOT {inner}"
    op = "AND" if isinstance(node, And) else "OR"
    if op == "AND":
        # ``a AND b NOT c``: the documented shape for every provider here.
        positives = [_render(c, op) for c in node.children if not isinstance(c, Not)]
        negatives = [_render(c, op) for c in node.children if isinstance(c, Not)]
        text = " AND ".join(positives)
        if negatives:
            text = (text + " " if text else "") + " ".join(negatives)
    else:
        parts = [_render(c, op) for c in node.children]
        text = f" {op} ".join(parts)
    # OR under AND needs brackets; AND under OR does not change meaning but
    # brackets keep the provider from guessing precedence.
    if parent is not None and parent != op:
        return f"({text})"
    return text


# ---------------------------------------------------------------------------
# Tokeniser and parser
# ---------------------------------------------------------------------------

_QUOTE_OPEN = '"“”‘’«»'
_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<quote>["“”«»])(?P<phrase>[^"“”«»]*)(?:["“”«»]|$)
  | (?P<lpar>\()
  | (?P<rpar>\))
  | (?P<comma>,)
  | (?P<pipe>\|)
  | (?P<plus>\+(?=\s))
  | (?P<minus>(?<!\S)-(?=\S))
  | (?P<word>[^\s()",|]+)
    """,
    re.VERBOSE,
)

_OPERATOR_WORDS = {"AND": "and", "OR": "or", "NOT": "not"}


@dataclass
class _Tok:
    kind: str
    value: str = ""


def _tokenize(text: str) -> List[_Tok]:
    out: List[_Tok] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            pos += 1
            continue
        pos = m.end()
        kind = next(k for k in ("ws", "quote", "lpar", "rpar", "comma", "pipe", "plus", "minus", "word")
                    if m.group(k) is not None)
        if kind == "ws":
            continue
        if kind == "quote":
            phrase = (m.group("phrase") or "").strip()
            if phrase:
                out.append(_Tok("phrase", phrase))
            continue
        if kind == "lpar":
            out.append(_Tok("("))
        elif kind == "rpar":
            out.append(_Tok(")"))
        elif kind in ("comma", "pipe"):
            out.append(_Tok("or"))
        elif kind == "plus":
            out.append(_Tok("and"))
        elif kind == "minus":
            out.append(_Tok("not"))
        else:
            word = m.group("word")
            op = _OPERATOR_WORDS.get(word.upper())
            if op and word.isupper():
                out.append(_Tok(op))
            else:
                # A trailing "+" glued to a word ("C++") stays part of it.
                out.append(_Tok("word", word))
    return out


class _Parser:
    def __init__(self, tokens: List[_Tok]):
        self.toks = tokens
        self.i = 0

    def peek(self) -> Optional[_Tok]:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self) -> _Tok:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def parse(self) -> Optional[Node]:
        node = self.parse_or()
        # Stray closing brackets are ignored rather than failing the query.
        while self.peek() is not None:
            self.take()
            more = self.parse_or()
            if more is not None:
                node = And((node, more)) if node is not None else more
        return node

    def parse_or(self) -> Optional[Node]:
        parts: List[Node] = []
        first = self.parse_and()
        if first is not None:
            parts.append(first)
        while self.peek() is not None and self.peek().kind == "or":
            self.take()
            nxt = self.parse_and()
            if nxt is not None:
                parts.append(nxt)
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else Or(tuple(_flatten(parts, Or)))

    def parse_and(self) -> Optional[Node]:
        parts: List[Node] = []
        while True:
            tok = self.peek()
            if tok is None or tok.kind in ("or", ")"):
                break
            if tok.kind == "and":
                self.take()
                continue
            node = self.parse_not()
            if node is not None:
                parts.append(node)
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else And(tuple(_flatten(parts, And)))

    def parse_not(self) -> Optional[Node]:
        tok = self.peek()
        if tok is not None and tok.kind == "not":
            self.take()
            inner = self.parse_not()
            if inner is None:
                return None
            return Not(inner)
        return self.parse_atom()

    def parse_atom(self) -> Optional[Node]:
        tok = self.peek()
        if tok is None:
            return None
        if tok.kind == "(":
            self.take()
            inner = self.parse_or()
            if self.peek() is not None and self.peek().kind == ")":
                self.take()
            return inner
        if tok.kind == ")":
            self.take()
            return None
        if tok.kind == "phrase":
            self.take()
            return Term(tok.value, phrase=True)
        if tok.kind == "word":
            self.take()
            return Term(tok.value)
        # An operator with nothing to apply to.
        self.take()
        return None


def _flatten(parts: Sequence[Node], cls) -> List[Node]:
    out: List[Node] = []
    for p in parts:
        if isinstance(p, cls):
            out.extend(p.children)
        else:
            out.append(p)
    return out


def parse_expression(text: Optional[str]) -> Expression:
    """Parse operator text into an ``Expression``. Never raises; empty or
    operator-only input gives an empty expression."""
    raw = (text or "").strip()
    if not raw:
        return Expression(original=raw, root=None)
    tokens = _tokenize(raw)
    root = _Parser(tokens).parse()
    return Expression(original=raw, root=root)


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


@dataclass
class Compiled:
    query: Optional[str]
    status: str
    dropped: List[str] = field(default_factory=list)
    reason: Optional[str] = None
    #: For an expansion: the several provider queries that together cover
    #: the expression. Empty when ``query`` alone does.
    queries: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status != STATUS_UNSUPPORTED and bool(self.query)


@dataclass(frozen=True)
class Capabilities:
    phrases: bool = True
    conjunction: bool = True
    alternatives: bool = True
    exclusions: bool = True
    grouping: bool = True
    #: Exclusions only as ``positive NOT term`` at the top level, each
    #: excluded part a single term or phrase.
    flat_exclusions_only: bool = False
    max_length: Optional[int] = None


#: What each provider's query language can express. NewsData: ``q`` takes
#: AND, OR, NOT, quoted phrases and brackets, at most 512 characters. Its
#: documentation shows NOT only as ``a NOT b``; a NOT inside an OR group or
#: applied to a group is not documented, so it is refused rather than guessed.
PROVIDER_CAPABILITIES = {
    "newsdata": Capabilities(flat_exclusions_only=True, max_length=512),
    "newsapi": Capabilities(max_length=500),
    "generic": Capabilities(),
}


def compile_for(provider: str, expr: Expression) -> Compiled:
    """Render ``expr`` for ``provider``. The result's ``status`` says whether
    the provider sees the same meaning the operator wrote."""
    caps = PROVIDER_CAPABILITIES.get((provider or "").lower(), PROVIDER_CAPABILITIES["generic"])
    if expr.empty:
        return Compiled(query=None, status=STATUS_EXACT, reason="empty expression")
    root = expr.root
    problem = _unsupported_reason(root, caps)
    if problem:
        return Compiled(query=None, status=STATUS_UNSUPPORTED, reason=problem)
    text = _render(root)
    if caps.max_length is not None and len(text) > caps.max_length:
        return Compiled(query=None, status=STATUS_UNSUPPORTED,
                        reason=f"compiled query is {len(text)} characters; {provider} allows {caps.max_length}")
    return Compiled(query=text, status=STATUS_EXACT)


def _unsupported_reason(node: Node, caps: Capabilities) -> Optional[str]:
    if isinstance(node, Not):
        if not caps.exclusions:
            return "exclusions are not supported"
        return "an exclusion needs a positive term beside it"
    if isinstance(node, Term):
        if node.phrase and not caps.phrases:
            return "exact phrases are not supported"
        return None
    if isinstance(node, Or) and not caps.alternatives:
        return "alternatives are not supported"
    if isinstance(node, And) and not caps.conjunction:
        return "conjunctions are not supported"
    if caps.flat_exclusions_only:
        if isinstance(node, Or):
            for child in node.children:
                if _contains_not(child):
                    return "an exclusion inside an alternative cannot be expressed"
        if isinstance(node, And):
            positives = [c for c in node.children if not isinstance(c, Not)]
            if not positives:
                return "an exclusion needs a positive term beside it"
            for child in node.children:
                if isinstance(child, Not) and not isinstance(child.child, Term):
                    return "only a single term or phrase can be excluded"
                if not isinstance(child, Not) and _contains_not(child):
                    return "a nested exclusion cannot be expressed"
        return _check_children(node, caps, allow_not=caps.flat_exclusions_only and isinstance(node, And))
    return _check_children(node, caps, allow_not=True)


def _check_children(node: Node, caps: Capabilities, *, allow_not: bool) -> Optional[str]:
    if isinstance(node, Term):
        return None
    if isinstance(node, Not):
        return None if allow_not else "a nested exclusion cannot be expressed"
    for child in node.children:
        if isinstance(child, Not):
            if not allow_not:
                return "a nested exclusion cannot be expressed"
            continue
        if isinstance(child, Term):
            if child.phrase and not caps.phrases:
                return "exact phrases are not supported"
            continue
        if not caps.grouping:
            return "grouping is not supported"
        inner = _unsupported_reason(child, caps) if caps.flat_exclusions_only else _check_children(child, caps, allow_not=True)
        if inner:
            return inner
    return None


def _contains_not(node: Node) -> bool:
    if isinstance(node, Not):
        return True
    if isinstance(node, Term):
        return False
    return any(_contains_not(c) for c in node.children)
