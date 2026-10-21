---
name: pcw
description: PCW (professional content writer) - load before writing, rewriting, editing or critiquing ANY piece of written content - ad copy, sales page, VSL, email or cold email, landing page, UX microcopy, product description, blog or SEO article, white paper, case study, newsletter, press release, social post, caption, thread, carousel, YouTube or reel or podcast script, speech, proposal, resume, bio, SOP, story, poem, screenplay, satire, slogan, in English, Hindi or Hinglish. Also use when checking a draft against a platform's character limits, an ad/influencer/election law, or AI-writing tells. Pulls the genre's structure, frameworks, hooks, platform limits, tone, language rules, legal checks and 2026 trends from the verified PCW knowledge base, then lints the draft.
---

# PCW: professional content writer

PCW is a verified knowledge base (spec: `CONTRACT.md`, index: `PCW.md`). Every card was written from cited sources;
genre, framework and hook cards were also tested by writing a demo piece from them that an independent judge scored.
Use it the way an editor uses a style guide: read before writing, check after.

**Install:** set `PCW_HOME` to the folder that holds `pcw.py` (your clone of the repo), or replace `$PCW_HOME` below
with that path. Every command runs offline with the Python standard library.

## 1. Brief (before the first word)

```bash
python "$PCW_HOME/pcw.py" brief "<what you are writing, in plain words>"
```

Check the genre it picked (first line). If it is wrong, find the right one and pass it:
`python "$PCW_HOME/pcw.py" find "<words>" genre`, then
`python "$PCW_HOME/pcw.py" brief --genre <id> [--platform <id>] [--lang <id>] [--tone <id>]`.
Find other ids with `pcw.py find "<words>" platform|tone|language|compliance|hook|framework`.
Prefer cards whose verdict is `pass`; treat a `weak` card's note as a known gap.

If no genre card fits (`brief` exits 1 with a `No genre card matches` line, or the pick is plainly wrong), write
from the nearest one and append one line to `$PCW_HOME/work/gaps.jsonl`:
`{"date": "<YYYY-MM-DD>", "kind": "genre", "gap": "<the request>", "source": "nearest <id>"}` (the critic turns gaps
into new cards). Write it as UTF-8 JSON with double quotes (in Windows PowerShell 5.1 use
`Add-Content -Encoding utf8`, not `>>`, which writes UTF-16); `pcw.py validate` reports a line it cannot read. Same for a missing platform limit, law or language rule (`"kind": "platform"` etc.).

## 2. Voice owner

- If the brand or client has its own voice guide (a voice bible, a brand book, another skill that owns that page's
  voice), that guide owns the voice and the procedure; PCW supplies the genre craft, platform limits and legal checks.
  When they conflict, the voice guide wins.
- Otherwise the brief's tone card (or the client's stated voice) owns the voice.

## 3. Facts and law

A number, quote, claim or result enters the piece only from the user, a source you can cite, or the brief; anything
else is a visible placeholder (`[stat: source needed]`). Health, finance, political, influencer/affiliate, AI-generated
or comparative copy: read every `## Legal` checklist in the brief, the cards its `## Legal: also check` list points
to, and the matching `comp:` cards before writing.

## 4. Write

Follow the brief's structure in order. Draft at least 3 hooks / headlines / subject lines from the brief's hook
families and keep the strongest. Respect the platform limits and the "visible before truncation" window: the hook must
land inside it.

## 5. Check (pre-flight, mandatory)

1. Save the draft to a file and run
   `python "$PCW_HOME/pcw.py" check <draft.txt> --genre <id> [--platform <id>] [--field "<limit field>"]`.
   Fix every `[fail]`. Treat each `[warn]` (AI tells, dashes) as a fail unless the voice owner uses that pattern.
   The AI-vocabulary list is sense-blind: a word meant in its domain sense ("foster parents", "seamless pipes") may
   stay; say so in the deliver line.
   A platform with several fields (headline / description, subject / preheader, title / caption) is only enforced
   per field (a bare check warns that nothing was measured): save each part in its own file and check it with
   `--field "<the field's name>"` (the brief's `check:` line and the `[warn]` line list them; an exact name selects
   that field, other words match by substring, and words that fit several alternative surfaces ask for the full name).
   Limits the lint cannot measure (seconds, pixels, buttons) are checked by hand from the brief's Platform section.
   Exit 2 means the draft was not read (a wrong path, a folder, not UTF-8 text): fix the call, not the draft.
2. English drafts: a final pass for AI-writing tells (a humanizer skill if you have one; the method is the
   `edit:ai_tell_removal` card).
3. Re-read the brief's checklist and answer every item yes, or fix the piece.

## 6. Deliver

The piece first. Then at most three lines: genre / framework / hook used, any `[warn]` kept and why, any legal note
the user must act on (a disclosure label, a claim that needs substantiation).
