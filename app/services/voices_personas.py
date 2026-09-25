"""Per-site persona sets: the list of author roles a site's Voices view uses.

The standard list (patient, clinician, customer, retailer ...) lives in
social_eval_service.AUTHOR_ROLES and fits a health provider or a consumer
brand. It does not fit a publisher, where the people talking are authors,
academics, librarians and students, so a site picks its set with
VOICES_PERSONAS. Unset (or "default") keeps the standard list and its prompt
text byte for byte.

The publisher set was tested on wileytest (24 Sep 2026): kimi through the
site's own Bedrock read 220 posts about Wiley, Elsevier, SAGE and Pearson and
got 36 of 40 right against blind labels. Four roles were asked for (author,
academic, librarian, student); editor_reviewer, journal_society and educator
came from reading the posts, where journal accounts, editors leaving and
teachers using courseware are all common.
"""
from __future__ import annotations

import os
from typing import Dict, Optional, Tuple


class PersonaSet:
    """One site's roles, the text that tells a model how to pick one, and the
    matching lines for Jev (author_role_jev)."""

    def __init__(self, name: str, definitions: Dict[str, str], guide: str,
                 reasons: Dict[str, str], person_roles: Tuple[str, ...],
                 groups: Optional[Dict[str, str]] = None,
                 display: Optional[Dict[str, Dict[str, str]]] = None,
                 not_audiences: Tuple[str, ...] = ()):
        self.name = name
        self.definitions = definitions
        self.guide = guide
        self.reasons = reasons
        # Readings a paid-promotion marker may turn into "brand".
        self.person_roles = set(person_roles)
        # The Voices view shows groups, not every stored role: each post keeps
        # its detailed role; `groups` maps it to the column it is shown in.
        self.groups = groups or {}
        self.display = display or {}
        # Groups that are rows, not columns (press, the brand, look-alikes...).
        self.not_audiences = set(not_audiences)

    def group(self, role: str) -> str:
        return self.groups.get(role, role)

    @property
    def roles(self) -> Tuple[str, ...]:
        return tuple(self.definitions)

    def role_prompt(self) -> str:
        """The part of a model prompt that lists the roles and says how to pick."""
        lines = "\n".join(f"- {k}: {v}" for k, v in self.definitions.items())
        return f"Pick author_role from this list only:\n{lines}\n{self.guide} "


PUBLISHER = PersonaSet(
    name="publisher",
    definitions={
        "author": "Speaks about their OWN work published, accepted, submitted or under review with the brand: their paper, book, chapter, APC or submission experience ('our new paper', 'my latest for')",
        "editor_reviewer": "A journal editor, editorial-board member or peer reviewer speaking in that role, including editors joining or resigning",
        "journal_society": "The account of a journal, book series or learned society promoting its own issues, papers, calls or events",
        "academic": "A researcher, lecturer or scientist sharing or discussing research published by the brand that is NOT their own, or discussing academic publishing as a researcher",
        "librarian": "A librarian, library, library consortium or university library speaking about subscriptions, access, deals, databases, training or webinars",
        "student": "A student speaking as such: textbooks, courseware, assignments, exams, citing a book for coursework",
        "educator": "A teacher or instructor speaking about teaching with the brand's textbooks, courseware or assessments",
        "reader": "A member of the public reading, buying or sharing the brand's books or articles out of personal interest, not as a researcher",
        "retailer": "Sells the brand's books or products: a bookshop, second-hand or antiquarian book dealer, online store, sales or deal bot ('selling well', 'in stock', price and buy link), or an affiliate or shop link",
        "professional": "Works in publishing, research integrity or scholarly communication but not for the brand (consultant, industry analyst, open-access advocate speaking professionally)",
        "journalist": "A news outlet, reporter, newsletter or watchdog (e.g. Retraction Watch) reporting on the brand",
        "investor": "A shareholder, stock commentator or market analyst",
        "employee": "Works or worked for the brand, speaking as staff",
        "brand": "The brand's own account (incl. imprint, subject or regional accounts), its staff speaking for it, or its paid promotion",
        "competitor": "The author IS a rival publisher or education company, its staff or its paid promotion",
        "unknown": "Commentary, jokes, politics or protest about the company with no sign of any role above, or nothing shows who is speaking",
    },
    guide=(
        "The brand is a publisher or education company. Judge who is speaking from what the post "
        "says and how the author speaks. Someone sharing their own paper or book is an author; "
        "someone sharing another person's paper is an academic (or a reader if they speak as a "
        "member of the public). A journal's or society's own account is journal_society, even when "
        "the brand publishes the journal; only the brand's own corporate, imprint or subject "
        "accounts are brand. A post that only cites a book or article as a source, with no sign of "
        "who is speaking, is unknown. When nothing in the text shows who is speaking, answer "
        "unknown rather than guessing."
    ),
    reasons={
        "author": "Shares their own published or submitted work",
        "editor_reviewer": "Speaks as an editor or peer reviewer",
        "journal_society": "A journal's or society's own account",
        "academic": "A researcher discussing published research",
        "librarian": "Speaks for a library",
        "student": "Speaks as a student",
        "educator": "Speaks as a teacher using the materials",
        "reader": "Reads or buys the brand's books or articles",
        "retailer": "Sells the brand's books or products",
        "professional": "Works in scholarly publishing, not for the brand",
        "journalist": "Reports on the brand",
        "investor": "Comments on the business or the stock",
        "employee": "Speaks as staff",
        "brand": "The brand's own account or its promotion",
        "competitor": "A rival publisher's own account",
        "unknown": "Nothing in the post shows who is speaking",
    },
    person_roles=("reader", "student", "unknown"),
    # Six audiences on screen (Oliver, 25 Sep: fifteen was too many).
    groups={
        "editor_reviewer": "author",
        "educator": "student",
        "investor": "journalist",
        "professional": "journalist",
        "employee": "brand",
    },
    display={
        "author": {"label": "Authors & editors", "plural": "authors and editors", "hint": "Authors sharing their own work, and journal editors and reviewers"},
        "academic": {"label": "Researchers", "plural": "researchers", "hint": "Researchers sharing or discussing work published by the brand"},
        "librarian": {"label": "Libraries", "plural": "libraries", "hint": "Libraries and consortia on subscriptions, access and deals"},
        "student": {"label": "Students & teachers", "plural": "students and teachers", "hint": "Students and teachers on textbooks, courseware and exams"},
        "reader": {"label": "Readers", "plural": "readers", "hint": "Members of the public reading or buying for themselves"},
        "retailer": {"label": "Sellers", "plural": "sellers", "hint": "Bookshops, second-hand dealers, sales bots and shop links"},
        "journalist": {"label": "Press & analysts", "plural": "press and analysts", "hint": "Reporters, market analysts, investors and industry commentators"},
        "brand": {"label": "Brand voice", "plural": "brand accounts", "hint": "The brand's own accounts, staff and paid promotion"},
    },
    not_audiences=("journalist",),
)

_SETS: Dict[str, PersonaSet] = {"publisher": PUBLISHER}


def active_set() -> Optional[PersonaSet]:
    """The site's persona set, or None for the standard list."""
    name = (os.getenv("VOICES_PERSONAS") or "").strip().lower()
    if not name or name == "default":
        return None
    return _SETS.get(name)


def all_role_names() -> Tuple[str, ...]:
    """Every role any set can produce, for code that must recognise all of them."""
    seen = []
    for s in _SETS.values():
        seen.extend(r for r in s.roles if r not in seen)
    return tuple(seen)
