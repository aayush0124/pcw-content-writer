# Brief: PCW card writer (wave 2)

You write PCW knowledge cards: the reference a writing session reads before it writes a piece for a paying client.
The reader of your card is another AI writer with no other context. A card is good when a writer who follows it
produces a piece a senior human professional would sign off.

**Spec:** `CONTRACT.md`, section "Card format" (read it whole, including the per-kind extra fields
and the genre `lint` format). Your batch file and output file are named in your prompt.

## Do this, in order

1. Read CONTRACT.md "Card format", then your batch file `work/batches/<batch>.json`. Each item
   carries the harvest's sources and notes; use them.
2. Write `cards/<batch>.json` = `{"cards": [...]}` with one card per batch item, `id` and `name`
   copied exactly. Put the first half of the batch on disk within ~12 minutes, then finish.
3. Cross-references: every id you name (`related`, `frameworks`, `techniques`, `hooks`, `platforms`, `tones`,
   `compliance`, `fits`, `works_on`) must exist. Look them up, do not invent them:
   `python pcw.py ids <kind> <words>` (kinds: genre framework technique hook platform tone language
   editing compliance trend). Prefer 2-6 strong references over a long weak list.
4. Validate until clean: `python pcw.py validate cards/<batch>.json`.

## Quality bar

- Write as a senior practitioner training a junior: concrete, actionable, in the order the work happens. "Use
  specific numbers" is useless; "replace 'many clients' with the count and the time window, e.g. '212 CA firms in 9
  months'" is a card.
- **No invented facts.** A number, a rule, a limit, an origin ("coined by X in 19YY") or a study result appears only
  when a source in the batch item or a source you fetched supports it, and that source goes in the card's `sources`.
  If you are not sure, write the guidance without the number. Platform `limits` are copied from the harvest unchanged.
- Examples, `before`/`after`, `mini_example`, `sample`, hook `examples` are ORIGINAL (written by you). Never paste
  copyrighted copy; name a famous piece and its URL instead.
- India first, global ready: where a worked example helps, set it in an Indian context (a Pune D2C brand, a CA firm in
  Jaipur, a Bihar civic story), and include Hinglish where the format is native to Hinglish (reels, captions, WhatsApp).
- `avoid` and `pitfalls` name the real failure and what to do instead, not generic warnings.
- `status`: `current` (standard practice), `rising` (growing in 2025-26, sourced), `declining`, `dated` (still asked
  for, old-fashioned), `niche`.

## Genre cards (the most important kind)

- `structure`: the parts in order, each with what it must do and a length (words, lines, seconds or slides).
- `length`: realistic range for the deliverable; say what drives it in `note`.
- `checklist`: 6-12 yes/no checks a finished piece must pass (each one checkable by reading the piece).
- `lint`: machine rules `pcw.py check` applies. Only rules a GOOD piece always passes and a bad one often fails:
  word range, sentence length ceilings, `require` (e.g. a CTA verb, a subject line marker) and `ban` (e.g. spam
  words for email, "click here" for UX). Regexes must be simple, case-insensitive (`(?i)`), and must not fail a good
  Hindi or Hinglish draft unless the genre is English-only. Leave `grade_max` out of creative genres.
  `pcw.py check` ends a sentence at `.` `!` `?` `।` AND at every line break, so bullets, slide lines and table rows
  each count as their own unit; sentence-length limits are safe for list-heavy genres.
- `exemplar_brief`: one concrete assignment the verify wave will write from this card: client, audience, offer or
  topic, channel, length, language. Make it realistic and specific, e.g. "Cold email from a Jaipur CA firm offering
  GST notice handling to D2C founders doing Rs 5-50 crore revenue; English; under 120 words; goal: a 15-minute call."
- `value` + `value_why`: from the harvest item's `value` / `value_evidence`, plus any matching entry in
  `work/trends_value/value_evidence.json` (2026 rate and demand evidence: EFA 2026 rate chart, BLS,
  Upwork In-Demand Skills 2026, AmbitionBox India). Quote a rate only with its source in `sources`.
- Trends that change how the genre is written in 2026 are trend cards; find them with
  `python pcw.py ids trend` and add the relevant ones to `related` (the brief surfaces them).

## Hand-back

Plain text, short: cards written, validate result, any item you think is a duplicate of another id (name both), any
reference you wanted but could not find an id for (it may be a gap).
