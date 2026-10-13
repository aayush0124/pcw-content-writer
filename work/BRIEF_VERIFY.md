# Brief: PCW verify wave (writer and judge)

PVE proves an effect card by rendering it; PCW proves a writing card by writing from it. A card passes when a
writer who reads ONLY the card's guidance produces a piece a senior human professional would sign off, and an
independent judge agrees. Spec: `CONTRACT.md`, sections "Gallery file format" and "Verification".
Your role (writer or judge), batch name and label are in your prompt. Scratch files go in
`work/<your label>/` only.

## Writer

For every card in `cards/<batch>.json`:

- **genre**: run `python pcw.py brief --genre <id>` and write the piece the card's
  `exemplar_brief` asks for, following the brief. Use only what the brief gives you plus the facts the exemplar brief
  states; invent no statistics, clients or quotes beyond the brief (placeholders like `[client result: 30% fewer
  notices]` are allowed when the piece needs a proof point the brief does not supply, and must look like placeholders).
- **hook**: write 5 hooks for the topic `TOPICS[n % 8]` below (n = the card's position in the batch, from 0), each
  from one of the card's `templates`, and name the template used after each hook. At least one in Hinglish.
- **framework**: write a 150-250 word piece for `TOPICS[n % 8]` that follows the card's `steps` in order, with each
  step labelled in square brackets at the start of its part, e.g. `[Problem]`. For results-heavy frameworks (case
  formats, postmortems, offer stacks) you may use figures clearly labelled "Illustrative", as the cards' own
  mini_examples do, so every step carries real copy.

Your notes for the lead (placeholders used, assumptions, facts to verify) go in a separate `writer_note` field of the
sample, never inside `brief` or `text`: the judge reads `brief` and must not see your reasoning.

Save each piece to `work/<label>/<slug>.txt`, run `python pcw.py check work/<label>/<slug>.txt
--genre <id>` (genre cards; add `--platform <id>` when the exemplar brief names a channel that has a platform card;
when the check says the platform has several fields, check each part of the piece (subject, headline, body ...)
from its own file with `--field "<field>"`) and fix every `[fail]` the piece itself causes. If a lint rule fails a piece that is correct for the brief, do not
bend the piece: keep it and write `"lint_suspect": "<rule>: why"` in the sample. Then append the sample to
`gallery/<batch>.json` = `{"samples": [{"id", "brief", "text", "check", "writer"}]}` (`check` = the
check output, `writer` = your label). Write the gallery file as you go, not at the end.

TOPICS = [
 "a Jaipur CA firm that handles GST notices for D2C brands",
 "a Pune cloud-kitchen brand launching a high-protein thali",
 "an AI tool that turns Hindi voice notes into meeting minutes",
 "a government scheme that gives rooftop-solar subsidies to households",
 "a 30-day English-speaking course for Tier-2 college students",
 "a Bengaluru B2B SaaS that automates invoice reconciliation",
 "a monsoon skincare range from an Ayurvedic D2C brand",
 "a Bihar civic story: a village that fixed its own road with a WhatsApp group"]

Hand-back: samples written, any card whose guidance you could not follow (and why), every `lint_suspect`.

## Judge

You did not write these pieces and you must not read the writer's notes or hand-back (skip any sample field
named `writer_note`; older samples may still carry a "Writer note:" inside `brief`: ignore that part). Read
`cards/<batch>.json` and `gallery/<batch>.json`. For each sample, judge the TEXT
against the card and the brief as a senior editor whose name goes on it:

| criterion | 0 | 1 | 2 |
|---|---|---|---|
| purpose | reader would not do the goal | might | clearly would |
| structure | ignores the card's structure / steps | partial | follows it, every part does its job |
| specificity | filler, generic | mixed | concrete throughout |
| voice | AI tells, wrong tone | some tells | human, right tone, natural Hinglish/Hindi where used |
| craft | weak hook, flat rhythm, weak CTA | ok | professional |

Total >= 8 = `pass`, 6-7 = `weak`, <= 5 = `wrong`. Be strict: a competent but forgettable piece is `weak`.
Two things are by design and are not penalised: (1) visible `[placeholders]` where the brief supplied no fact (the
writers may not invent statistics; judge specificity on everything else, and DO penalise a placeholder where the
brief or common sense supplied the fact); (2) for process / checklist frameworks (e.g. 4 Cs, 4 Us, positioning
templates, Feynman) a worksheet that ends in final copy is the right shape; judge `purpose` on that final copy.
Facts the writer added that the brief did not supply: if you know one is wrong, say so in the note (that is a
writer fault); do not reward or penalise correct public facts.
Then decide whose fault a weak/wrong result is: `card` (the card's guidance is missing, wrong or misleading: say
exactly which field to change and to what) or `writer` (the card was fine, the piece did not follow it).

Write into each card of `cards/<batch>.json` ONLY the `verified` field:
`{"verdict", "score", "sample": "gallery/<batch>.json#<id>", "note": "<what you saw; if card fault: CARD FIX: field -> change>",
"judge": "<your label>", "date": "2026-10-04"}`. Change nothing else in the card. Load the file, edit, write it back
once at the end, then run `python pcw.py validate cards/<batch>.json`.

Hand-back: counts per verdict, and the list of CARD FIX notes.
