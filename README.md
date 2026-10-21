# PCW: professional content writer

PCW is a verified, offline knowledge base for writing jobs: content-writing genres, the frameworks and techniques
professionals use, hook and headline families, the hard limits of the platforms the words land on (each number with
the source's own words and URL), tones, languages (English, Hindi, Hinglish), editing passes, the law that applies to
published copy (India first: ASCI, CCPA, DPDP, IT Rules, ECI, BNS, SEBI, TRAI, FSSAI, RERA; plus FTC, CAN-SPAM, EU
rules) and 2026 trends with dated evidence. A writer (human or AI) reads a brief from it before writing and lints the
draft against it afterwards.

"Training" here means a curated, sourced and tested knowledge base that a writing session reads. It is not model
fine-tuning. Everything runs on the Python standard library, with no network and no API key.

## Quick start

```bash
git clone <this repo> pcw && cd pcw
python pcw.py brief "cold email to D2C founders"           # what to write and how
python pcw.py check draft.txt --genre genre:cold_email       # lint the draft (exit 1 on any fail)
python pcw.py check post.txt --platform plat:linkedin_post   # platform limits
python pipeline.py status                                    # where the build stands
python -m unittest discover -s tests -v                      # offline test suite
```

Python 3.10 or newer. Character limits count visible characters (grapheme clusters), so a Hindi conjunct or an
emoji with a skin tone is one character; the standard-library segmenter follows UAX #29 for Latin, Indic scripts,
emoji sequences, Hangul and CRLF, and `pip install regex` (optional) switches to the full rules for every script.
Limits whose source says otherwise are counted the platform's way: X posts with X's weights (emoji and CJK 2, a link
23, with or without `https://`), SMS in GSM-7 septets or UCS-2 units, Telegram bios in code points, Google Ads with a
double-width (CJK) character as 2 and Microsoft Ads with CJK and emoji as 2. Run from any folder; set `PCW_HOME` to
read the data from another copy.

## How a writing job runs

1. **Brief.** `python pcw.py brief "<what you are writing>"` picks the genre card and prints its goal, buyers,
   length, structure, checklist, pitfalls, the linked frameworks, techniques and hook templates, the platform limits
   (with the "visible before truncation" window), tone and language rules, the legal checklists that apply, live
   trends, and the genre's lint rules; platforms and laws whose own cards name the genre are listed as one-line
   pointers. Pass `--genre`, `--platform`, `--lang`, `--tone` to override the picks; find ids with
   `python pcw.py find "<words>" [kind]`. When no genre card matches, `brief` prints a `No genre card matches` line
   and exits 1: write from the nearest card and log a gap.
2. **Write** from the brief, in its structure order. Facts come from the client or a citable source; anything else is
   a visible placeholder.
3. **Check.** `python pcw.py check draft.txt --genre <id> [--platform <id>] [--field "<limit field>"]` fails on the
   genre's lint (word range, sentence ceilings, required and banned patterns, emoji / hashtag / exclamation caps) and
   on platform limits; it warns on high-signal AI-writing tells and on every em/en dash (house rule; number ranges
   aside). The AI-vocabulary list is sense-blind ("foster parents" warns too): a warn kept for a domain sense is
   reported in the deliver line. A platform with several fields (headline / description, subject / preheader) is
   enforced one field at a time with `--field` (the brief's `check:` line names them; an exact field name selects that
   field, other words match by substring); without it, check warns that nothing was measured. A `--field` that fits
   several alternative surfaces of one unit (LinkedIn's introductory text for single image and for carousel) is a fail
   that asks for the full name. Exit 0 = no fails, 1 = fails, 2 = a usage error or a draft that cannot be read
   (missing path, a folder, not UTF-8 / UTF-16 text).

## CLI

| command | what it does |
|---|---|
| `pcw.py brief "<request>" [--genre ID] [--platform ID] [--lang ID] [--tone ID]` | the writer's brief, as Markdown; exit 1 for an unknown id, or when no genre card matches (the `No genre card matches` line) |
| `pcw.py check <draft.txt> [--genre ID] [--platform ID] [--field NAME]` | lint a draft; no path or `-` reads stdin (a bare `check` waits for piped text); exit 0 pass, 1 fails, 2 usage or unreadable draft |
| `pcw.py find "<words>" [kind]` | ranked card search (kind: a kind name or an id prefix with its colon, `plat:`) |
| `pcw.py card <id>` | one card as JSON (`null` and exit 1 when there is none) |
| `pcw.py ids [kind] [words]` | harvested ids, for cross-references |
| `pcw.py validate [file ...]` | harvest + cards against the contract; exit 1 on issues |
| `pcw.py dupes` | harvest items that look like the same thing |
| `pcw.py batches [kind ...]` | merged harvest into agent-sized batches (idempotent) |
| `pcw.py stats` / `pcw.py docs` | counts / regenerate `PCW.md` (the card index) |
| `pcw.py selftest` | in-memory checks of the lint and card rules |
| `pipeline.py status / doctor / run <stage> / all` | the build pipeline (below) |

As a library: `import pcw; pcw.brief("press release"); pcw.check_text(text, genre="genre:press_release")`.
`brief()` raises `LookupError` when an id passed as `genre`, `platform`, `lang` or `tone` is unknown or of another
kind; `check_text()` reports it as a fail. Drafts are read as UTF-8 (with or without a BOM) or UTF-16 with a BOM.
Windows PowerShell 5.1 pipes text as ASCII by default, so every non-ASCII character (Hindi, ₹, curly quotes, emoji)
arrives as `?` and the check runs on that; pass a file path there. Piped text in a legacy code page that is not valid
UTF-8 is rejected (exit 2).

## Kinds

Every item has one global id `<prefix>:<slug>` and lives in exactly one kind (`CONTRACT.md` has the full spec).

| kind | prefix | one item is |
|---|---|---|
| genre | `genre:` | a deliverable someone commissions (cold email, VSL script, press release, reel script ...) |
| framework | `fw:` | a named structure for a piece or section (AIDA, PAS, SCQA, inverted pyramid ...) |
| technique | `tech:` | a craft move at line, paragraph or piece level (open loop, specificity, risk reversal ...) |
| hook | `hook:` | a family of hooks, headlines, subject lines or titles |
| platform | `plat:` | one surface where text is published, with its sourced limits |
| tone | `tone:` | a voice or register |
| language | `lang:` | a language or variety and its writing rules |
| editing | `edit:` | an editing pass or quality method |
| compliance | `comp:` | a law, code or platform policy that published copy must obey |
| trend | `trend:` | something current in 2026, with dated evidence |

## Pipeline and coverage

`python pipeline.py status` reports every stage with live counts (exit 0 ok, 10 needs attention, 1 failure);
`run <stage>` runs one deterministic stage, `all` runs them in order, `doctor` checks the environment. Agent stages
need an LLM agent, never run from CI, and `status` names the brief that drives each one.

1. **harvest** (agent): research workers list everything PCW must know from cited sources into `harvest/*.json`.
2. **batches**: `pcw.py batches` merges the harvest and splits it into `work/batches/<kind>_<nn>.json`.
3. **cards** (agent): one card per harvested item, `cards/<kind>_<nn>.json` (`work/BRIEF_CARDS.md`).
4. **validate** / **dupes**: the contract checks, then near-duplicate names for the critic.
5. **samples** (agent): for every genre, hook and framework card, a demo piece written only from `pcw.py brief`,
   linted by `pcw.py check`, saved in `gallery/` (`work/BRIEF_VERIFY.md`, Writer).
6. **judge** (agent): a second, independent agent scores each piece 0-2 on purpose, structure, specificity, voice
   and craft (total 8+ pass, 6-7 weak, 5 or less wrong) and writes the verdict into the card. A weak or wrong
   verdict blamed on the card means the card is rewritten and the piece re-tested.
7. **fixes**: `work/lead/collect_fixes.py` gathers the judges' CARD FIX notes for a fixer agent.
8. **critic** (agent): `cards/zz_critic.json`, gaps and next steps from `work/gaps.jsonl`.
9. **docs**: `PCW.md` and the table below.

The table is written by `python pipeline.py run docs` from `pipeline.py status`; it is never typed by hand.

<!-- pipeline-status:begin -->
| stage | kind | state | numbers |
|---|---|---|---|
| harvest | agent | ok | 879 items from 30 files, 1559 cited sources (compliance 102, editing 45, framework 67, genre 290, hook 54, language 21, platform 108, technique 127, tone 35, trend 30) |
| batches | code | ok | 879/879 items batched |
| cards | agent | ok | 879 cards, 0 harvest items without a card (compliance 102, editing 45, framework 67, genre 290, hook 54, language 21, platform 108, technique 127, tone 35, trend 30) |
| validate | code | ok | 0 issues |
| dupes | code | ok | 4 name collisions left for the critic |
| samples | agent | ok | 411/411 genre, hook and framework cards have a demo piece |
| judge | agent | attention | 410/411 judged: pass 409, weak 1, wrong 0, not_tested 1; 79 cards rewritten after judging |
| fixes | code | ok | 0 cards with an open CARD FIX note |
| critic | agent | ok | zz_critic.json as of 2026-10-13: 14 gaps, 7 weak cards, 11 doubts, 10 next steps; 0 gaps logged since |
<!-- pipeline-status:end -->

Technique, editing, tone, language, platform, compliance and trend cards are validated against their cited sources
but were not demo-tested; only genre, hook and framework cards carry a judge's verdict.

## Data

- `harvest/*.json`: the ground truth, one file per research worker. Items carry `sources` (URL, title, what the
  source supports); platform limits carry the number, unit, URL, check date, the source's own words in `quote` and a
  confidence; trends carry dated evidence. Quotes are short (25 words or fewer) and attributed.
- `cards/*.json`: one card per item, written from the harvest; `cards/zz_critic.json` is the critic's report.
- `gallery/*.json`: the demo pieces the judges scored, with the `pcw.py check` output for each.
- `work/batches/`: the batch files the cards were written from (`validate` checks cards against them);
  `work/BRIEF_*.md`: the agent briefs; `work/gaps.jsonl`: requests no card covered yet.
- `PCW.md`: the generated card index.

## Known gaps

- Platforms with no official limit found (Facebook organic posts, Threads bio, Quora answers, some Indian short-video
  apps) and conflicting official numbers (kept with a "which to trust" note on the card).
- `check` does not implement TikTok's UTF-16 count or X's weighting on X surfaces other than `plat:x_post`; limits in
  seconds, pixels or link counts are checked by hand from the brief. Readability grades are English-only. X links
  typed without `https://` are found with a compact list of generic TLDs, so one on an unlisted TLD (`.world`) is
  under-counted.
- Alternative surfaces that share a field name (LinkedIn's introductory text for single image and for carousel,
  Telegram's bio with and without Premium, Meta Ads headlines per placement): when they are the platform's only text
  field (Telegram's bio) a bare `check --platform` enforces all of them; otherwise a bare check measures nothing and
  warns. A `--field` that fits several asks for one; pass the full field name, e.g. `--field "bio (Premium)"`.
- Laws and platform rules change: every compliance card has an `as_of` date and every limit a `checked` date; the
  critic's report lists the items to re-check monthly. The cards are writing guidance, not legal advice.
- The full gap list and next steps are in `cards/zz_critic.json`, a snapshot as of its `critic.date` (later fixes
  are added to its `resolved` list).

## Use it from Claude (skill)

`skill/SKILL.md` is a Claude skill that makes every writing task start with `pcw.py brief` and end with
`pcw.py check`. Copy it to `~/.claude/skills/pcw/SKILL.md` and set `PCW_HOME` to your clone (or replace `$PCW_HOME`
in the file with the path). It also tells the writer to log uncovered requests to `work/gaps.jsonl`.

## Tests

`python -m unittest discover -s tests -v` runs offline with the standard library: every `pcw.py` and `pipeline.py`
subcommand (exit codes and output shape), data integrity (every card validates, ids unique, every reference and
verdict resolves), golden queries, negative tests (over-limit posts and bad cards are flagged), reproducible docs,
`selftest`, and `tests/test_public_scrub.py`, which fails on machine paths, private names, personal data,
credentials, vendor files, files over 5 MB and quotes over 25 words in anything git would track. CI runs the suite
on Ubuntu and Windows with Python 3.12 and 3.14.

## License

Code: MIT (`LICENSE`). Cards, briefs and docs: CC BY 4.0. Harvested quotes remain their owners' and appear only as
short, attributed excerpts with their source URLs. PCW is not affiliated with any platform, regulator or publisher it
cites; product and platform names are trademarks of their owners.
