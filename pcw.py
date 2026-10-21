"""PCW ("professional content writer"): every genre, framework, technique, hook, platform limit, tone, language,
editing pass, legal rule and 2026 trend a writing job needs, harvested from cited sources, written up as knowledge
cards and tested by writing a demo piece from each card. Writing sessions read it before they write. See CONTRACT.md.

    python pcw.py brief "cold email to D2C founders" [--genre ID] [--platform ID] [--lang ID] [--tone ID]
                                                        exit 1: an unknown id, or no genre card matches the request
    python pcw.py check draft.txt [--genre ID] [--platform ID] [--field NAME]   lint a draft (- or no path: stdin)
                                                        exit 0 pass, 1 fails, 2 usage or unreadable draft
    python pcw.py find "landing page saas" [kind]       search cards (kind: a kind name or an id prefix like plat:)
    python pcw.py card genre:cold_email                 one card in full (null and exit 1 when there is none)
    python pcw.py ids [kind] [words]                    harvested ids (for cross-references)
    python pcw.py validate [file ...]                   harvest + cards (default: everything)
    python pcw.py dupes                                 harvest items that look like the same thing
    python pcw.py batches [kind ...]                    merged harvest -> work/batches/<kind>_<nn>.json
    python pcw.py stats | docs                          counts | regenerate PCW.md

    import sys; sys.path.insert(0, "<path to this folder>"); import pcw
    pcw.brief("press release"); pcw.check_text(text, genre="genre:press_release") -> (fails, warns, info)

Data (harvest/, cards/, work/, PCW.md) is read from the folder this file is in, or from $PCW_HOME when it is set.
"""
import argparse, bisect, json, os, re, sys, unicodedata, warnings
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path

# a value pasted with quotes or spaces (cmd's `set PCW_HOME="<folder>"` keeps the quotes) still names the folder
HERE = Path((os.environ.get("PCW_HOME") or "").strip().strip("\"'").strip() or Path(__file__).parent).resolve()
KINDS = {"genre": "genre", "framework": "fw", "technique": "tech", "hook": "hook", "platform": "plat", "tone": "tone",
         "language": "lang", "editing": "edit", "compliance": "comp", "trend": "trend"}
PREFIX_KIND = {v: k for k, v in KINDS.items()}
ID_RE = re.compile(r"^(%s):[a-z0-9_]+$" % "|".join(KINDS.values()))
STATUS = {"current", "rising", "declining", "dated", "niche"}
CONF = {"high", "medium", "low"}
VALUE = {"high", "medium", "low"}
VERDICT = {"pass", "weak", "wrong", "not_tested"}
UNITS = {"chars", "words", "bytes", "lines", "count", "px", "seconds"}
TREND_FLOOR = "2025-10-04"  # trend evidence must be published on or after this date (12 months before the harvest)
COMMON = ("id", "kind", "name", "status", "summary", "use_for", "avoid", "confidence")
KIND_FIELDS = {
    "genre": ("buyers", "value", "goal", "structure", "length", "frameworks", "techniques", "checklist", "pitfalls",
              "lint", "exemplar_brief"),
    "framework": ("steps", "best_for", "not_for", "mini_example"),
    "technique": ("level", "how", "before", "after", "overuse_signs"),
    "hook": ("templates", "examples", "why_it_works", "works_on", "risk"),
    "platform": ("limits", "formatting", "writing_notes"),
    "tone": ("markers", "avoid", "sample", "fits"),
    "language": ("rules", "mistakes", "sample", "script"),
    "editing": ("steps", "checks"),
    "compliance": ("jurisdiction", "applies_to", "rules", "checks", "as_of"),
    "trend": ("as_of", "evidence", "do", "dont", "half_life_months"),
}
NEEDS_SOURCES = {"platform", "compliance", "trend"}
REF_FIELDS = ("related", "frameworks", "techniques", "hooks", "platforms", "tones", "languages", "compliance", "fits",
              "works_on")
REF_PREFIX = {"frameworks": "fw", "techniques": "tech", "hooks": "hook", "platforms": "plat", "works_on": "plat",
              "tones": "tone", "languages": "lang", "compliance": "comp", "fits": "genre"}  # related, applies_to: any
LINT_KEYS = {"min_words", "max_words", "max_sentence_words", "max_avg_sentence_words", "grade_max", "require", "ban",
             "max_exclamations", "max_emoji", "max_hashtags"}
TEXT_UNITS = ("chars", "words", "bytes", "lines")
# limits[].count: how a chars limit is counted when the source says so (default: visible characters)
COUNT_METHODS = {"x_weighted",  # X: NFC code points, CJK and emoji weigh 2, a URL 23 (twitter-text)
                 "sms",  # the whole message in ONE SMS of the encoding it needs (GSM-7 160 / UCS-2 70)
                 "sms_gsm7", "sms_ucs2",  # a single-SMS limit for that encoding only
                 "sms_gsm7_segment", "sms_ucs2_segment",  # per-segment size: reported, never failed
                 "code_points",  # Unicode code points: a Devanagari vowel sign or virama is one more (Telegram)
                 "double_width", "double_width_emoji"}  # CJK counts 2 (Google Ads); emoji 2 as well (Microsoft Ads)

# High-signal AI tells, applied to every draft (the full method is the humanizer skill: edit:ai_tell_removal).
AI_TELLS = [
    # sense-blind on purpose (high recall): "foster parents" or "seamless pipes" warn too; a warn kept for a domain
    # sense is reported in the deliver line
    ("AI vocabulary", r"(?i)\b(delv(e|es|ed|ing)|tapestr(y|ies)|testament to|underscor(e|es|ed|ing)|pivotal|"
                      r"showcas(e|es|ed|ing)|foster(s|ed|ing)?|intricate|intricac(y|ies)|interplay|garner(s|ed|ing)?|"
                      r"vibrant|seamless(ly)?|game[- ]chang(er|ers|ing)|unlock(s|ing)? (the|your|new|growth|potential)|"
                      r"elevate (your|the)|in today's (fast-paced|digital|ever-changing|ever-evolving)|fast-paced world)\b"),
    # negative parallelism: the second clause restates the subject ("it's Y", "but rather Y"), in one or two sentences
    ("not X but Y", r"(?i)\b(?:it|this|that)(?:'s\s+not|\s+is\s+not|\s+isn'?t)\s+(?:just |only |merely )?(?:about )?"
                    r"[^.!?\n]{1,40}(?:[,;—–-]\s*|[.!?]\s+)(?:it'?s|it is|this is|that'?s|but rather)\b"
                    r"|\bnot (?:just|only|merely) [^.!?\n]{1,40},? but (?:also|rather)\b"),
    ("filler phrase", r"(?i)\b(in order to|due to the fact that|at this point in time|it is important to note that|"
                      r"it'?s worth noting that|needless to say)\b"),
    ("fake-candid opener", r"(?im)^(honestly\?|here'?s the thing|let'?s be honest|real talk)"),
    ("generic send-off", r"(?i)\b(the future (looks|is) bright|exciting times (lie|are) ahead|journey towards? excellence)\b"),
    # the assistant's offer, not "Let me know if you need a GST copy"
    ("chatbot residue", r"(?i)\b(as an ai|i hope this helps|great question|let me know if you(?:'d| would) like "
                        r"(?:me to|any)|feel free to ask)\b|\bcertainly!"),
    ("stock email opener", r"(?i)\bhope (?:this|the|my) (?:e-?mail|message|mail|note|letter) finds you\b"),
]
CURLY = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"'}  # Word / Docs / chat typography must not hide a tell


# Unicode tables (generated from Unicode 16 property data; hex ranges): Emoji_Presentation, Extended_Pictographic,
# Indic consonants that join through a virama (InCB=Consonant), Prepend, and the spacing marks that are letters (Lo).
def _ranges(spec):
    return [tuple(int(x, 16) for x in (r + "-" + r if "-" not in r else r).split("-")) for r in spec.split()]


def _cls(spec):
    return "[" + "".join(re.escape(chr(a)) + ("-" + re.escape(chr(b)) if b > a else "") for a, b in _ranges(spec)) + "]"


_EP = ("231a-231b 23e9-23ec 23f0 23f3 25fd-25fe 2614-2615 2648-2653 267f 2693 26a1 26aa-26ab 26bd-26be 26c4-26c5 "
       "26ce 26d4 26ea 26f2-26f3 26f5 26fa 26fd 2705 270a-270b 2728 274c 274e 2753-2755 2757 2795-2797 27b0 27bf "
       "2b1b-2b1c 2b50 2b55 1f004 1f0cf 1f18e 1f191-1f19a 1f1e6-1f1ff 1f201 1f21a 1f22f 1f232-1f236 1f238-1f23a "
       "1f250-1f251 1f300-1f320 1f32d-1f335 1f337-1f37c 1f37e-1f393 1f3a0-1f3ca 1f3cf-1f3d3 1f3e0-1f3f0 1f3f4 "
       "1f3f8-1f43e 1f440 1f442-1f4fc 1f4ff-1f53d 1f54b-1f54e 1f550-1f567 1f57a 1f595-1f596 1f5a4 1f5fb-1f64f "
       "1f680-1f6c5 1f6cc 1f6d0-1f6d2 1f6d5-1f6d8 1f6dc-1f6df 1f6eb-1f6ec 1f6f4-1f6fc 1f7e0-1f7eb 1f7f0 1f90c-1f93a "
       "1f93c-1f945 1f947-1f9ff 1fa70-1fa7c 1fa80-1fa8a 1fa8e-1fac6 1fac8 1facd-1fadc 1fadf-1faea 1faef-1faf8")
_XP = ("a9 ae 203c 2049 2122 2139 2194-2199 21a9-21aa 231a-231b 2328 23cf 23e9-23f3 23f8-23fa 24c2 25aa-25ab 25b6 "
       "25c0 25fb-25fe 2600-2604 260e 2611 2614-2615 2618 261d 2620 2622-2623 2626 262a 262e-262f 2638-263a 2640 "
       "2642 2648-2653 265f-2660 2663 2665-2666 2668 267b 267e-267f 2692-2697 2699 269b-269c 26a0-26a1 26a7 "
       "26aa-26ab 26b0-26b1 26bd-26be 26c4-26c5 26c8 26ce-26cf 26d1 26d3-26d4 26e9-26ea 26f0-26f5 26f7-26fa 26fd "
       "2702 2705 2708-270d 270f 2712 2714 2716 271d 2721 2728 2733-2734 2744 2747 274c 274e 2753-2755 2757 "
       "2763-2764 2795-2797 27a1 27b0 27bf 2934-2935 2b05-2b07 2b1b-2b1c 2b50 2b55 3030 303d 3297 3299 1f004 "
       "1f02c-1f02f 1f094-1f09f 1f0af-1f0b0 1f0c0 1f0cf-1f0d0 1f0f6-1f0ff 1f170-1f171 1f17e-1f17f 1f18e 1f191-1f19a "
       "1f1ae-1f1e5 1f201-1f20f 1f21a 1f22f 1f232-1f23a 1f23c-1f23f 1f249-1f25f 1f266-1f321 1f324-1f393 1f396-1f397 "
       "1f399-1f39b 1f39e-1f3f0 1f3f3-1f3f5 1f3f7-1f3fa 1f400-1f4fd 1f4ff-1f53d 1f549-1f54e 1f550-1f567 1f56f-1f570 "
       "1f573-1f57a 1f587 1f58a-1f58d 1f590 1f595-1f596 1f5a4-1f5a5 1f5a8 1f5b1-1f5b2 1f5bc 1f5c2-1f5c4 1f5d1-1f5d3 "
       "1f5dc-1f5de 1f5e1 1f5e3 1f5e8 1f5ef 1f5f3 1f5fa-1f64f 1f680-1f6c5 1f6cb-1f6d2 1f6d5-1f6e5 1f6e9 1f6eb-1f6f0 "
       "1f6f3-1f6ff 1f7da-1f7ff 1f80c-1f80f 1f848-1f84f 1f85a-1f85f 1f888-1f88f 1f8ae-1f8af 1f8bc-1f8bf 1f8c2-1f8cf "
       "1f8d9-1f8ff 1f90c-1f93a 1f93c-1f945 1f947-1f9ff 1fa58-1fa5f 1fa6e-1faff 1fc00-1fffd")
_CONS = ("915-939 958-95f 978-97f 995-9a8 9aa-9b0 9b2 9b6-9b9 9dc-9dd 9df 9f0-9f1 a95-aa8 aaa-ab0 ab2-ab3 ab5-ab9 af9 "
         "b15-b28 b2a-b30 b32-b33 b35-b39 b5c-b5d b5f b71 c15-c28 c2a-c39 c58-c5a d15-d3a")
_PREPEND = "600-605 6dd 70f 890-891 8e2 d4e 110bd 110cd 111c2-111c3 113d1 1193f 11941 11a84-11a89 11d46 11f02"
_SPACING_LO = "e33 eb3 11b61 11b65 11b67"
_SKIN = "\U0001F3FB-\U0001F3FF"
# one emoji as the reader sees it: a flag (regional-indicator pair), a keycap, or an emoji-presentation character (or a
# pictograph made emoji by U+FE0F, or by a skin tone: ✌🏽 needs no U+FE0F) with its skin tone, tag sequence and
# ZWJ-joined parts. Text symbols (✓ ★ ➤ ©) are 0.
_EMOJI_ONE = rf"(?:{_cls(_EP)}|{_cls(_XP)}(?:\ufe0f|(?=[{_SKIN}])))[{_SKIN}]?\ufe0f?"
EMOJI_RE = re.compile(rf"[\U0001F1E6-\U0001F1FF]{{2}}|[0-9#*]\ufe0f?\u20e3|{_EMOJI_ONE}[\U000E0020-\U000E007F]*"
                      rf"(?:\u200d(?:{_cls(_EP)}|{_cls(_XP)})[{_SKIN}]?\ufe0f?)*")
HASHTAG_RE = re.compile(r"(?<!\w)#(?=\w*[^\W\d_])\w+")  # "#1" or "#4821" is a rank or an order number, not a tag


# ---------------------------------------------------------------- loading

def _load(path):
    """A JSON object from a file (a UTF-8 BOM is fine), or {"_error": ...} for a file that is unreadable, mid-write or
    not an object."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception as e:  # noqa: BLE001  (reported by validate; a file mid-write is skipped by the loaders)
        return {"_error": f"{path}: {e}"}
    return d if isinstance(d, dict) else {"_error": f"{path}: the top level must be a JSON object, not {type(d).__name__}"}


def _skip(d):
    """True for a file the loaders cannot use; said once on stderr so a broken file never just vanishes."""
    if "_error" in d:
        print(f"pcw: skipped {d['_error']} (python pcw.py validate)", file=sys.stderr)
    return "_error" in d


@lru_cache(None)
def harvest():
    """id -> merged item (first file wins the fields, sources and aliases are unioned)."""
    out = {}
    for f in sorted((HERE / "harvest").glob("*.json")):
        d = _load(f)
        if _skip(d):
            continue
        for it in d.get("items") or []:
            iid = it.get("id")
            if not iid:
                continue
            if iid in out:
                m = out[iid]
                m["sources"] = (m.get("sources") or []) + [s for s in it.get("sources") or []
                                                            if s.get("url") not in {x.get("url") for x in m.get("sources") or []}]
                m["aliases"] = sorted(set(m.get("aliases") or []) | set(it.get("aliases") or []))
                m["_files"].append(f.name)
            else:
                out[iid] = dict(it, kind=d.get("kind") or PREFIX_KIND.get(iid.split(":")[0]), _files=[f.name])
    return out


@lru_cache(None)
def cards():
    out = []
    for f in sorted((HERE / "cards").glob("*.json")):
        d = _load(f)
        if _skip(d):
            continue
        for c in d.get("cards") or []:
            out.append(dict(c, _file=f.name))
    return out


def card(cid, kind=None):
    """The card with this id (or exact name); with `kind`, only a card of that kind."""
    n = (cid or "").strip().lower()
    pool = [c for c in cards() if not kind or c.get("kind") == kind]
    hit = [c for c in pool if c.get("id", "").lower() == n] or [c for c in pool if c.get("name", "").lower() == n]
    return hit[0] if hit else None


def _missing(cid, kind):
    """"no genre card 'x'", plus what an id of another kind is and the id that was probably meant."""
    msg, other = f"no {kind} card {cid!r}", card(cid)
    if other:
        alt = f"{KINDS[kind]}:{other['id'].split(':', 1)[1]}"
        msg += f": {other['id']} is a {other['kind']} card" + (f"; did you mean {alt}?" if card(alt, kind) else "")
    return msg


def kind_of(word):
    """A kind name ("platform") or an id prefix with its colon ("plat:") -> the kind name, else None."""
    w = (word or "").strip().lower()
    return w if w in KINDS else PREFIX_KIND.get(w[:-1]) if w.endswith(":") else None


STOP = {"about", "for", "the", "an", "to", "my", "our", "your", "of", "on", "in", "with", "and", "me", "us", "write",
        "make", "create", "need", "want", "please", "some", "this", "that", "from", "by", "at", "is", "it", "a"}
# \w alone splits Devanagari (and every Indic script) at each vowel sign and virama: keep the combining marks
TOK_RE = re.compile(r"[\w\u0300-\u036f\u0900-\u0963\u0966-\u0dff]+")


def _toks(q):
    """Whole tokens of a request or a card field, stopwords out (single letters kept: the X in 'X post')."""
    return [w for w in TOK_RE.findall((q or "").lower()) if w not in STOP]


def _words(q):
    return [w for w in _toks(q) if len(w) > 1]


def _forms(w):
    """A word and its plain plural or singular ("headline" ~ "headlines"), for words of 4+ letters."""
    return ({w, w[:-1]} if w.endswith("s") else {w, w + "s"}) if len(w) >= 4 else {w}


@lru_cache(None)
def _card_terms(cid):
    """Per card: head tokens (name, id, aliases), haystack token counts, multi-word phrases, one-word aliases and
    one-word name parts, and the exact forms (full name, id slug, aliases)."""
    c, it = card(cid), harvest().get(cid) or {}
    name, al = c.get("name", ""), list(it.get("aliases") or [])
    head = " ".join([name, cid.replace("_", " ").replace(":", " "), " ".join(al)])
    hay = " ".join([head, c.get("summary", ""), " ".join(c.get("use_for") or []), it.get("category", "")])
    parts = re.split(r"\s*/\s*", re.sub(r"\(.*?\)", "", name))  # "A / B (x)" -> "A", "B"
    brk = [x for p in re.findall(r"\((.*?)\)", name) for x in re.split(r"\s*/\s*", p)]
    al += [x for x in brk if len(x.split()) > 1 or x.isupper()]  # "(SOP)" is an alias; "(Instagram)" a qualifier
    phrases = {" ".join(_toks(a)) for a in parts + al if len(_toks(a)) > 1}

    def one(xs):  # one RAW word ("tweet", "SOP"): "About page" minus a stopword is not the alias "page"
        return {_toks(a)[0] for a in xs if len(TOK_RE.findall(a.lower())) == 1 and len(_toks(a)) == 1
                and len(_toks(a)[0]) > 2}
    # an alias ("tweet", "magalog", "(SOP)") is a deliberate synonym; a slash part of the name ("Brand" of "Brand /
    # business naming", "FAQ" of "FAQ / answer article") is a fragment and weighs less in find()
    singles = (one(al), one(parts) - one(al))
    exact = {" ".join(_toks(x)) for x in [re.sub(r"\(.*?\)", "", name), cid.split(":", 1)[1].replace("_", " ")]
             + list(it.get("aliases") or [])}
    return set(_toks(head)), Counter(_toks(hay)), phrases, singles, exact - {""}


SHORTHAND = {"insta": "instagram", "fb": "facebook", "yt": "youtube"}  # platform nicknames in requests
ONE_WORD = 9  # score of a one-word harvested alias the request names (a one-word part of the card's name: 3)


def find(query, kind=None, limit=20):
    """Rank cards by query words in name / id / summary / use_for / aliases (name + id hits weigh most); a request
    that is a card's whole name, alias or id slug ranks that card first; verified passes and current items float up."""
    kind = kind_of(kind) or kind
    toks = [SHORTHAND.get(w, w) for w in _toks(query)]
    words, q, scored = [w for w in toks if len(w) > 1], f" {' '.join(toks)} ", []
    pool = [(c, _card_terms(c["id"])) for c in cards() if not kind or c.get("kind") == kind]
    forms = {}
    for w in words:  # a shorthand that is no card's whole token ("advert") matches the name/alias tokens it begins
        f = _forms(w)
        forms[w] = f if len(w) < 5 or any(f & t[1].keys() for _, t in pool) else \
            {k for _, t in pool for k in t[0] if k.startswith(w)}
    for c, (head, hay, phrases, (alias1, part1), exact) in pool:
        hits = [w for w in words if forms[w] & head]
        s = 3 * len(hits) + sum(min(sum(hay[f] for f in forms[w]), 3) for w in words)  # whole tokens, not substrings
        named = sum(f" {p} " in q for p in phrases)  # a whole alias or name inside the request ("reel script")
        # a one-word alias the request names ("tweet", "magalog") outweighs two generic words it would otherwise
        # lose to ("product launch tweet" is an X post, not a launch sequence)
        one = sum(f" {w} " in q for w in alias1) * ONE_WORD + sum(f" {w} " in q for w in part1) * 3
        s += 6 * named + one
        s += 20 * (q.strip() in exact)
        if s:
            v = (c.get("verified") or {}).get("verdict")
            s += (c.get("status") in ("current", "rising")) + 2 * (v == "pass") - 2 * (v == "wrong")
            scored.append((s, named + one, len(hits), c))  # one: named by a one-word alias or name part
    scored.sort(key=lambda x: (-x[0], -x[1], -x[2]))  # a tie goes to the card the request names, not to file order
    return [x[-1] for x in scored[:limit]]


def ids(kind=None, words=""):
    w = _words(words)
    if words.strip() and not w:  # a filter with no usable word matches nothing, not everything
        return []
    return [f"{i}  {it.get('name')}" for i, it in sorted(harvest().items())
            if (not kind or it.get("kind") == kind)
            and all(x in (i + " " + it.get("name", "") + " " + " ".join(it.get("aliases") or [])).lower() for x in w)]


# ---------------------------------------------------------------- validation

def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_harvest_file(path):
    d, issues = _load(path), []
    if "_error" in d:
        return [d["_error"]]
    kind = d.get("kind")
    if kind not in KINDS:
        return [f"{path.name}: kind {kind!r} not in {sorted(KINDS)}"]
    for k in ("worker", "as_of", "source", "items"):
        if not d.get(k):
            issues.append(f"{path.name}: missing top-level {k!r}")
    seen = Counter(it.get("id") for it in d.get("items") or [])
    for i, it in enumerate(d.get("items") or []):
        w = f"{path.name} #{i} {it.get('id')}"
        if seen[it.get("id")] > 1:
            issues.append(f"{w}: id repeated in this file")
        if not ID_RE.match(it.get("id") or "") or it["id"].split(":")[0] != KINDS[kind]:
            issues.append(f"{w}: id must be {KINDS[kind]}:<lower_snake>")
        miss = [k for k in ("name", "category", "one_line") if not it.get(k)]
        if miss:
            issues.append(f"{w}: missing {miss}")
        for s in it.get("sources") or []:
            if not str(s.get("url", "")).startswith("http"):
                issues.append(f"{w}: source without an http url: {s}")
        if kind == "genre" and it.get("value") not in VALUE:
            issues.append(f"{w}: genre value must be one of {sorted(VALUE)}")
        if kind == "platform":
            if not it.get("limits"):
                issues.append(f"{w}: platform item needs limits[] (sourced)")
            for lim in it.get("limits") or []:
                miss = [k for k in ("field", "unit", "url", "checked", "confidence") if lim.get(k) in (None, "")]
                if lim.get("max") is None and lim.get("min") is None:
                    miss.append("max (or min)")
                if miss:
                    issues.append(f"{w}: limit {lim.get('field')!r} missing {miss}")
                for k in ("max", "min"):
                    if lim.get(k) is not None and not _is_num(lim.get(k)):
                        issues.append(f"{w}: limit {lim.get('field')!r} {k} must be a number")
                if lim.get("unit") and lim["unit"] not in UNITS:
                    issues.append(f"{w}: limit unit {lim['unit']!r} not in {sorted(UNITS)}")
                if str(lim.get("confidence", "")).split(" ")[0] not in CONF:
                    issues.append(f"{w}: limit confidence must start with high / medium / low")
                issues += [f"{w}: limit {lim.get('field')!r}: {x}" for x in _limit_keys(lim)]
        if kind == "trend":
            ev = it.get("evidence") or []
            if not ev:
                issues.append(f"{w}: trend needs evidence[]")
            for e in ev:
                if not (e.get("claim") and str(e.get("url", "")).startswith("http") and e.get("date")):
                    issues.append(f"{w}: evidence needs claim, url, date: {e}")
            if ev and max(str(e.get("date", "")) for e in ev) < TREND_FLOOR:
                issues.append(f"{w}: newest evidence is older than {TREND_FLOOR}: not a 2026 trend")
        if kind in NEEDS_SOURCES and kind != "platform" and not it.get("sources") and not it.get("evidence"):
            issues.append(f"{w}: {kind} item needs sources[]")
    return issues


def _limit_keys(lim):
    """The optional limit keys: `lint` false (a row check must not measure: a URL weight, a button count) and `count`
    (how a chars limit is counted, COUNT_METHODS)."""
    out = []
    if "lint" in lim and not isinstance(lim["lint"], bool):
        out.append("lint must be true or false")
    if lim.get("count") is not None and (lim["count"] not in COUNT_METHODS or lim.get("unit") != "chars"):
        out.append(f"count {lim['count']!r} must be one of {sorted(COUNT_METHODS)}, on a chars limit")
    return out


LIMIT_KEY = ("field", "max", "min", "unit", "visible", "lint", "count")  # what a card copies from the harvest unchanged
SLOW_RX = re.compile(r"\^\\s[*+]")  # (?m)^\s*: \s eats newlines, so a run of blank lines makes the match cubic


def _batch_for(card_file):
    b = HERE / "work" / "batches" / card_file.name
    return _load(b) if b.exists() else None


def check_card(c, hv):
    w, issues = c.get("id") or c.get("name"), []
    kind = c.get("kind")
    miss = [f for f in COMMON + KIND_FIELDS.get(kind, ()) if c.get(f) in (None, "", [], {})]
    if kind not in KINDS:
        return [f"{w}: kind {kind!r} not in {sorted(KINDS)}"]
    if miss:
        issues.append(f"{w}: missing {miss}")
    it = hv.get(c.get("id"))
    if hv and not it:
        issues.append(f"{w}: id is not in the harvest (python pcw.py ids {kind} ...)")
    elif it and c.get("name") != it.get("name"):
        issues.append(f"{w}: name {c.get('name')!r} must be the harvested name {it.get('name')!r}")
    if c.get("status") and c["status"] not in STATUS:
        issues.append(f"{w}: status {c['status']!r} not in {sorted(STATUS)}")
    if c.get("confidence") and c["confidence"] not in CONF:
        issues.append(f"{w}: confidence {c['confidence']!r} not in {sorted(CONF)}")
    if kind in NEEDS_SOURCES and not c.get("sources") and not c.get("evidence"):
        issues.append(f"{w}: a {kind} card needs sources")
    for s in c.get("sources") or []:
        if not str(s.get("url", "")).startswith("http"):
            issues.append(f"{w}: source without an http url: {s}")
    for f in REF_FIELDS:
        v = c.get(f)
        if f == "compliance" and kind == "compliance":
            continue
        if v is not None and not isinstance(v, list):  # a bare string would be read character by character
            issues.append(f"{w}: {f} must be a list of ids, got {type(v).__name__} {v!r:.60}")
        refs = v if isinstance(v, list) else []
        bad = [r for r in refs if isinstance(r, str) and ID_RE.match(r) and hv and r not in hv]
        junk = [r for r in refs if not (isinstance(r, str) and ID_RE.match(r))]
        if f == "applies_to":
            continue
        if bad:
            issues.append(f"{w}: {f} names ids not in the harvest: {bad[:8]}")
        if junk:
            issues.append(f"{w}: {f} must hold PCW ids (prefix:slug), got {junk[:5]}")
        wrong = [r for r in refs if isinstance(r, str) and ID_RE.match(r) and f in REF_PREFIX
                 and r.split(":")[0] != REF_PREFIX[f]]
        if wrong:
            issues.append(f"{w}: {f} must hold {REF_PREFIX[f]}: ids, got {wrong[:5]}")
    if c.get("id") in (c.get("related") or []):
        issues.append(f"{w}: related lists itself")
    if kind == "genre":
        if c.get("value") and c["value"] not in VALUE:
            issues.append(f"{w}: value must be one of {sorted(VALUE)}")
        for p in c.get("structure") or []:
            if not (isinstance(p, dict) and p.get("part") and p.get("does")):
                issues.append(f"{w}: structure entries need part + does")
                break
        lint = c.get("lint") or {}
        unknown = set(lint) - LINT_KEYS
        if unknown:
            issues.append(f"{w}: lint has unknown keys {sorted(unknown)} (allowed {sorted(LINT_KEYS)})")
        for k in ("require", "ban"):
            for r in lint.get(k) or []:
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error")  # e.g. "possible nested set": meaning may change later
                        rx = re.compile(r.get("regex", ""))
                    if not r.get("label") or not r.get("regex"):
                        raise ValueError("needs label + regex")
                    if rx.flags & re.M and SLOW_RX.search(r["regex"]):
                        raise ValueError(r"(?m)^\s* also eats newlines (cubic time on blank lines): use ^[^\S\n]*")
                except Exception as e:  # noqa: BLE001
                    issues.append(f"{w}: lint.{k} entry {r}: {e}")
        if lint.get("min_words") and lint.get("max_words") and lint["min_words"] > lint["max_words"]:
            issues.append(f"{w}: lint min_words > max_words")
    if kind == "platform":
        issues += [f"{w}: limit {l.get('field')!r}: {x}" for l in c.get("limits") or [] for x in _limit_keys(l)]
    if kind == "platform" and it:
        hl = {tuple(l.get(k) for k in LIMIT_KEY) for l in it.get("limits") or []}
        cl = {tuple(l.get(k) for k in LIMIT_KEY) for l in c.get("limits") or []}
        if hl and cl != hl:
            issues.append(f"{w}: limits must be the harvested limits unchanged ({', '.join(LIMIT_KEY)}): "
                          f"harvest {sorted(hl - cl, key=str)} card {sorted(cl - hl, key=str)}")
    if kind == "hook" and len(c.get("examples") or []) < 3:
        issues.append(f"{w}: hook needs >= 3 examples")
    if kind == "framework":
        for s in c.get("steps") or []:
            if not (isinstance(s, dict) and s.get("step") and s.get("does")):
                issues.append(f"{w}: steps entries need step + does")
                break
        if len((c.get("mini_example") or "").split()) > 120:
            issues.append(f"{w}: mini_example over 120 words")
    if kind == "trend" and c.get("evidence") and max(str(e.get("date", "")) for e in c["evidence"]) < TREND_FLOOR:
        issues.append(f"{w}: newest evidence older than {TREND_FLOOR}")
    v = c.get("verified")
    if v:
        if v.get("verdict") not in VERDICT:
            issues.append(f"{w}: verified.verdict {v.get('verdict')!r} not in {sorted(VERDICT)}")
        if v.get("verdict") in ("pass", "weak", "wrong") and not _is_num(v.get("score")):
            issues.append(f"{w}: verified.score must be a number 0-10")
    return issues


def check_card_file(path):
    d = _load(path)
    if "_error" in d:
        return [d["_error"]]
    hv, cs = harvest(), d.get("cards") or []
    issues = [f"{path.name}: {x}" for c in cs for x in check_card(c, hv)]
    b = _batch_for(path)
    if b:
        want = {it["id"] for it in b.get("items") or []}
        got = Counter(c.get("id") for c in cs)
        issues += [f"{path.name}: missing card for {i}" for i in sorted(want - set(got))]
        issues += [f"{path.name}: {i} is not in this batch" for i in sorted(set(got) - want)]
        issues += [f"{path.name}: {n} cards for {i}" for i, n in got.items() if n > 1]
    return issues


def gaps():
    """work/gaps.jsonl -> (rows, bad): rows are the gap objects; bad is [(line number, error)] for lines a hand edit or
    a UTF-16 shell append (Windows PowerShell 5.1 `>>`) broke. A blank line and a stray BOM are fine."""
    f = HERE / "work" / "gaps.jsonl"
    if not f.exists():
        return [], []
    rows, bad = [], []
    for n, line in enumerate(f.read_bytes().decode("utf-8", "replace").split("\n"), 1):
        s = line.replace("\x00", "").strip().lstrip("\ufeff")
        if not s:
            continue
        try:
            if "\x00" in line or "\ufffd" in line:
                raise ValueError("not UTF-8 text (an append in UTF-16?)")
            g = json.loads(s)
            if not isinstance(g, dict):
                raise ValueError(f"a gap line must be a JSON object, not {type(g).__name__}")
            rows.append(g)
        except ValueError as e:
            bad.append((n, str(e)[:80]))
    return rows, bad


def _gallery_issues(p):
    d, known = _load(p), {c.get("id") for c in cards()}
    if "_error" in d:
        return [d["_error"]]
    ss = d.get("samples") or []
    issues = [f"{p.name}: sample {s.get('id')!r} missing {[k for k in ('id', 'brief', 'text', 'check', 'writer') if not s.get(k)]}"
              for s in ss if not all(s.get(k) for k in ("id", "brief", "text", "check", "writer"))]
    issues += [f"{p.name}: {s.get('id')} is not a card" for s in ss if s.get("id") not in known]
    issues += [f"{p.name}: {i} has {n} samples" for i, n in Counter(s.get("id") for s in ss).items() if n > 1]
    # a card with no sample yet is not an issue: the samples wave writes gallery files as it goes, and the samples
    # row of `pipeline.py status` reports the shortfall as attention
    return issues


def validate(paths=None):
    harvest.cache_clear(); cards.cache_clear(); _card_terms.cache_clear()
    harvest_only = paths and all(Path(p).parent.name == "harvest" for p in paths)
    if not any((HERE / "harvest").glob("*.json")) and not harvest_only:
        return [f"no harvest/*.json under {HERE} (is PCW_HOME right?): nothing to check cards against"]
    glob = []
    if not paths:
        paths = [f for d in ("harvest", "cards", "gallery") for f in sorted((HERE / d).glob("*.json"))]
        dup = Counter(c.get("id") for c in cards())
        glob = [f"duplicate card id across files: {i} ({n}x)" for i, n in dup.items() if n > 1]
        by = {c.get("id"): c for c in cards()}  # CONTRACT: genre:x and plat:x twins name each other
        glob += [f"{g} / plat:{g[6:]}: twin cards must name each other (genre platforms / platform related)"
                 for g in by if str(g).startswith("genre:") and f"plat:{g[6:]}" in by
                 and (f"plat:{g[6:]}" not in (by[g].get("platforms") or [])
                      or g not in (by[f"plat:{g[6:]}"].get("related") or []))]
        seen = {}
        for f in sorted((HERE / "work" / "batches").glob("*.json")):
            d = _load(f)
            glob += [f"work/batches/{d['_error']}"] if "_error" in d else []
            for it in d.get("items") or []:
                seen.setdefault(it.get("id"), []).append(f.name)
        glob += [f"{i} is in {len(fs)} batch files: {fs}" for i, fs in seen.items() if len(fs) > 1]
        glob += [f"work/gaps.jsonl line {n}: {e}" for n, e in gaps()[1]]
    issues = []
    for p in map(Path, paths):
        p = p if p.is_absolute() else (Path.cwd() / p if (Path.cwd() / p).exists() else HERE / p)
        if p.parent.name == "harvest":
            issues += check_harvest_file(p)
        elif p.parent.name == "cards":
            if p.name.startswith("zz_"):
                continue
            issues += check_card_file(p)
        elif p.parent.name == "gallery":
            issues += _gallery_issues(p)
        elif p.name == "gaps.jsonl":
            issues += [f"work/gaps.jsonl line {n}: {e}" for n, e in gaps()[1]]
        else:
            issues.append(f"{p}: not under harvest/ or cards/")
    return issues + glob


def dupes():
    """Pairs of harvest items whose normalised names / aliases collide (same kind)."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", re.sub(r"\(.*?\)", "", s.lower())).strip()
    seen, out = {}, []
    for iid, it in harvest().items():
        for n in [it.get("name", ""), iid.split(":")[1].replace("_", " ")] + list(it.get("aliases") or []):
            k = (it.get("kind"), norm(n))
            if k[1] and k in seen and seen[k] != iid:
                out.append(f"{seen[k]}  ~  {iid}   ({n!r}; {'/'.join(harvest()[seen[k]]['_files'])} vs {'/'.join(it['_files'])})")
            seen.setdefault(k, iid)
    return sorted(set(out))


def batches(kinds=None, size=30, sizes={"genre": 20}):
    """Merged harvest -> work/batches/<kind>_<nn>.json (genre cards are the richest, so smaller batches). Safe to
    re-run: items already in a batch file are skipped and new batches are numbered after the existing ones."""
    out = HERE / "work" / "batches"
    out.mkdir(parents=True, exist_ok=True)
    batched, last = set(), Counter()
    for f in out.glob("*.json"):
        d = _load(f)
        if "_error" in d:  # mid-write by a parallel agent, or broken: re-batching now would duplicate its items
            raise ValueError(f"{d['_error']}: fix or delete it before re-batching (nothing written)")
        batched |= {it["id"] for it in d.get("items") or []}
        k, _, n = f.stem.rpartition("_")
        last[k] = max(last[k], int(n) if n.isdigit() else 0)
    by_kind = {}
    for iid, it in sorted(harvest().items()):
        if (not kinds or it["kind"] in kinds) and iid not in batched:
            by_kind.setdefault(it["kind"], []).append({k: v for k, v in it.items() if k != "_files"})
    made = []
    for kind, items in by_kind.items():
        nb = -(-len(items) // sizes.get(kind, size))  # batch count, then even chunks (no 1-item stragglers)
        step = -(-len(items) // nb)
        for n, i in enumerate(range(0, len(items), step), last[kind] + 1):
            f = out / f"{kind}_{n:02d}.json"
            f.write_text(json.dumps({"kind": kind, "items": items[i:i + step]}, indent=1, ensure_ascii=False),
                         encoding="utf-8")
            made.append(f"{f.name} ({len(items[i:i + step])})")
    return made


# ---------------------------------------------------------------- writing: brief + check

def _short(c, keys):
    return {k: c[k] for k in keys if c.get(k)}


def brief(request="", genre=None, platform=None, lang=None, tone=None):
    """Everything a writer needs for one job, as Markdown: the genre card's structure, length, checklist and lint, its
    frameworks / techniques / hooks (compact), the platform limits, tone + language rules, legal checks, live trends;
    platforms and laws that name the genre from their own cards (not listed on the genre card) as one-line pointers.
    An id passed explicitly that is unknown or of another kind raises LookupError naming the flag; a request that
    matches no genre returns a "No genre card matches" line."""
    bad = [f"--{flag} {v}: " + _missing(v, kind) for flag, kind, v in
           (("genre", "genre", genre), ("platform", "platform", platform), ("lang", "language", lang),
            ("tone", "tone", tone)) if v and not card(v, kind)]
    if bad:
        raise LookupError("\n".join(bad) + '\nFind ids with: python pcw.py find "<words>" <kind>')
    g = card(genre, "genre") if genre else next(iter(find(request, "genre", 1)), None)
    if not g:
        return f"No genre card matches {request!r}. Try: python pcw.py find \"{request}\""
    L = [f"# Brief: {g['name']} ({g['id']})", "", g.get("summary", ""), ""]
    v = g.get("verified") or {}
    if v:  # verdict only: the judge's note is test history, not guidance (and would leak into re-tests)
        L += [f"Card tested: {v.get('verdict')} ({v.get('score')}/10)", ""]
    L += [f"**Goal:** {g.get('goal', '')}", f"**Buyers:** {', '.join(g.get('buyers') or [])}",
          f"**Length:** {json.dumps(g.get('length'), ensure_ascii=False)}", "", "## Structure"]
    L += [f"{i}. **{p['part']}**: {p['does']}" + (f" ({p['length']})" if p.get("length") else "")
          for i, p in enumerate(g.get("structure") or [], 1)]
    L += ["", "## Checklist (every item must be yes)"] + [f"- [ ] {x}" for x in g.get("checklist") or []]
    L += ["", "## Pitfalls"] + [f"- {x}" for x in g.get("pitfalls") or []]
    L += ["", "## Avoid"] + [f"- {x}" for x in g.get("avoid") or []]

    def section(title, ids_, keys, cap=4):
        got = [card(i) for i in (ids_ or [])[:cap]]
        got = [c for c in got if c]
        if not got:
            return []
        out = ["", f"## {title}"]
        for c in got:
            out.append(f"### {c['name']} ({c['id']})")
            for k, val in _short(c, keys).items():
                if isinstance(val, list):
                    val = "; ".join(x if isinstance(x, str) else " / ".join(str(y) for y in x.values()) for x in val)
                out.append(f"- {k}: {val}")
        return out

    L += section("Frameworks", g.get("frameworks"), ("summary", "steps", "best_for"), 3)
    L += section("Techniques", g.get("techniques"), ("how",), 6)
    L += section("Hooks", g.get("hooks"), ("templates", "risk"), 4)
    plats = [platform] if platform else (g.get("platforms") or [])[:2]
    for pid in plats:
        p = card(pid, "platform")
        if p:
            L += ["", f"## Platform: {p['name']} ({p['id']})"]
            L += [f"- {l['field']}: " + ", ".join(f"{k} {l[k]}" for k in ("min", "max") if l.get(k) is not None)
                  + f" {l['unit']}" + (f", visible {l['visible']}" if l.get("visible") else "")
                  + (f", counted {l['count']}" if l.get("count") else "") + (", by hand" if l.get("lint") is False else "")
                  + f"  [{l.get('confidence', '').split(' ')[0]}, checked {l.get('checked')}]" for l in p.get("limits") or []]
            L += [f"- check: {check_plan(p)}"]
            L += [f"- formatting: {p.get('formatting')}"] + [f"- {x}" for x in p.get("writing_notes") or []]
    # every platform linked either way (the genre lists it, or the platform card names the genre), not printed above
    linked = (g.get("platforms") or []) + [c["id"] for c in cards() if c.get("kind") == "platform"
                                           and g["id"] in (c.get("related") or [])]
    more = [c for c in (card(i, "platform") for i in dict.fromkeys(linked) if i not in plats) if c]
    if more:
        L += ["", "Also relevant platforms (`python pcw.py card <id>` for their limits): "
              + ", ".join(f"{c['name']} ({c['id']})" for c in more)]
    for tid in [tone] if tone else (g.get("tones") or [])[:1]:
        t = card(tid, "tone")
        if t:
            L += ["", f"## Tone: {t['name']}", f"- markers: {'; '.join(t.get('markers') or [])}",
                  f"- avoid: {'; '.join(t.get('avoid') or [])}"]
    if lang:
        lc = card(lang, "language")
        if lc:
            L += ["", f"## Language: {lc['name']}"] + [f"- {x}" for x in lc.get("rules") or []]
            L += [f"- mistake: {x}" for x in lc.get("mistakes") or []]
    for cid in g.get("compliance") or []:
        c = card(cid, "compliance")
        if c:
            L += ["", f"## Legal: {c['name']} ({c.get('jurisdiction', '')}, as of {c.get('as_of', '')})"]
            L += [f"- [ ] {x}" for x in c.get("checks") or []]
    # laws whose own card names this genre (applies_to) but which the genre card does not list: one line each, India
    # first (a generic genre can have 30+ of them, so pointers, not full checklists)
    also = sorted((c for c in cards() if c.get("kind") == "compliance" and g["id"] in (c.get("applies_to") or [])
                   and c["id"] not in (g.get("compliance") or [])),
                  key=lambda c: ("India" not in (c.get("jurisdiction") or ""), c.get("name", "")))
    if also:
        L += ["", "## Legal: also check (these laws name this genre; `python pcw.py card <id>` for the checklist)"]
        L += [f"- {c['name']} ({c['id']}; {c.get('jurisdiction', '')}, as of {c.get('as_of', '')})" for c in also]
    rel = {g["id"]} | set(plats)
    tr = [c for c in cards() if c.get("kind") == "trend" and rel & set(c.get("related") or [])]
    if tr:
        L += ["", "## Live trends that touch this job"]
        L += [f"- {c['name']} (as of {c.get('as_of')}): do {'; '.join(c.get('do') or [])}" for c in tr[:4]]
    if g.get("lint"):
        L += ["", "## Lint (python pcw.py check draft.txt --genre " + g["id"] + ")",
              "```json", json.dumps(g["lint"], ensure_ascii=False), "```"]
    L += ["", "Last pass: humanizer skill (edit:ai_tell_removal), then `pcw.py check`."]
    return "\n".join(L)


def _in(o, table):
    i = bisect.bisect_right(table, (o, 0x10FFFF)) - 1
    return i >= 0 and table[i][0] <= o <= table[i][1]


_XP_T, _CONS_T, _PRE_T, _SPACING_T = (_ranges(x) for x in (_XP, _CONS, _PREPEND, _SPACING_LO))
_LINKER_VIRAMAS = "\u094d\u09cd\u0acd\u0b4d\u0c4d\u0d4d"  # Devanagari, Bengali, Gujarati, Oriya, Telugu, Malayalam
_HANGUL_JOIN = {("L", "L"), ("L", "V"), ("L", "LV"), ("L", "LVT"), ("LV", "V"), ("LV", "T"), ("V", "V"), ("V", "T"),
                ("LVT", "T"), ("T", "T")}


def _hangul(o):
    if 0x1100 <= o <= 0x115F or 0xA960 <= o <= 0xA97C:
        return "L"
    if 0x1160 <= o <= 0x11A7 or 0xD7B0 <= o <= 0xD7C6:
        return "V"
    if 0x11A8 <= o <= 0x11FF or 0xD7CB <= o <= 0xD7FB:
        return "T"
    if 0xAC00 <= o <= 0xD7A3:
        return "LV" if (o - 0xAC00) % 28 == 0 else "LVT"
    return None


def _clusters_stdlib(text):
    """Extended grapheme clusters without the `regex` module. Follows UAX #29 for CRLF and controls, Hangul, marks and
    spacing marks, Prepend, Indic consonant + virama + consonant (GB9c), emoji ZWJ sequences, skin tones, tag flags
    and regional-indicator pairs; tests/test_graphemes.py pins it against `regex`."""
    out, prev, pctrl, ri, pict, cons, link = [], None, False, 0, False, False, False
    for ch in text:
        o, cat = ord(ch), unicodedata.category(ch)
        ext = cat.startswith("M") or ch in "\u200c\u200d" or 0xFE00 <= o <= 0xFE0F or 0x1F3FB <= o <= 0x1F3FF \
            or 0xE0020 <= o <= 0xE007F
        ctrl = cat in ("Cc", "Zl", "Zp") or (cat == "Cf" and not ext and not _in(o, _PRE_T))
        if prev is None:
            join = False
        elif prev == "\r" and ch == "\n":
            join = True
        elif pctrl or ctrl:
            join = False
        elif (_hangul(ord(prev)), _hangul(o)) in _HANGUL_JOIN:
            join = True
        elif ext or _in(o, _SPACING_T) or _in(ord(prev), _PRE_T):
            join = True
        elif link and _in(o, _CONS_T):  # GB9c: क + ् + ष
            join = True
        elif prev == "\u200d" and pict and _in(o, _XP_T):  # GB11: pictograph ZWJ pictograph
            join = True
        else:
            join = 0x1F1E6 <= o <= 0x1F1FF and ri % 2 == 1  # flags: regional indicators in pairs
        if join:
            out[-1] += ch
        else:
            out.append(ch)
        ri = ri + 1 if 0x1F1E6 <= o <= 0x1F1FF else 0
        pict = _in(o, _XP_T) or (pict and ext)
        if _in(o, _CONS_T):
            cons, link = True, False
        elif ch in _LINKER_VIRAMAS:
            link = cons
        elif ch == "\u200c" or not ext:  # ZWNJ is not InCB=Extend, so it ends a GB9c conjunct (क्‌ष is 2)
            cons = link = False
        prev, pctrl = ch, ctrl
    return out


def _clusters(text):
    """Visible characters (extended grapheme clusters): the `regex` module's \\X when installed, else the stdlib
    segmenter above, which agrees with it on Latin, Indic conjuncts, emoji sequences, Hangul and CRLF."""
    try:
        import regex
    except ImportError:
        return _clusters_stdlib(text)
    return regex.findall(r"\X", text)


def _graphemes(text):
    return len(_clusters(text))


def _graphemes_stdlib(text):
    return len(_clusters_stdlib(text))


# GSM 03.38: the 7-bit default alphabet, and the extension table whose characters cost two septets
_GSM7 = ("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
         "abcdefghijklmnopqrstuvwxyzäöñüà")
_GSM7_EXT = "\f^{}\\[~]|€"
SMS_ONE = {"GSM-7": (160, 153), "UCS-2": (70, 67)}  # one SMS, and each segment of a long SMS (3GPP TS 23.038/23.040)


def sms_units(text):
    """(encoding, units, segments, first non-GSM character): GSM-7 counts septets (^ { } [ ] ~ | \\ € cost 2); any
    other character (₹, a curly quote, an emoji, Devanagari) makes the whole message UCS-2, counted in UTF-16 units."""
    odd = next((ch for ch in text if ch not in _GSM7 and ch not in _GSM7_EXT), None)
    enc = "GSM-7" if odd is None else "UCS-2"
    n = sum(1 + (ch in _GSM7_EXT) for ch in text) if odd is None else len(text.encode("utf-16-le")) // 2
    one, seg = SMS_ONE[enc]
    return enc, n, 1 if n <= one else -(-n // seg), odd


_X_LIGHT = ((0, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))  # twitter-text v3 weight-1 ranges
URL_RE = re.compile(r"(?i)https?://\S*[^\s.,;:!?)\]'\"]")
# X also links a domain typed without http(s):// (twitter-text): a listed generic TLD, or a two-letter country TLD
# with a path, a subdomain (www.) or as t.co. ponytail: compact TLD list, so an unlisted one (.world) is under-counted
_X_GTLD = ("com|net|org|info|biz|edu|gov|mil|int|name|pro|app|dev|xyz|online|site|store|shop|tech|blog|news|live|"
           "club|top|cloud|link|space|website")
_X_BARE = re.compile(r"(?i)(?<![\w@$#.\-/])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+)(?:(" + _X_GTLD + r")|[a-z]{2})"
                     r"(?![\w-])(/(?:\S*[^\s.,;:!?)\]'\"])?)?")


def _x_linked(m):
    """True for a bare domain X turns into a link ("amazon.in" alone is not one; "amazon.in/deals" is)."""
    return bool(m.group(2) or m.group(3) or m.group(1).count(".") > 1 or m.group(0).lower() == "t.co")


def x_weighted(text):
    """X's own count (twitter-text config v3): after NFC a URL counts 23 and an emoji 2; code points in Latin,
    Devanagari and the other blocks below U+1100 (and some punctuation) count 1, everything else (CJK) 2. A link may
    come without a scheme (zomato.com, amazon.in/deals, www.example.in) and in any letter case (HTTPS://)."""
    t = unicodedata.normalize("NFC", text)
    n = 23 * len(URL_RE.findall(t))
    t = URL_RE.sub("", t)
    n += 23 * sum(map(_x_linked, _X_BARE.finditer(t)))
    t = _X_BARE.sub(lambda m: "" if _x_linked(m) else m.group(0), t)
    n += 2 * len(EMOJI_RE.findall(t))
    return n + sum(1 if any(a <= ord(ch) <= b for a, b in _X_LIGHT) else 2 for ch in EMOJI_RE.sub("", t))


def width_count(text, emoji=False):
    """Google Ads and Microsoft Advertising: a double-width (East Asian wide or fullwidth: CJK) character counts 2, and
    with emoji=True (Microsoft) an emoji does too; anything else 1 per visible character."""
    n = 0
    for cl in _clusters(text):
        e = EMOJI_RE.fullmatch(cl) is not None
        n += 2 if (e and emoji) or (not e and unicodedata.east_asian_width(cl[0]) in "WF") else 1
    return n


def _syllables(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


# full stops that do not end a sentence: a capitalised title before any word ("Dr. Mehta", "Acme Pvt. Ltd.", not
# "300 ms. Users"), a company word or a.m. / p.m. before a lowercase word or number ("Acme Ltd. has", "10 a.m. to 6";
# "Acme Ltd. Our plant" and "at 10 a.m. Entry" end there), an abbreviation before a number ("Rs. 499", "No. 14"),
# initials ("M.G. Road", "the U.S. market"), e.g. / i.e. / vs. before any word, etc. before a lowercase word ("etc. the")
_ABBR = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Prof|Shri|Smt|Sri|Pvt|Dept|St|Jr|Sr|Er|Adv|Capt|Col|Lt|Hon)\.(?=\s)"
                   r"|\b(?:Ltd|Govt|Co|Inc|Corp)\.(?=\s+[a-z\d])"
                   r"|\b(?i:Rs|No|Nos|Fig|Vol|pp|Art|Sec|Ch|approx)\.(?=\s+\d)|\b(?i:a\.m|p\.m)\.(?=\s+[a-z\d])"
                   r"|(?<![\w.])(?:[A-Z]\.){2,}(?=\s+\w)|\b(?i:e\.g|i\.e|vs|viz|cf)\.(?=\s+\w)"
                   r"|\b(?i:etc|incl|esp)\.(?=\s+[a-z\d])")


def _mask_urls(text):
    """Each URL cut to its scheme and host ("https://studio.in/", "studio.in/" for a link typed without a scheme): an
    anchor (#pricing), a query (?ref=) or an @handle in a path is not copy, so it is no hashtag, mention or question."""
    text = URL_RE.sub(lambda m: re.match(r"(?i)https?://[^/?#\s]*/?", m.group(0)).group(0), text)
    return _X_BARE.sub(lambda m: m.group(0)[:m.start(3) - m.start(0)] + "/" if m.group(3) else m.group(0), text)


def stats_text(text):
    words = [w for w in text.split() if re.search(r"\w", w)]  # table pipes, bullets and dashes are not words
    # . ! ? and the danda end a sentence before any word, lowercase too ("link in bio. grab yours"), except after the
    # abbreviations above; line breaks and table cells end a unit
    sents = [s for s in re.split(r"(?<=[!?।…])\s+|(?<=\.)\s+|(?<=[.!?।…][\"'”’)\]])\s+|\n+|\|",
                                 _ABBR.sub(lambda m: m.group(0)[:-1], text))
             if re.search(r"\w", s)]
    sw = [len(s.split()) for s in sents] or [0]
    latin = sum(ch.isascii() and ch.isalpha() for ch in text)
    alpha = sum(ch.isalpha() for ch in text) or 1
    grade = None
    if latin / alpha > 0.9 and words and sents:
        syl = sum(_syllables(w) for w in words)
        grade = round(0.39 * len(words) / len(sents) + 11.8 * syl / len(words) - 15.59, 1)
    return {"words": len(words), "chars": len(text), "sentences": len(sents), "max_sentence_words": max(sw),
            "avg_sentence_words": round(sum(sw) / len(sents), 1) if sents else 0, "fk_grade": grade,
            "exclamations": len(re.findall(r"!(?![\[=])", text)),  # not Markdown images "![" or "!="
            "emoji": len(EMOJI_RE.findall(text)),  # one per emoji as seen: a flag, a family or a skin tone is 1
            "hashtags": len(HASHTAG_RE.findall(_mask_urls(text))),  # "studio.in/#pricing" is a link, not a tag
            # an en dash between numbers ("10–12", "10 – 12") is a range, not a tell; a number on one side only
            # ("Founded 2019 – and", "Call us – 98765") still counts
            "dashes": len(re.findall(r"—|(?<!\d)(?<!\d )–|–(?! ?\d)| -- ", text)),
            "devanagari": any("\u0900" <= ch <= "\u097f" for ch in text)}


COUNTS = ("hashtag", "emoji", "mention", "link", "url", "punctuation")  # what a "count" limit's field can name


def _count_key(l):
    return next((k for k in COUNTS if k in l.get("field", "").lower()), None)


def _base(field):
    """'post text (UTF-8 bytes)' -> 'post text': rows that share a base name measure the same text."""
    return re.split(r"\s*[(,]", field or "")[0].strip().lower()


def lint_rows(p):
    """The limits of platform card p that check can measure on a draft: text units, and counts whose field names what
    to count (hashtags, @mentions, links, emoji). A row marked "lint": false (a URL weight, a button count) never."""
    return [l for l in (p or {}).get("limits") or [] if l.get("lint") is not False
            and (l.get("unit") in TEXT_UNITS or (l.get("unit") == "count" and _count_key(l) is not None))]


def _several(rows):
    return len({_base(l["field"]) for l in rows if l.get("unit") != "count"}) > 1


def check_plan(p):
    """One line for the brief: what `check --platform` enforces on this platform card."""
    rows, cmd = lint_rows(p), f"`pcw.py check draft.txt --platform {p['id']}`"
    if not rows:
        return f"{cmd} has no limit it can measure here; check the limits above by hand"
    if _several(rows):
        return (f"{cmd} enforces nothing on its own: save each part in its own file and add --field \"<name>\", one "
                f"of {[l['field'] for l in rows]}")
    return f"{cmd} enforces {[l['field'] for l in rows]}"


def check_text(text, genre=None, platform=None, field=None):
    """-> (fails, warns, info). Fails: genre lint and platform limits. Warns: AI tells, dashes, readability drift."""
    text = text.replace("\r\n", "\n").lstrip("\ufeff").strip()  # a BOM or the file's trailing newline is not copy
    # patterns see straight quotes and each URL cut to its host (a "?ref=" query is no question, "#pricing" no tag);
    # counts (and SMS encoding) see the text as typed
    tx = _mask_urls(text.translate(CURLY))
    st, fails, warns, info = stats_text(text), [], [], []
    info.append(json.dumps(st, ensure_ascii=False))
    if not text:
        fails.append("draft is empty")
    for label, rx in AI_TELLS:
        hits = sorted({m.group(0) for m in re.finditer(rx, tx)})
        if hits:
            warns.append(f"AI tell ({label}): {hits[:5]}")
    if st["dashes"]:
        warns.append(f"{st['dashes']} em/en dashes (AI tell unless the brand voice uses them)")
    g = card(genre, "genre") if genre else None
    if genre and not g:
        fails.append(_missing(genre, "genre"))
    lint = (g or {}).get("lint") or {}
    for k, stat, op in (("min_words", "words", "<"), ("max_words", "words", ">"),
                        ("max_sentence_words", "max_sentence_words", ">"),
                        ("max_avg_sentence_words", "avg_sentence_words", ">"),
                        ("max_exclamations", "exclamations", ">"), ("max_emoji", "emoji", ">"),
                        ("max_hashtags", "hashtags", ">")):
        if k in lint and (st[stat] < lint[k] if op == "<" else st[stat] > lint[k]):
            fails.append(f"{k} {lint[k]}: draft has {st[stat]}")
    if "grade_max" in lint and st["fk_grade"] is not None and st["fk_grade"] > lint["grade_max"]:
        fails.append(f"grade_max {lint['grade_max']}: draft reads at grade {st['fk_grade']}")
    for r in lint.get("require") or []:
        if not re.search(r["regex"], tx):
            fails.append(f"missing: {r['label']}")
    for r in lint.get("ban") or []:
        m = re.search(r["regex"], tx)
        if m:
            fails.append(f"banned ({r['label']}): {m.group(0)!r}")
    p = card(platform, "platform") if platform else None
    if platform and not p:
        fails.append(_missing(platform, "platform"))
    links = len(re.findall(r"(?i)https?://\S+", text))
    counts = {"hashtag": st["hashtags"], "emoji": st["emoji"],
              "mention": len(re.findall(r"(?<!\w)@\w+", _mask_urls(text))),  # not medium.com/@handle
              "link": links, "url": links, "punctuation": len(re.findall(r"[!?.,;:]", text))}
    rows = lint_rows(p)
    if field:  # a field NAMED by --field (its base before any "(...)" / ", ..." qualifier, or that base's first words:
        # "subject line" -> "subject line words") wins over a substring ("description" is not "in-app purchase
        # description"); the count rows of the same text come along: they mention --field or share a word with the
        # field's base ("emojis per subject", "links per post", "@ mentions per caption")
        fl = field.strip().lower()
        lims = [l for l in rows if l["unit"] != "count" and (fl == l["field"].lower() or fl == _base(l["field"])
                                                             or _base(l["field"]).startswith(fl + " "))]
        if lims:
            words = {w for l in lims for w in _toks(_base(l["field"]))} - {"per", "text"}
            lims += [l for l in rows if l["unit"] == "count" and (fl in l["field"].lower()
                                                                   or words & set(_toks(l["field"])))]
        else:
            lims = [l for l in rows if fl in l["field"].lower()]
        # alternative surfaces: several text rows of one unit, none named exactly (LinkedIn's "introductory text" for
        # single image and carousel, Meta's headline per placement, Telegram's bio with and without Premium). A draft
        # is written for one of them, so ask which instead of failing it against all
        alt = [l for l in lims if l["unit"] != "count" and not (l.get("count") or "").startswith("sms")]
        if len({l["unit"] for l in alt}) < len(alt) and fl not in {l["field"].lower() for l in alt}:
            fails.append(f"{p['id']}: --field {field!r} fits several alternative fields; name one: "
                         f"{[l['field'] for l in alt]}")
            lims = []
        elif p and not lims:
            fails.append(f"{p['id']} has no lintable limit matching --field {field!r}: {[l['field'] for l in rows]}")
        elif len({_base(l["field"]) for l in lims}) > 1:
            info.append(f"--field {field!r} matches several fields; all are enforced: {[l['field'] for l in lims]}")
    elif _several(rows):  # several texts (headline / description, title / body): the writer must name one
        lims = []
        warns.append(f"{p['id']} has {len(rows)} fields and nothing was measured: pass --field <one of> "
                     f"{[l['field'] for l in rows]}")
    else:
        lims = rows
        if p and not rows:
            info.append(f"{p['id']} has no limit check can measure; check its limits by hand from the brief")
    clusters, sms = _clusters(text), None
    for l in lims:
        unit, how, mx, name = l.get("unit"), l.get("count") or "", l.get("max"), f"{p['id']} {l['field']}"
        if how.startswith("sms"):
            if sms is None:
                sms = enc, n, segs, odd = sms_units(text)
                info.append(f"SMS: {enc}" + (f" (because of {odd!r})" if odd else "") +
                            f", {n} {'septets' if enc == 'GSM-7' else 'UTF-16 units'}, {segs} segment(s)")
            enc, n, segs, odd = sms
            want = "UCS-2" if "ucs2" in how else "GSM-7" if "gsm7" in how else enc
            if (how == "sms_gsm7" and enc == "UCS-2" and mx is not None
                    and not any(x.get("count") in ("sms", "sms_ucs2") for x in lims)):
                # the writer asked for one GSM-7 SMS and no row of the text's own encoding is selected: say it is not
                fails.append(f"{name}: does not fit one GSM-7 SMS: UCS-2 because of {odd!r}, {n} UTF-16 units, "
                             f"{segs} segment(s)")
                continue
            if mx is None or want != enc or how.endswith("_segment"):  # another encoding's row; a segment size
                continue
            cap = min(mx, SMS_ONE[enc][0]) if how == "sms" else mx
            if n > cap:
                fails.append(f"{name}: {enc} message, {n} {'septets' if enc == 'GSM-7' else 'UTF-16 units'} > max "
                             f"{cap} for one SMS ({segs} segments)")
            continue
        n = {"chars": len(text), "words": st["words"], "bytes": len(text.encode("utf-8")),
             "lines": text.count("\n") + 1, "count": counts.get(_count_key(l))}.get(unit)
        if n is None:
            continue
        if l.get("min") is not None and unit != "count" and n < l["min"]:
            fails.append(f"{name}: {n} {unit} < min {l['min']}")
        if mx is not None and how == "x_weighted":
            w = x_weighted(text)
            if w > mx:
                fails.append(f"{name}: {w} X-weighted chars > max {mx} (a link counts 23, an emoji or CJK character 2)")
        elif mx is not None and how.startswith("double_width"):
            w = width_count(text, how == "double_width_emoji")
            if w > mx:
                fails.append(f"{name}: {w} chars > max {mx} (a double-width CJK character"
                             + (" or an emoji" if how == "double_width_emoji" else "") + " counts 2)")
        elif mx is not None and how == "code_points":
            if n > mx:
                fails.append(f"{name}: {n} code points > max {mx} ({len(clusters)} visible characters; a vowel sign, "
                             f"virama or emoji modifier counts too)")
        elif mx is not None and unit == "chars":
            g = len(clusters)
            if g > mx:
                fails.append(f"{name}: {g} chars" + (f" ({n} code points)" if n != g else "") + f" > max {mx}")
            elif n > mx:  # Devanagari / emoji: over in code points, within visible characters
                warns.append(f"{name}: {n} code points > max {mx} but {g} visible characters; "
                             f"check the platform's own counter")
        elif mx is not None and n > mx:
            fails.append(f"{name}: {n} {unit} > max {mx}")
        if l.get("visible") and unit == "chars":
            info.append(f"visible before truncation ({l['visible']} chars): {''.join(clusters[:l['visible']])!r}")
    if st["devanagari"] and p and "sms" in p["id"]:
        info.append("Devanagari forces UCS-2 encoding: 70 chars per SMS segment (67 when concatenated)")
    return fails, warns, info


# ---------------------------------------------------------------- docs + stats

def stats():
    hv, cs = harvest(), cards()
    return {"harvest": dict(Counter(it["kind"] for it in hv.values())), "cards": dict(Counter(c["kind"] for c in cs)),
            "verdicts": dict(Counter((c.get("verified") or {}).get("verdict") for c in cs if c.get("verified"))),
            "uncarded": len(set(hv) - {c.get("id") for c in cs})}


DOCS_STAMP = "Generated by `python pcw.py docs` on "


def docs_text(day=None):
    cs, s = cards(), stats()
    L = ["# PCW: professional content writer", "",
         f"{DOCS_STAMP}{day or date.today()}. Contract: `CONTRACT.md`.", "",
         "Before writing anything: `python pcw.py brief \"<what you are writing>\"`; after: "
         "`python pcw.py check draft.txt --genre <id> [--platform <id>]`.", "",
         f"Cards: {sum(s['cards'].values())} ({', '.join(f'{k} {v}' for k, v in sorted(s['cards'].items()))}). "
         f"Verdicts: {s['verdicts']}.", ""]
    for kind in KINDS:
        rows = sorted((c for c in cs if c.get("kind") == kind), key=lambda c: c.get("id"))
        if not rows:
            continue
        L += [f"## {kind} ({len(rows)})", "", "| id | name | status | verified | summary |", "|---|---|---|---|---|"]
        for c in rows:
            v = c.get("verified") or {}
            ver = f"{v.get('verdict')} {v.get('score')}" if v else ""
            L.append(f"| `{c['id']}` | {c['name']} | {c.get('status')} | {ver} | "
                     f"{(c.get('summary') or '').replace('|', '/')[:140]} |")
        L.append("")
    return "\n".join(L)


def _undated(md):
    return "\n".join(l for l in md.splitlines() if not l.startswith(DOCS_STAMP))


def docs_fresh():
    """True when PCW.md matches what `docs` would write today (the date line aside)."""
    f = HERE / "PCW.md"
    return f.exists() and _undated(f.read_text(encoding="utf-8")) == _undated(docs_text())


def docs():
    """Regenerate PCW.md. Rewritten only when the content changed, so re-running is a no-op (no date-only diffs)."""
    if not docs_fresh():
        (HERE / "PCW.md").write_text(docs_text(), encoding="utf-8")
    return HERE / "PCW.md"


def selftest():
    """In-memory checks of the lint and card rules (no files touched)."""
    global card
    real = card
    g = {"id": "genre:t", "kind": "genre", "lint": {"max_words": 12, "require": [{"label": "CTA", "regex": "(?i)reply"}],
                                                   "ban": [{"label": "spam", "regex": "(?i)free money"}]}}
    p = {"id": "plat:t", "limits": [{"field": "body", "max": 40, "unit": "chars", "visible": 10}]}
    sms = {"id": "plat:s", "limits": [{"field": "message body, one SMS", "max": 160, "unit": "chars", "count": "sms"}]}
    card = lambda i, kind=None: {"genre:t": g, "plat:t": p, "plat:s": sms}.get(i)  # noqa: E731  (kind: test cards)
    try:
        f, w, _ = check_text("We delve into it. Free money — reply today.", "genre:t", "plat:t")
        assert any("spam" in x for x in f) and any("plat:t body" in x for x in f), f
        assert any("AI vocabulary" in x for x in w) and any("dashes" in x for x in w), w
        f, w, _ = check_text("Short note. Reply if useful.", "genre:t", "plat:t")
        assert not f and not w, (f, w)
        f, _, _ = check_text("No call to action here at all.", "genre:t")
        assert f == ["missing: CTA"], f
        assert check_text("  \n", "genre:t")[0][0] == "draft is empty"
        p["limits"][0]["max"] = 8  # "नमस्ते दोस्तों" = 14 code points, 6 visible characters
        f, w, _ = check_text("नमस्ते दोस्तों", None, "plat:t")
        assert not f and any("visible characters" in x for x in w), (f, w)
        p["limits"][0]["max"] = 5
        assert not check_text(chr(0xFEFF) + "Hello\r\n", None, "plat:t")[0]  # BOM + newline from an editor do not count
        assert check_text("x" * 158, None, "plat:s")[0] == []  # GSM-7: 160 septets fit one SMS
        assert check_text("Flat ₹200 off today. -SHOP " + "x" * 50, None, "plat:s")[0]  # ₹ makes it UCS-2: 70
    finally:
        card = real
    assert stats_text("एक दो। तीन")["fk_grade"] is None and stats_text("One two. Three four.")["sentences"] == 2
    assert stats_text('He said "stop." Then he left. (It rained.) Next.')["sentences"] == 4
    assert stats_text("Dr. Mehta pays Rs. 499 for Plot No. 14, e.g. the corner one.")["sentences"] == 1
    assert stats_text("| a b | c |\n![x](y.svg) Done!")["exclamations"] == 1
    st = stats_text("Made in India \U0001F1EE\U0001F1F3 \U0001F44D\U0001F3FD ⭐ ✓ ★ order #4821 #Diwali FY2025–26")
    assert (st["emoji"], st["hashtags"], st["dashes"]) == (3, 1, 0), st
    for s, tell in (("It’s not a bug. It’s a feature.", True), ("In today’s fast-paced world, we ship.", True),
                    ("Certainly! Here is the draft.", True), ("It's not ready yet, but the beta opens on Friday.", False),
                    ("I hope this email finds you well.", True), ("We delved into the data.", True),
                    ("Let me know if you need a GST copy.", False)):
        assert any("AI tell" in x for x in check_text(s)[1]) == tell, s
    assert x_weighted("नमस्ते https://example.com/a/very/long/link \U0001F44D 中") == 6 + 1 + 23 + 1 + 2 + 1 + 2
    hv = {"genre:a": {"name": "A"}, "fw:b": {"name": "B"}, "tech:c": {"name": "C"}}
    base = dict(zip(COMMON, ("genre:a", "genre", "A", "current", "s", ["u"], ["v"], "high")))
    full = dict(base, buyers=["x"], value="high", goal="g", structure=[{"part": "p", "does": "d"}], length={"min": 1},
                frameworks=["fw:b"], techniques=["tech:c"], checklist=["c"], pitfalls=["p"], lint={"max_words": 99},
                exemplar_brief="e")
    assert check_card(full, hv) == [], check_card(full, hv)
    assert any("not in the harvest" in x for x in check_card(dict(full, frameworks=["fw:zz"]), hv))
    assert any("must hold fw: ids" in x for x in check_card(dict(full, frameworks=["tech:c"]), hv))
    assert any("must be a list" in x for x in check_card(dict(full, frameworks="fw:b"), hv))
    assert any("unknown keys" in x for x in check_card(dict(full, lint={"max_word": 3}), hv))
    assert any("cubic" in x for x in check_card(dict(full, lint={"ban": [{"label": "b", "regex": r"(?m)^\s*-"}]}), hv))
    assert any("missing" in x for x in check_card(base, hv))
    return "selftest OK"


# ---------------------------------------------------------------- CLI

class DraftError(ValueError):
    """A draft that cannot be read as text: missing, a folder, binary, or not UTF-8 / UTF-16."""


_BOMS = ((b"\xff\xfe\0\0", "utf-32"), (b"\0\0\xfe\xff", "utf-32"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"))


def read_draft(src="-"):
    """The draft as text from a file path, or from stdin for "-". UTF-8 (with or without a BOM), or UTF-16 / UTF-32
    with a BOM (Windows PowerShell 5.1 `>` writes UTF-16); CRLF becomes LF. Anything else raises DraftError."""
    where = "stdin" if src == "-" else repr(src)
    if src == "-":
        data = sys.stdin.buffer.read()
    elif not src or not Path(src).exists():
        raise DraftError(f"no such draft file: {where}")
    elif Path(src).is_dir():
        raise DraftError(f"{where} is a folder, not a draft file")
    else:
        data = Path(src).read_bytes()
    enc = next((e for bom, e in _BOMS if data.startswith(bom)), "utf-8-sig")
    try:
        text = data.decode(enc)
    except UnicodeDecodeError as e:
        raise DraftError(f"{where}: not UTF-8 text (byte {e.start}); save the draft as UTF-8") from None
    if chr(0) in text:
        raise DraftError(f"{where}: binary data, not a text draft")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _args(cmd, rest, flags, positional, nargs, intermixed=False):
    """argparse for one subcommand: unknown flags, a flag without a value, an empty value and stray words exit 2."""
    ap = argparse.ArgumentParser(prog=f"python pcw.py {cmd}", allow_abbrev=False)
    ap.add_argument(positional, nargs=nargs)
    for f in flags:
        ap.add_argument(f"--{f}")
    a = ap.parse_intermixed_args(rest) if intermixed else ap.parse_args(rest)
    for f in flags:
        if getattr(a, f) is not None and not getattr(a, f).strip():
            ap.error(f"--{f} needs a value")
    return ap, a


def _no_data():
    if any((HERE / "harvest").glob("*.json")):
        return False
    print(f"pcw: no harvest/*.json under {HERE} (is PCW_HOME right?)", file=sys.stderr)
    return True


def _main(argv):
    if not argv:
        print(__doc__)
        return 0
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cmd, rest = argv[0], list(argv[1:])
    if cmd in ("find", "card", "ids", "brief", "dupes", "batches", "stats", "docs") and _no_data():
        return 2
    if cmd == "find":
        if not rest:
            print('usage: python pcw.py find "<words>" [kind]', file=sys.stderr)
            return 2
        kind = kind_of(rest[-1]) if len(rest) > 1 else None
        if len(rest) > 1 and rest[-1].endswith(":") and not kind:
            print(f"unknown kind {rest[-1]!r}: one of {sorted(KINDS)}, or an id prefix and a colon (plat:)",
                  file=sys.stderr)
            return 2
        for c in find(" ".join(rest[:-1] if kind else rest), kind):
            v = (c.get("verified") or {}).get("verdict", "")
            print(f"[{c['id']}{' ' + v if v else ''}] {c['name']}: {(c.get('summary') or '')[:110]}")
    elif cmd == "card":
        if len(rest) != 1:
            print("usage: python pcw.py card <id or exact name>", file=sys.stderr)
            return 2
        c = card(rest[0])
        print(json.dumps(c, indent=1, ensure_ascii=False))
        if c is None:
            print(f"no card {rest[0]!r}; try: python pcw.py find \"<words>\"", file=sys.stderr)
            return 1
    elif cmd == "ids":
        kind = kind_of(rest[0]) if rest else None
        print("\n".join(ids(kind, " ".join(rest[1:] if kind else rest))))
    elif cmd == "brief":
        _, a = _args(cmd, rest, ("genre", "platform", "lang", "tone"), "request", "*", intermixed=True)
        try:
            out = brief(" ".join(a.request), a.genre, a.platform, a.lang, a.tone)
        except LookupError as e:
            print(e, file=sys.stderr)
            return 1
        print(out)
        if out.startswith("No genre card matches"):  # no brief: a pipeline must be able to tell (exit 1)
            return 1
    elif cmd == "check":
        ap, a = _args(cmd, rest, ("genre", "platform", "field"), "draft", "?")
        if a.field and not a.platform:
            ap.error("--field needs --platform")
        if (a.genre or a.platform) and _no_data():
            return 2
        src = "-" if a.draft is None else a.draft
        if src == "-" and (sys.stdin is None or sys.stdin.isatty()):  # no file and nothing piped: don't hang
            print("usage: python pcw.py check <draft.txt> [--genre ID] [--platform ID] [--field NAME]  (or pipe text in)")
            return 2
        try:
            text = read_draft(src)
        except (DraftError, OSError) as e:  # exit 2: an unreadable draft is not a lint verdict (1)
            print(f"pcw check: {e}", file=sys.stderr)
            return 2
        fails, warns, info = check_text(text, a.genre, a.platform, a.field)
        print("\n".join([f"[fail] {x}" for x in fails] + [f"[warn] {x}" for x in warns] + [f"[info] {x}" for x in info]))
        print("OK: no fails" if not fails else f"{len(fails)} fail(s)")
        return 1 if fails else 0
    elif cmd == "validate":
        issues = validate(rest or None)
        print("\n".join(issues) or "OK: 0 issues")
        return 1 if issues else 0
    elif cmd == "dupes":
        print("\n".join(dupes()) or "no name collisions")
    elif cmd == "batches":
        try:
            print("\n".join(batches(rest or None)))
        except ValueError as e:
            print(f"pcw batches: {e}", file=sys.stderr)
            return 1
    elif cmd == "stats":
        print(json.dumps(stats(), indent=1))
    elif cmd == "docs":
        print(docs())
    elif cmd == "selftest":
        print(selftest())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
