# PCW contract (professional content writer)

PCW is what every writing job on this machine knows about **content writing**: every genre a client pays for, the
frameworks and techniques professionals use, hook and headline formulas, the hard limits of every platform the words
land on, tones, languages (English, Hindi, Hinglish), editing passes, the law that applies to published copy, and what
is trending in 2026. Sibling of PVE (After Effects + Premiere) and PGD (Photoshop + Illustrator + CorelDRAW). Same
pipeline, adapted to text:

1. **harvest** (`harvest/<file>.json`): the list of everything PCW must know, built from cited sources (platform help
   centres, regulators, style guides, course syllabi, freelance-market category lists). For writing, the "live app" is
   the published source: a limit, a rule, a framework's origin or a trend is only true if a source on the record says so.
2. **batches** (`python pcw.py batches` -> `work/batches/<kind>_<nn>.json`): the merged, de-duplicated harvest split
   into agent-sized batches.
3. **cards** (`cards/<kind>_<nn>.json`): one card per harvested item. `python pcw.py validate` must report 0 issues.
4. **gallery** (`gallery/<kind>_<nn>.json`): for every genre, hook and framework card, a demo piece written ONLY from
   `python pcw.py brief <id>` output, linted by `python pcw.py check`, then scored by a second, independent agent.
5. **verify**: the score and verdict are written into the card; a weak or wrong verdict means the CARD is rewritten
   (the guidance failed), then the piece is rewritten and re-judged.
6. **critic** (`cards/zz_critic.json`: gaps and next steps), then `PCW.md` (`python pcw.py docs`). The critic writes
   `"gaps_seen": <number of work/gaps.jsonl lines it read>` at the top level, so `pipeline.py status` counts every gap
   logged after it ran, the same day included (without the field, only gaps dated after `critic.date` count).

"Training" here means a curated, verified knowledge base that the writing session reads before it writes. It is not
model fine-tuning.

## Kinds and ids (fixed vocabulary)

Every item has a global id `<prefix>:<slug>` (slug = lower-case ascii, digits, `_`), unique across PCW.

| kind | prefix | what one item is | examples |
|---|---|---|---|
| `genre` | `genre:` | a deliverable someone commissions | `genre:cold_email`, `genre:vsl_script`, `genre:press_release`, `genre:short_form_video_script` |
| `framework` | `fw:` | a named structure for a whole piece or section | `fw:aida`, `fw:pas`, `fw:storybrand_sb7`, `fw:scqa`, `fw:inverted_pyramid` |
| `technique` | `tech:` | a craft move at line, paragraph or piece level | `tech:open_loop`, `tech:specificity`, `tech:bucket_brigade`, `tech:risk_reversal` |
| `hook` | `hook:` | a family of hooks / headlines / subject lines / titles | `hook:how_to`, `hook:contrarian`, `hook:number_list`, `hook:curiosity_gap` |
| `platform` | `plat:` | one surface where text is published, with its limits | `plat:linkedin_post`, `plat:google_ads_rsa`, `plat:email_subject_line`, `plat:sms_india_dlt` |
| `tone` | `tone:` | a voice / register | `tone:authoritative`, `tone:playful_witty`, `tone:luxury_premium`, `tone:satirical_vyangya` |
| `language` | `lang:` | a language or variety and its writing rules | `lang:hinglish_roman`, `lang:hindi_devanagari`, `lang:indian_english`, `lang:us_english` |
| `editing` | `edit:` | an editing pass, checklist or quality method | `edit:ai_tell_removal`, `edit:yoast_readability`, `edit:fact_check`, `edit:seo_on_page` |
| `compliance` | `comp:` | a law, code or platform policy that published copy must obey | `comp:asci_influencer`, `comp:ftc_endorsement_guides`, `comp:dpdp_act_rules`, `comp:eci_mcc` |
| `trend` | `trend:` | something current in 2026, with dated evidence | `trend:geo_ai_search`, `trend:thought_leadership_b2b` |

Each item lives in exactly ONE kind. A thing that is both a genre and a platform (a LinkedIn post) is a genre
(`genre:linkedin_post`: what to write) AND a platform (`plat:linkedin_post`: the limits); the two cards point at
each other through `platforms` / `related`.

## Harvest file format

`harvest/<file>.json` (one file per research worker; `pcw.py batches` merges them by kind):

```json
{"kind": "genre", "worker": "genre_commercial", "as_of": "2026-10-04",
 "source": "how this list was built (one line)",
 "items": [ <item>, ... ]}
```

Item (`id`, `name`, `category`, `one_line` required; leave any other field out rather than guess):

```json
{"id": "genre:cold_email",
 "name": "Cold email (B2B outbound)",
 "category": "Email & CRM",
 "one_line": "Unsolicited first-touch email that earns a reply from a stranger.",
 "aliases": ["outbound email", "prospecting email"],
 "value": "high|medium|low",                         // how much paid demand exists for this; genres only
 "value_evidence": "what the tier rests on: a source, a market list, a rate card",
 "sources": [{"url": "https://...", "title": "...", "supports": "what this source shows"}],
 "limits": [ <limit>, ... ],                          // platform items only, see below
 "evidence": [{"claim": "...", "url": "...", "date": "YYYY-MM-DD"}],   // trend items only
 "note": "anything the card writer must know"}
```

Platform `limits[]` (every number needs its own source; a number from memory is not allowed):

```json
{"field": "post body", "max": 3000, "unit": "chars|words|bytes|lines|count|px|seconds",
 "visible": 210,                       // characters shown before truncation ("see more"), when the source says
 "url": "https://official.help.page/...", "checked": "2026-10-04",
 "quote": "the source's own words for the number (short)",
 "confidence": "high (official page) | medium (official but old / indirect) | low (third-party only)"}
```

Two optional row keys tell `pcw.py check` how to read a row; set them only where the source says so, and copy them
into the card unchanged (validate compares field, max, min, unit, visible, lint and count):
- `"lint": false`: a row the checker must not measure on the draft, such as a URL weight (X counts any link as 23),
  a count of buttons or of tags outside the text. It stays in the brief, checked by hand.
- `"count"` (chars limits only): how the platform counts. `x_weighted` (X: NFC code points, CJK and emoji 2, a
  link 23); `sms` (the message must fit ONE SMS in the encoding it needs: 160 GSM-7 septets, or 70 UTF-16 units
  once any character is outside GSM-7); `sms_gsm7` / `sms_ucs2` (a single-SMS limit for that encoding only; a
  `sms_gsm7` row also fails a message that needs UCS-2 when no UCS-2 row is selected); `sms_gsm7_segment` /
  `sms_ucs2_segment` (the size of each part of a long SMS: reported, never failed); `code_points` (Unicode code
  points, so a vowel sign or virama counts: Telegram's "UTF-8 length"); `double_width` (a double-width CJK character
  counts 2: Google Ads); `double_width_emoji` (CJK and emoji count 2: Microsoft Advertising). Without it a chars
  limit counts visible characters (grapheme clusters).

Rows that share a field name before any `(...)` or `, ...` qualifier ("post text" and "post text (UTF-8 bytes)")
measure the same text, and `check --platform` enforces them together without `--field`; a platform with several
differently named text fields needs `--field` (without it, check warns that nothing was measured). A `--field` that
fits several rows of one unit without naming one exactly (alternative surfaces such as "bio (non-Premium)" and
"bio (Premium)") is a fail that asks for the full name.

Trend `evidence[]`: a claim, the URL, and the date the source was PUBLISHED. A trend with no evidence dated within
the last 12 months (since 2025-10-04) is not a trend; leave it out.

Rules for research workers:
- Prefer primary sources: the platform's own help centre or developer docs, the regulator's own text, the framework's
  originator (book, original article). A blog repeating a number is low confidence; say so.
- A fetch summary is paraphrase. For an exact number or rule, read the page itself and copy the source's words into
  `quote`.
- No copying of copyrighted copy. Famous ads, sales letters and books are cited by name and URL, never pasted.
- Scope partitions are fixed in the worker's brief; do not harvest another worker's kinds. Overlap at the edges is
  removed by the merge, so when unsure whether an item is yours, include it.

## Card format

`cards/<kind>_<nn>.json` = `{"cards": [...]}`, one card per item of `work/batches/<kind>_<nn>.json`, matched by `id`.
`python pcw.py validate cards/<kind>_<nn>.json` must report 0 issues. Every card:

```json
{"id": "<harvested id>", "kind": "<kind>", "name": "<harvested name exactly>",
 "status": "current|rising|declining|dated|niche",
 "summary": "what it is and what good looks like, one or two sentences",
 "use_for": ["concrete jobs this serves"],
 "avoid": ["when it goes wrong and what to use instead"],
 "confidence": "high|medium|low",
 "sources": [{"url": "...", "title": "...", "supports": "..."}],
 "related": ["<other PCW ids>"]}
```

Every id named anywhere in a card (`related`, `frameworks`, `techniques`, `hooks`, `platforms`, `tones`,
`languages`, `compliance`, `fits`, `works_on`) must exist in the merged harvest; the validator checks it. Look ids up
with `python pcw.py ids [kind] [words]`.

Extra fields by kind:

- **genre**: `buyers` (who commissions it), `value` (`high|medium|low`) + `value_why`, `goal` (the one job the
  reader must do after reading), `structure` (`[{"part", "does", "length"}]` in order), `length`
  (`{"min", "max", "unit", "note"}`), `frameworks`, `techniques`, `hooks`, `platforms`, `tones`, `compliance`
  (id lists), `checklist` (yes/no checks a finished piece must pass), `pitfalls`, `lint` (see below),
  `exemplar_brief` (a concrete, India-relevant assignment the verify wave writes a demo piece for: client, audience,
  offer, channel, length).
- **framework**: `steps` (`[{"step", "does"}]`), `best_for`, `not_for`, `origin` (`{"who", "when", "url"}`; leave
  out if unknown, never guess), `mini_example` (original, <= 120 words).
- **technique**: `level` (`line|paragraph|piece`), `how` (instructions a writer can follow), `before` / `after`
  (original lines showing the move), `overuse_signs`.
- **hook**: `templates` (fill-in patterns with `[slots]`), `examples` (>= 3 original; include Hinglish where natural),
  `why_it_works`, `works_on` (platform ids), `risk` (where it tips into clickbait or a broken promise).
- **platform**: `limits` (copied from the harvest, numbers unchanged), `formatting` (what renders: line breaks,
  bold, links, emoji, hashtags, mentions), `writing_notes`, `algorithm_notes` (`[{"note", "url"}]`, sourced only).
- **tone**: `markers` (word choice, sentence shape, punctuation), `avoid`, `sample` (original, <= 80 words), `fits`
  (genre ids).
- **language**: `rules`, `mistakes`, `sample` (original, <= 80 words), `script` (`latin|devanagari|mixed`).
- **editing**: `steps` (ordered passes), `checks` (yes/no).
- **compliance**: `jurisdiction`, `applies_to` (genre ids or plain words), `rules` (`[{"rule", "url"}]`, each sourced),
  `penalty` (sourced or left out), `checks`, `as_of`.
- **trend**: `as_of`, `evidence` (from the harvest), `do`, `dont`, `half_life_months`.

Genre `lint` (machine rules `pcw.py check` applies to a draft of this genre; every key optional):

```json
{"min_words": 50, "max_words": 150,         // body words, whitespace-split
 "max_sentence_words": 25,                  // longest sentence allowed
 "max_avg_sentence_words": 18,
 "grade_max": 9,                            // Flesch-Kincaid grade ceiling, English only
 "require": [{"label": "has a CTA", "regex": "(?i)reply|book|call|click|sign up"}],
 "ban": [{"label": "fake urgency", "regex": "(?i)act now|limited time only"}],
 "max_exclamations": 1, "max_emoji": 0, "max_hashtags": 0}
```

Verification (written by the verify wave):
`"verified": {"verdict": "pass|weak|wrong|not_tested", "score": 0-10, "sample": "gallery/<file>.json#<id>",
"note": "what the judge saw", "judge": "agent label", "date": "YYYY-MM-DD"}`.

## Gallery file format

`gallery/<kind>_<nn>.json` = `{"samples": [{"id": "<card id>", "brief": "<exemplar_brief used>", "text": "...",
"check": "<pcw.py check output>", "writer": "agent label"}]}`. The judge reads the card, the brief and the text, never
the writer's reasoning, and scores 0-2 on each of: purpose (does the reader do the goal), structure (follows the card),
specificity (concrete, no filler), voice (human, no AI tells, right tone), craft (hook, rhythm, CTA). Total >= 8 =
pass, 6-7 = weak, <= 5 = wrong.

## Rules for every agent

- Work in your own folder `work/<your worker label>/` for scratch files; never write generic file names at the PCW
  root or a shared scratchpad root (parallel agents overwrite each other silently).
- Write only the files your brief names. Prose for the lead goes in your hand-back, not in a new .md file.
- Run `python pcw.py validate <your file>` (from the PCW folder) until it reports 0 issues before you hand back.
