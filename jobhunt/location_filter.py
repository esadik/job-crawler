"""Decide whether a posting's location is in-scope for the user.

Rules:
  * Empty / unknown location → KEEP (don't drop something we can't verify).
  * "Remote" or "remote-friendly" phrasing → KEEP (user can judge).
  * Any match against ``cfg.locations_allowed`` (case-insensitive,
    word-boundary) → KEEP.
  * Province-code match (e.g. ``(BC)``) → KEEP.
  * Any match against the explicit OUT-OF-PROVINCE token list below → DROP.
    This catches Job Bank's "Halifax (NS)" / "Toronto (ON)" / "Montréal (QC)"
    style location strings even if the user only lists allowed names.
  * Otherwise → KEEP (we err on the side of showing the posting).
"""

from __future__ import annotations

import re

from .config import UserConfig


# Province codes OTHER than BC. If a posting's location matches one of these
# (``(ON)``, ``(QC)`` etc.), it's clearly out of scope.
_OTHER_PROVINCE_CODES = {
    "AB", "SK", "MB", "ON", "QC", "NB", "NS", "PE", "NL", "YT", "NT", "NU",
}

# Full province / territory names other than BC. Matched case-insensitively,
# as whole words.
_OTHER_PROVINCE_NAMES_RE = re.compile(
    r"\b(?:alberta|saskatchewan|manitoba|ontario|qu[eé]bec|quebec|"
    r"new brunswick|nova scotia|prince edward island|newfoundland|"
    r"labrador|yukon|northwest territories|nunavut)\b",
    re.I,
)

_REMOTE_RE = re.compile(r"\bremote\b|\banywhere\b|\btelework\b|\bwork from home\b", re.I)
_PROV_CODE_RE = re.compile(r"\b([A-Z]{2})\b")


def _phrase_in(phrase: str, hay_lower: str) -> bool:
    tokens = re.split(r"\s+", phrase.lower().strip())
    tokens = [t for t in tokens if t]
    if not tokens:
        return False
    pat = r"\s+".join(re.escape(t) for t in tokens)
    return re.search(rf"\b{pat}\b", hay_lower) is not None


def is_in_scope(location: str, cfg: UserConfig) -> bool:
    if not cfg.strict_location_filter:
        return True

    text = (location or "").strip()
    if not text:
        return True

    lower = text.lower()

    codes = {m.group(1) for m in _PROV_CODE_RE.finditer(text)}
    user_pc = cfg.province_code.upper() if cfg.province_code else ""

    # Explicit same-province signal → keep.
    if user_pc and user_pc in codes:
        return True
    for allowed in cfg.locations_allowed:
        if _phrase_in(allowed, lower):
            return True

    # Explicit other-province signal → drop, even if the posting also says
    # "remote". A "remote in Ontario" job is out of scope for a BC-only
    # filter.
    if (codes & _OTHER_PROVINCE_CODES) or _OTHER_PROVINCE_NAMES_RE.search(lower):
        return False

    # Remote with no province attached → keep.
    if _REMOTE_RE.search(lower):
        return True

    return True
