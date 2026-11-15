# Contributing to dav2d: what reviewers have asked for

Distilled from the review comments on our dav2d MRs and issues (full overview with quotes and links in `2026-11-15-dav2d-review-overview.md`). These are the preferences of a small group of maintainers, not laws: use judgement, and when a reviewer asks for something else, follow the reviewer. Add to this file when a review point comes up a second time.

## Code

- Write code the way the dav2d authors would, not the smallest diff that matches AVM. Before pushing, reread the surrounding function: reuse locals already in scope, keep its units, fold into an existing branch rather than adding one, use `assert()` for impossible cases, put shared logic in the caller, move a function rather than forward-declare it. Style: [dav1d coding style](https://code.videolan.org/videolan/dav1d/-/wikis/coding-style).
- Code comments: none by default. The why goes in the commit message and MR description. A comment is for a fact the code can't show, one short line. Check the diff for added `//` and `/*` before pushing; this was the most repeated review point.
- Match AVM's output, not its structure. Per-block branches for a rare case get pushed back: prefer frame-level setup, and removing stale AV1 leftovers over guarding them.

## Shape of contributions

- One fix per MR. A fix goes in an MR, not as a patch attached to an issue.
- For partly implemented features or areas maintainers are reworking, propose a design or ask before writing the code, and check their open MRs and WIP branches first. Closing ours in favour of theirs is fine.
- Before fixing a known issue, read its whole thread and linked MRs.
- Issues need an action: a bug with a public repro. Analyses the maintainers already know don't help as issues.
- Small public repros and regression samples for dav2d-test-data are welcome; testing maintainers' MRs on our corpus is appreciated.

## Claims and text

- Scope every claim to what was run: which streams, which builds (asm/C), which threading modes. "No output change" needs the streams the MR is about plus our wider corpus; a sanitizer claim needs the CI job's config.
- Write so a domain expert can check the reasoning without trusting the tool: AVM function names, the condition that differs, a repro. Keep replies short and specific.
- No AI attribution or mention anywhere on VideoLAN (VideoLAN AI policy). What costs goodwill is AI-flavoured output (explanatory comments, verbose text) and patches nobody can explain.
