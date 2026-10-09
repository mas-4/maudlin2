# Commit style

How commit messages read in this repo, from Oct 9 2026 on. (Before that, subjects ran to a median 263 characters;
don't copy them.)

## The subject line

- **One line, at most 72 characters.** What changed, not the story of why.
- **Imperative, sentence case, no period:** "Order the check list least sure first", not "The check list goes least
  sure first." or "ordered check list".
- **A scope prefix when it helps you scan:** `filing:`, `worker:`, `checker:`, `site:`, `experiments:`, `docs:`,
  `transcribe:`, `proposals:`, `ops:`. Lower case, then the subject.
- **No quotes from conversations, no "(the person: ...)", no dates, no commit hashes.**

Good:

    filing: use Nimble 9B as the confidence model's judge
    worker: yield to experiments holding the GPU lease
    site: show the top stories three to a row
    experiments: add J1, a jury of models on decided filings

## The body (when it's needed)

Leave a blank line after the subject, then wrap at 72 characters. Say **why**, and anything the diff can't show:

- the measurement that justified it ("AUC 0.824 vs 0.818 on 817 decided filings");
- what breaks, migrates or needs a manual step (a service to install, a cache to warm);
- what was tried and dropped, in a line.

Short paragraphs or `-` bullets. Leave out what the diff already says (file names, function names, every
constant), the back-and-forth that led to it, and adjectives.

    filing: use Nimble 9B as the confidence model's judge

    Nimble judged the 817 decided filings as well as Gemma 26B
    (AUC 0.824 vs 0.818 alone, 0.895 vs 0.894 in the model) at
    0.22 s a pair, and fits the card whole. The confidence model
    retrains on Nimble's answers before scoring again.

## One change per commit

A commit does one thing. If the subject needs an "and", it's probably two commits. Docs that describe a change go
in the same commit; a results write-up of experiments can be its own `docs:` commit.

## The trailer

End with the co-author line the session asks for, after a blank line.
