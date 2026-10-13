# Brief: PCW gap-fill research (wave 1b)

The first harvest (752 items) and the card writers found gaps: things a writing job needs that PCW has no item for.
You harvest a fixed slice of them. Spec: `CONTRACT.md` sections "Kinds and ids", "Harvest file
format", "Rules for research workers", "Rules for every agent". Gap log: `work/gaps.jsonl`.

## Rules (same as the first harvest, plus)

- Your output file(s) and slice are named in your prompt. One file per kind (`"kind"` at the top), worker = your label.
- **Never duplicate an existing id or instrument.** Before adding an item, check: `python pcw.py ids
  <kind> <words>`. If the thing exists, skip it (or, if the existing item lacks the fact you found, list that in your
  hand-back instead of creating a second item).
- Primary sources first: the platform's help centre / developer docs, the regulator's or gazette's own text, the
  originator's own page or book. A fetch summary is paraphrase: for a number or rule, read the page and copy the
  source's own words into `quote` (platform limits) or the item `note` (law). Third-party only = low confidence, said so.
- Platform `limits[]`: field, max, unit, visible (only if the source states it), url, checked "2026-10-05", quote,
  confidence. A surface with no published limit can still be an item if the source documents its fields; then put
  the documented fields in `note` and give `limits` only what is published (an item needs >= 1 sourced limit; if none
  exists anywhere official, skip the item and say so in the hand-back).
- Law items: note = status and date as read ("in force since ...", "draft as of ..."), then the 2-5 rules a
  copywriter must remember, each tied to its source; no section numbers, penalties or dates from memory.
- Never bypass a CAPTCHA or a login. Blocked page -> say so, use the best secondary source labelled secondary.
- Web search works again (2026-10-05); still keep to the budget in your prompt.
- Scratch files only in `work/<your label>/`. Write your harvest file early (first items within
  ~12 minutes), then extend.
- Validate: `python pcw.py validate <your file(s)>` until "OK: 0 issues", then
  `python pcw.py dupes` must show no new collision involving your ids.

Hand-back (plain text, short): items harvested, items skipped as already present, items unreachable and why.
