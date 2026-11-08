# DONNA memory contract (vault v0)

Rules for every note an agent writes into this vault. They come from DONNA's Memory spec
(Notion: Memory 01–08) as far as a Markdown vault can carry them. A git pre-commit hook
(`resources/donna/validate_notes.py`, values in `resources/donna/contract.yaml`) rejects
commits that break them. This file and those two are managed from `ai_stack_infra`
(`stacks/agents/cornelius/vault`); do not edit them here.

Status: **Knowledge Vault v0** (accepted 2026-11-07). Not the canonical CORE Memory Fabric.
Synthetic and public data only until the blockers in the reconciliation doc are closed.

## Frontmatter of a new note

Cornelius keeps its own keys (`type`, `status`, `tags`, `created`, …). DONNA adds `donna_*`
keys and requires Cornelius's `provenance` and `confidence`:

```yaml
---
title: Short claim in plain words
provenance: ai-inferred        # originated | endorsed | encountered | ai-inferred | reference
confidence: medium             # low | medium | high
donna_id: 6f1c2d0e-8a4b-4c7e-9d2f-1b3a5c7e9f01   # cat /proc/sys/kernel/random/uuid; never changes
donna_type: Lesson             # Fact Decision Experience Lesson Principle Preference Pattern
                               # Hypothesis Idea Outcome | Entity Reference Artifact Event
donna_kind: strategy           # optional: Decision -> strategy, Idea -> content_opportunity
donna_state: candidate         # candidate | curated
donna_scopes: [global]         # global | datonum | rb-home (one or more, no copies per scope)
donna_sources: ["https://example.com/article", "[[Other note]]", "paperclip:RBV-12"]
donna_task: RBV-12             # Paperclip issue that produced the note
donna_approved_via: RBV-14     # required for originated/endorsed and for curated
donna_valid_from: 2026-11-07   # optional: when it became true in the world
donna_valid_to:                # optional: when it stopped being true
donna_supersedes: []           # donna_id values this note replaces
donna_contradicts: []          # donna_id values this note conflicts with
---
```

`recorded_at` is the commit time; nobody sets it by hand.

## Rules

1. **Provenance.** `encountered` = external source (needs `donna_sources`). `ai-inferred` =
   the agent's own conclusion (needs the notes/sources it was derived from). `reference` =
   a record. `originated` = the operator's own thinking, `endorsed` = an external idea the
   operator adopted: both only with `donna_approved_via`.
2. **Operator's own words (decision D3).** When the operator writes a thought, decision or
   experience into a Paperclip task and asks to save it, the note is `provenance: originated`,
   with `donna_task` and `donna_approved_via` both set to that task. Only the operator's own
   text qualifies; anything the agent adds (summary, generalisation, links) goes into a separate
   `ai-inferred` note. Tasks created by agents never qualify.
3. **Types.** Pick `donna_type` by what the text is: "maybe / I'm considering" = Idea or
   Hypothesis; "I decided / we will" = Decision; "this worked / failed" = Experience or
   Outcome; "next time…" = Lesson. Do not upgrade a thought into a decision.
   One note holds one claim of one type: split mixed text ("X is my main business" = Fact,
   "I hope it brings most of the income" = Hypothesis). The operator's words are split only
   at sentence or clause boundaries, never reworded (instructions in the task, like the
   business or type to use, are metadata, not part of the quote); every part keeps `originated` and the
   same `donna_approved_via`, and the parts reference each other in `donna_sources`.
4. **State.** New notes are `candidate`. `curated` only after the operator approved that note
   (a Paperclip decision); set `donna_approved_via` to the issue where it was approved.
5. **No silent overwrite.** A curated note's text and keys are frozen (only `donna_valid_to`,
   `donna_superseded_by`, `donna_contradicted_by`, `updated`, `updated_by`, `tags` change).
   A correction is a new note with `donna_supersedes: [<old id>]`; then set the old note's
   `donna_superseded_by` and, if it stopped being true, `donna_valid_to`.
6. **Contradictions.** Never pick a winner. Write a note (usually `donna_type: Fact` or
   `Pattern`, `ai-inferred`) that states the conflict, with `donna_contradicts: [<id>, <id>]`,
   set `donna_contradicted_by` on both, and list it for the operator in the task.
7. **Scopes.** Every note names the business it belongs to (`datonum`, `rb-home`) or
   `global`. One note, several scopes if it applies to several; never copy a note per scope.
   Scopes are labels in vault v0, not access control: all of this vault is visible to the
   agents that can read it.
8. **Deletion.** Curated notes are not deleted; supersede them. A rejected candidate may be
   deleted.
9. **Secrets.** No credentials, keys or tokens in any file. The hook rejects them.
10. **Seed corpus.** The 1,067 shipped notes have no `donna_*` keys and stay as they are
    (external material). Give a seed note the DONNA frontmatter only when the operator asks
    to curate it.

## Search scope

Agents search with `BRAIN_READ_SCOPE=core,inbox` (decision D4): core folders plus
`00-Inbox`, so fresh candidates are found. Check `donna_state` before treating a hit as
approved knowledge.
