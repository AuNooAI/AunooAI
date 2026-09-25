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

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PersonaSet:
    """One site's roles, the text that tells a model how to pick one, and the
    matching lines for Jev (author_role_jev)."""

    def __init__(self, name: str, definitions: Dict[str, str], guide: str,
                 reasons: Dict[str, str], person_roles: Tuple[str, ...],
                 groups: Optional[Dict[str, str]] = None,
                 display: Optional[Dict[str, Dict[str, str]]] = None,
                 not_audiences: Tuple[str, ...] = (),
                 hidden: Tuple[str, ...] = (),
                 open_pairs: Tuple[Tuple[str, str], ...] = ()):
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
        # Rows left out of the view altogether; the posts keep their roles.
        self.hidden = set(hidden)
        # The pairs the view opens on, first match wins; empty = the default pairs.
        self.open_pairs = tuple(tuple(p) for p in open_pairs)

    def group(self, role: str) -> str:
        return self.groups.get(role, role)

    # --- the settings page stores a set as JSON -----------------------------

    def to_dict(self) -> Dict[str, Any]:
        try:
            from app.services.audience_voices import ROLE_LABELS
        except ImportError:
            ROLE_LABELS = {}
        audiences = []
        for key, definition in self.definitions.items():
            shown = self.group(key)
            show = ("hidden" if shown in self.hidden else
                    "button" if shown in self.not_audiences or shown in _ALWAYS_BUTTONS else "column")
            audiences.append({
                "key": key,
                "label": ((self.display.get(key) or {}).get("label")
                          or (ROLE_LABELS.get(key) or {}).get("label")
                          or key.replace("_", " ").title()),
                "definition": definition,
                "reason": self.reasons.get(key, ""),
                "show": show,
                "group": self.groups.get(key, ""),
            })
        return {"name": self.name, "audiences": audiences, "guide": self.guide,
                "open_pairs": [list(p) for p in self.open_pairs],
                "person_roles": sorted(self.person_roles)}

    @classmethod
    def from_dict(cls, name: str, d: Dict[str, Any]) -> "PersonaSet":
        auds = d.get("audiences") or []
        definitions = {a["key"]: a["definition"] for a in auds}
        reasons = {a["key"]: (a.get("reason") or a["definition"][:80]) for a in auds}
        groups = {a["key"]: a["group"] for a in auds if a.get("group")}
        display = {a["key"]: {"label": a.get("label") or a["key"],
                              "plural": (a.get("label") or a["key"]).lower(),
                              "hint": a["definition"][:160]} for a in auds}
        not_audiences = tuple(a["key"] for a in auds if a.get("show") == "button")
        hidden = tuple(a["key"] for a in auds if a.get("show") == "hidden")
        return cls(name=d.get("name") or name, definitions=definitions,
                   guide=d.get("guide") or "", reasons=reasons,
                   person_roles=tuple(d.get("person_roles") or ("unknown",)),
                   groups=groups, display=display, not_audiences=not_audiences,
                   hidden=hidden, open_pairs=tuple(tuple(p) for p in d.get("open_pairs") or ()))

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
        "retailer": "Sells THE BRAND'S OWN books or products for money: a bookshop, second-hand or antiquarian dealer, online store, or sales or deal bot giving a price, stock or a buy link for the brand's title. NOT a seller: someone sharing a free or open-access paper or ebook (academic or reader), a publicist promoting another publisher's books, or anyone selling a service such as homework or exam help (spam, so unknown)",
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
    # Oliver, 25 Sep: still too many rows. The view shows the six audiences
    # and Competitors; press, the brand's own posts, journal accounts and
    # bystanders are left out of it.
    hidden=("journalist", "brand", "journal_society", "unknown", "unclassified"),
)

HEALTH = PersonaSet(
    name="health",
    definitions={
        "patient": "Uses, is on, is referred to or prescribed the brand's programme, app, clinic or medication, including someone weighing it up, logging progress or complaining about it",
        "clinician": "A GP, doctor, nurse, dietitian, pharmacist or other health professional speaking as such, including one who says 'we' or 'our patients', or is asked to prescribe or refer",
        "payer": "Pays for or commissions the programme for other people: an NHS commissioner or ICB, a health insurer or Krankenkasse, an employer or benefits team offering it to staff",
        "caregiver": "A relative or carer describing someone else's care",
        "journalist": "A news outlet, reporter or newsletter, or a market analyst, investor or industry commentator",
        "academic": "A researcher or scientist discussing evidence about the programme or the condition",
        "employee": "Works or worked for the brand, speaking as staff",
        "brand": "The brand's own account (including country accounts), its staff speaking for it, affiliates, or paid promotion (#ad, sponsored, affiliate links)",
        "competitor": "The author IS a rival programme, clinic or company in the same market, its staff or its paid promotion",
        "unknown": "Recipes, memes, jokes, commentary or ads that show no use of the programme and no role above",
    },
    guide=(
        "The brand runs a health programme, clinic or app. Judge who is speaking from what the post says "
        "and how the author speaks. Anyone using, on, referred to or prescribed it is a patient, never a "
        "customer. Anyone who prescribes, refers, treats, or speaks as a health professional is a clinician. "
        "An organisation or team paying for it on others' behalf (a commissioner, insurer or employer) is a "
        "payer. When nothing in the text shows who is speaking, answer unknown rather than guessing."
    ),
    reasons={
        "patient": "Uses or is referred to the programme",
        "clinician": "Speaks as a health professional",
        "payer": "Pays for or commissions it for others",
        "caregiver": "Speaks about someone else's care",
        "journalist": "Reports on or analyses the market",
        "academic": "Discusses the evidence",
        "employee": "Speaks as staff",
        "brand": "The brand's own account or its promotion",
        "competitor": "A rival company's own account",
        "unknown": "Nothing in the post shows who is speaking",
    },
    person_roles=("patient", "caregiver", "unknown"),
    groups={"employee": "brand", "academic": "journalist"},
    display={
        "patient": {"label": "Patients", "plural": "patients", "hint": "People using, referred to or prescribed the programme"},
        "clinician": {"label": "Clinicians", "plural": "clinicians", "hint": "GPs, doctors, nurses, dietitians and pharmacists"},
        "payer": {"label": "Payers & commissioners", "plural": "payers and commissioners", "hint": "NHS commissioners, insurers and employers paying for it"},
        "caregiver": {"label": "Carers", "plural": "carers", "hint": "Relatives and carers"},
        "journalist": {"label": "Press & analysts", "plural": "press and analysts", "hint": "Reporters, analysts, investors and researchers"},
        "academic": {"label": "Researchers", "plural": "researchers", "hint": "Researchers discussing the evidence"},
        "employee": {"label": "Employees", "plural": "employees", "hint": "Current or former staff"},
        "brand": {"label": "Brand voice", "plural": "brand accounts", "hint": "The brand's own accounts, staff and paid promotion"},
        "competitor": {"label": "Competitors", "plural": "competitors", "hint": "Rival programmes' and clinics' own accounts"},
        "unknown": {"label": "Bystanders", "plural": "bystanders", "hint": "Commentary with no sign of a role"},
    },
    not_audiences=("journalist",),
    hidden=("brand", "unknown", "unclassified"),
    open_pairs=(("clinician", "patient"), ("payer", "patient")),
)

_SETS: Dict[str, PersonaSet] = {"publisher": PUBLISHER, "health": HEALTH}

# Rows the Voices view never makes a column, whatever a set says.
_ALWAYS_BUTTONS = {"brand", "competitor", "journal_society", "unknown", "unclassified"}
# The account registry and the fallbacks write these roles, so every set needs them.
REQUIRED_KEYS = ("brand", "competitor", "unknown")
_KEY_RE = re.compile(r"^[a-z][a-z_]{1,39}$")

_DB_TTL_S = 60
_db_cache: Dict[str, Any] = {"at": 0.0, "set": None, "loaded": False}


def invalidate() -> None:
    """Forget the cached saved set (after a save on the settings page)."""
    _db_cache.update(at=0.0, set=None, loaded=False)


def saved_set() -> Optional[PersonaSet]:
    """The set saved on the settings page (the active row), cached for a minute."""
    now = time.monotonic()
    if _db_cache["loaded"] and now - _db_cache["at"] < _DB_TTL_S:
        return _db_cache["set"]
    found = None
    try:
        from sqlalchemy import text
        from app.database import get_database_instance
        conn = get_database_instance()._temp_get_connection()
        try:
            if conn.execute(text("SELECT to_regclass('voices_persona_sets')")).scalar():
                row = conn.execute(text(
                    "SELECT name, content FROM voices_persona_sets WHERE active "
                    "ORDER BY id DESC LIMIT 1")).fetchone()
                if row:
                    content = row[1] if isinstance(row[1], dict) else json.loads(row[1])
                    found = PersonaSet.from_dict(row[0], content)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 - fall back to the set in code
        logger.warning("voices_personas: saved set lookup failed: %s", e)
    _db_cache.update(at=now, set=found, loaded=True)
    return found


def active_set() -> Optional[PersonaSet]:
    """The site's persona set: the one saved on the settings page, else the
    set VOICES_PERSONAS names, else None for the standard list."""
    saved = saved_set()
    if saved is not None:
        return saved
    name = (os.getenv("VOICES_PERSONAS") or "").strip().lower()
    if not name or name == "default":
        return None
    return _SETS.get(name)


def standard_dict() -> Dict[str, Any]:
    """The standard list (social_eval_service.AUTHOR_ROLES) as an editable set."""
    from app.services import audience_voices, author_role_jev, social_eval_service
    audiences = []
    for key in social_eval_service.AUTHOR_ROLES:
        meta = audience_voices.ROLE_LABELS.get(key, {})
        audiences.append({
            "key": key, "label": meta.get("label") or key.title(),
            "definition": author_role_jev.CRITERIA.get(key, meta.get("hint", "")),
            "reason": author_role_jev.REASONS.get(key, ""),
            "show": "button" if key in _ALWAYS_BUTTONS else "column",
            "group": "",
        })
    keys = {a["key"] for a in audiences}
    return {"name": "standard", "audiences": audiences, "guide": social_eval_service._ROLE_GUIDE.strip(),
            "open_pairs": [list(p) for p in audience_voices.PREFERRED_PAIRS if set(p) <= keys],
            "person_roles": ["customer", "patient", "caregiver", "unknown"]}


def preset(name: str) -> Optional[Dict[str, Any]]:
    if name == "standard":
        return standard_dict()
    s = _SETS.get(name)
    return s.to_dict() if s else None


def validate(d: Dict[str, Any]) -> List[str]:
    """Problems with a set from the settings page; empty when it can be saved."""
    problems: List[str] = []
    auds = d.get("audiences") or []
    keys = [a.get("key", "") for a in auds]
    for a in auds:
        k = a.get("key", "")
        if not _KEY_RE.match(k):
            problems.append(f"'{k}': keys are 2-40 lower-case letters and underscores")
        if not (a.get("label") or "").strip():
            problems.append(f"'{k}': needs a label")
        if not (a.get("definition") or "").strip():
            problems.append(f"'{k}': needs a definition; the model picks by it")
        elif len(a["definition"]) > 600:
            problems.append(f"'{k}': definition over 600 characters")
        if a.get("show") not in ("column", "button", "hidden"):
            problems.append(f"'{k}': show must be column, button or hidden")
        if a.get("group") and a["group"] not in keys:
            problems.append(f"'{k}': groups into '{a['group']}', which is not in the set")
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        problems.append("keys used twice: " + ", ".join(sorted(dupes)))
    missing = [k for k in REQUIRED_KEYS if k not in keys]
    if missing:
        problems.append("the set must keep: " + ", ".join(missing))
    for pair in d.get("open_pairs") or []:
        if len(pair) != 2 or any(p not in keys for p in pair):
            problems.append(f"open pair {pair}: both keys must be in the set")
    if len(d.get("guide") or "") > 3000:
        problems.append("guide over 3000 characters")
    return problems


def save(d: Dict[str, Any], name: str, updated_by: str) -> int:
    """Store a set as the site's active set; earlier rows stay as history."""
    from sqlalchemy import text
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        conn.execute(text("UPDATE voices_persona_sets SET active = false WHERE active"))
        new_id = conn.execute(text("""
            INSERT INTO voices_persona_sets (name, content, active, updated_by)
            VALUES (:n, CAST(:c AS JSONB), true, :u) RETURNING id
        """), {"n": name, "c": json.dumps(d), "u": updated_by}).scalar()
        conn.commit()
    finally:
        conn.close()
    invalidate()
    return int(new_id)


def clear_saved(updated_by: str) -> None:
    """Go back to the set in code (VOICES_PERSONAS or the standard list)."""
    from sqlalchemy import text
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        conn.execute(text("UPDATE voices_persona_sets SET active = false, updated_by = :u WHERE active"),
                     {"u": updated_by})
        conn.commit()
    finally:
        conn.close()
    invalidate()


def all_role_names() -> Tuple[str, ...]:
    """Every role any set can produce, for code that must recognise all of them."""
    seen = []
    for s in _SETS.values():
        seen.extend(r for r in s.roles if r not in seen)
    return tuple(seen)
