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

Python 3.10 or newer. Optional: `pip install regex` makes character limits count visible characters (grapheme
clusters) instead of code points, which matters for Devanagari and emoji. Run from any folder; set `PCW_HOME` to
read the data from another copy.

## How a writing job runs

1. **Brief.** `python pcw.py brief "<what you are writing>"` picks the genre card and prints its goal, buyers,
   length, structure, checklist, pitfalls, the linked frameworks, techniques and hook templates, the platform limits
   (with the "visible before truncation" window), tone and language rules, the legal checklists that apply, live
   trends, and the genre's lint rules. Pass `--genre`, `--platform`, `--lang`, `--tone` to override the picks; find
   ids with `python pcw.py find "<words>" [kind]`.
2. **Write** from the brief, in its structure order. Facts come from the client or a citable source; anything else is
   a visible placeholder.
3. **Check.** `python pcw.py check draft.txt --genre <id> [--platform <id>] [--field "<limit field>"]` fails on the
   genre's lint (word range, sentence ceilings, required and banned patterns, emoji / hashtag / exclamation caps) and
   on platform limits; it warns on high-signal AI-writing tells and dashes. A platform with several fields (headline /
   description, subject / preheader) is enforced one field at a time with `--field`.

## CLI

| command | what it does |
|---|---|
| `pcw.py brief "<request>" [--genre ID] [--platform ID] [--lang ID] [--tone ID]` | the writer's brief, as Markdown |
| `pcw.py check <draft.txt> [--genre ID] [--platform ID] [--field NAME]` | lint a draft (or pipe text in); exit 1 on fails |
| `pcw.py find "<words>" [kind]` | ranked card search |
| `pcw.py card <id>` | one card as JSON |
| `pcw.py ids [kind] [words]` | harvested ids, for cross-references |
| `pcw.py validate [file ...]` | harvest + cards against the contract; exit 1 on issues |
| `pcw.py dupes` | harvest items that look like the same thing |
| `pcw.py batches [kind ...]` | merged harvest into agent-sized batches (idempotent) |
| `pcw.py stats` / `pcw.py docs` | counts / regenerate `PCW.md` (the card index) |
| `pcw.py selftest` | in-memory checks of the lint and card rules |
| `pipeline.py status / doctor / run <stage> / all` | the build pipeline (below) |

As a library: `import pcw; pcw.brief("press release"); pcw.check_text(text, genre="genre:press_release")`.

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
| harvest | agent | ok | 851 items from 23 files, 1450 cited sources (compliance 79, editing 45, framework 67, genre 290, hook 54, language 21, platform 103, technique 127, tone 35, trend 30) |
| batches | code | ok | 851/851 items batched |
| cards | agent | ok | 851 cards, 0 harvest items without a card (compliance 79, editing 45, framework 67, genre 290, hook 54, language 21, platform 103, technique 127, tone 35, trend 30) |
| validate | code | ok | 0 issues |
| dupes | code | ok | 4 name collisions left for the critic |
| samples | agent | ok | 411/411 genre, hook and framework cards have a demo piece |
| judge | agent | ok | 411/411 judged: pass 409, weak 1, wrong 0; 79 cards rewritten after judging |
| fixes | code | ok | 0 cards with an open CARD FIX note |
| critic | agent | ok | zz_critic.json as of 2026-10-13: 14 gaps, 8 weak cards, 10 doubts, 9 next steps; 0 gaps logged since |
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
- `check` does not implement X's weighted character counting or TikTok's UTF-16 count; limits in seconds, pixels or
  link counts are checked by hand from the brief. Readability grades are English-only.
- Laws and platform rules change: every compliance card has an `as_of` date and every limit a `checked` date; the
  critic's report lists the items to re-check monthly. The cards are writing guidance, not legal advice.
- The full gap list and next steps are in `cards/zz_critic.json`.

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
