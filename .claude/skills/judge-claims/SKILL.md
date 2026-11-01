---
name: judge-claims
description: How to judge claim filings in the motif index (the 🎯 claims to judge, ✅ check queue, 🔁 second look, ⏸ held, today tab, proposals) with the attention the person expects. Use whenever reviewing, filing, checking, unfiling or splitting claims, or drafting a slate of verdicts for the person.
---

# Judging claims

## The one rule: very close attention, on every claim, every run

Everything below follows from this. Each claim gets your full attention, every time: the fiftieth claim of a long
queue as much as the first, and today's run as much as the first run of a session. Close attention means reading
every source line by line, reading the motif's note against what the tellers actually said, and thinking about what
this particular telling is doing before deciding anything. When you notice yourself speeding up, matching on names,
or clearing claims because the last few were alike, stop and go back. A queue is never cleared by going faster. If it
is too big to read closely, split the reading (mode 2 below); never read it less closely.

The person has seen what happens without it: about a thousand claims cleared in a day at one line each, with weak
fits they then had to find. With close attention the judgments are as good as theirs. Without it they are not worth
making.

## Why

The person's edge is a folklorist's reading of claims, and their attention is the scarce thing. A judgment is useful
only if it is as careful as theirs. A fast clear that is wrong costs them more than a slow one that is right, because
they have to find and fix it. Tokens are not the constraint; attention is. A judgment made from the claim's wording
and a motif's name alone is not a judgment.

The rules behind each step are in `docs/motif-praxis.md` (working rules, genres, notes, names, seeds) and
`docs/claim-praxis-draft.md` (what a claim is, by source). Earlier rulings, with their claims and reasons, are in the
casebook, `~/maudlin-data/motifs/casebook.md`, which is private and stays out of the repo. Read the parts that bear on
the claims at hand before judging, and the casebook entries for any motif you are unsure of.

## For every claim

1. **Read every source in full.** Use `claim_detail` or `claim_details` (up to 15 at once): the posts, transcript
   lines, fact-check or focus-group quotes. Check who is speaking. Focus-group and radio quotes are often the host or
   a clip being played.
2. **Read each motif's note and its not-this line** (`motif`) before deciding whether the claim fits. Never pass a
   filing because the name sounds right.
3. **Ask what shape the telling has before testing the motifs that exist.** Name the shape in your own words, then
   look for the motif that carries it (`motif_search`). Take-outs, "no motif" and weak fits often hide a shape no
   motif carries yet. Seeds are cheap: propose one (name, genre, note, groups) rather than force a near fit.
4. **File the telling, not the why.** File what the tellers say, never a reading of why the story circulates. The
   shape must be in what is told: in the details the telling chooses, its framing, or the reactions it draws. Quote
   the teller's words that carry each filing. Straight news gets no motif, and that is fine.
5. **Motifs are stance-neutral.** A teller who embraces the shape tells the same motif as one who condemns it. Stances
   that answer each other are a counter pair, not grounds to unfile.
6. **Check the claim's own words.** Reword (`correct`) a gloss that takes a side, carries the fact-check's verdict, or
   hides the part a motif is filed for. Word allegations to what the tellings establish ("accused", "says"). Leave
   tellers' politics out of the claim.
7. **Split disputes.** A claim worded as a dispute ("Arguments exist over whether…", "Debates persist…") is split
   with `split {claim, children}`, one child per side, each in that side's voice from the posts. When only one side
   is really told, reword it instead.
8. **Say every motif the claim carries.** Kept, added and new, not just the one under review.
9. **No topic gets special handling.** File politically charged claims like any other. Hold nothing back and add no
   flags because of the subject.

### Held claims

A claim the person put on hold usually means they think it needs a new motif. Look for the missing shape first and
propose a seed for it. Keep the existing filing too if it fits. Clear a person-held claim with no new motif only when
nothing new is there, and say so in its row.

### Genre calls, when a new motif needs one

- **Plot** is what happened.
- **Theory** is what people think about it, but only when the reading goes beyond the surface: a hidden cause, agent
  or mechanism.
- **Belief** is a premise people reason from.
- **Argument** is a rhetorical move people actually make.
- **Archetype** is a kind of person the tellers portray.

Reason each call in one line. The full casebook of calls is in `docs/motif-praxis.md` under Genres.

## Two modes

The person picks the mode. **Mode 1, slates:** they read slates and approve. **Mode 2, agents:** the session clears
the queue itself with subagents, applies the verdicts, and reports, and the person corrects afterwards. They pick
mode 2 when too many claims are coming in for them to read; words like "do it all", "clear it" or "use agents" mean
mode 2. If the request doesn't say, use mode 1. A mode holds for the clear it was given for; the next clear starts
from what the person asks then.

The reading is the same in both modes: every claim gets the full read above. Mode 2 changes who approves, and when.
It doesn't change how closely anyone reads.

### Mode 1: slates

- **Ten claims per slate.**
- **Decide every row yourself**, the close ones too: ✅ keep, ❌ take out, ➕ add, or a new motif proposed outright.
- **No questions anywhere in the slate.** Not "…too?", not "your call", not "X or Y?". Put uncertainty in the row as
  "Doubt: …", with the teller's words.
- **Raise every doubt, and only real ones.** A doubt is about a filing you are making or keeping that could be wrong.
  Don't surface shapes or motifs you are not filing. Don't force a doubt where nothing is uncertain; an empty cell is
  fine. Doubts belong to the job the slate is doing: a slate rewriting notes carries notes only. Misfilings you
  notice along the way go into a separate list for later.
- **Show all the motifs each claim ends up in.**
- End with one line saying everything not flagged was read and judged sound, and what "take it" applies. Only write
  that line if it is true: every claim in the slate had its sources read in full.

After the person corrects a slate, apply it at once. Their corrections plus silence on the other rows is the
go-ahead. Never re-table the slate. Report only the new motifs' ids, anything that came out differently from what
they read, and answers to their questions. Never read a reply to a later message as approval of a slate they haven't
said they've read.

### Mode 2: agents clear the queue

1. **Take the whole queue.** Page through `claims_to_judge` (or the queue named) with `offset` until it is empty,
   and note how many claims there are.
2. **Split it into packets of about ten claims.** Keep claims about the same story or motif in one packet, so one
   reader sees them together. Send packets to read-only subagents in parallel, several at a time.
3. **Brief each subagent fully.** It has none of this conversation. Tell it to:
   - read this file (`.claude/skills/judge-claims/SKILL.md`), `docs/motif-praxis.md` and the casebook first;
   - give every claim the full read: sources via `claim_details`, each motif's note and not-this line;
   - never call `checker_action`;
   - return, for each claim, a verdict per filing (keep, take out with a one-line why, add, move), every motif the
     claim ends up in, the teller's words carrying each filing, any split or rewording with its new words, any seed
     proposed (name, genre, note, groups, the claims it takes), and its real doubts.
4. **A second, independent reader for every packet.** It judges each claim from the sources first, then compares
   with the first reader's draft and lists every difference, quoting the sources. Run it as a workflow (read, then
   check, pipelined per packet), with the drafts and packets saved in `~/Repos/maudlin-notes/judging/`.
5. **Check before writing anything.** Read the sources yourself (`claim_details`, 15 at a time) for every claim
   where the readers differ, and for every take-out, new motif, split, rewording and doubt, even where they agree.
   Where you disagree, your reading decides. A keep both readers agree on, with the tellers' words quoted, passes.
   Merge seeds that different packets proposed for the same shape into one, and check that no existing motif already
   carries it (`motif_search`).
6. **Work in waves of about a hundred claims** when the queue is large. Apply and report each wave as it finishes,
   so the person can correct while the next wave reads.
7. **Apply in batches** through `checker_action`: one batch per packet, `why` on every take-out, seeds made with
   `new_with` and given their note, genre and groups in the same batch.
8. **Report each wave for correction after the fact:**
   - how many claims were judged, and how many filings were kept, taken out, added and moved;
   - the new motifs with their real ids (looked up);
   - one row for each claim with a doubt, the doubt in its row with the teller's words;
   - the splits and rewordings;
   - one line saying every other claim was read in full by two readers who agreed.

   No questions in the report. The person corrects what's wrong; apply the corrections at once (with `why` on
   take-outs) and report only what changed.

If the queue is small enough to read closely yourself, mode 2 can skip the subagents. Everything else stays the same.

## Applying changes

- Use `checker_action`, and only for changes the person asked for: an approved slate in mode 1, or the clear they
  handed over in mode 2.
- Every take-out of a model filing (`check` no, `unfile`, `move`, a rejected proposal) carries `why`: the reason from
  the approved row, or the person's words, tidied for capitals, spelling and grammar. Don't put `why` on your own
  additions.
- Put related changes in one `batch`. Name motifs made earlier in the batch as `$1`, `$2`, counted from the start of
  the batch. After the batch, look up a new motif's real id before acting on it again. Never guess the next id.
- Notes describe the general shape. They never name the one story where the motif was found.
- Never test the checker by doing and undoing on the live one (port 8766). Its undo stack is shared with the person.

## Out of scope

Model work (experiment scripts, filing models, GPU runs) belongs to other sessions. When judging turns up a fix for a
model, write it down as a proposal for the person; don't edit or run anything.
