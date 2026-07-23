# README Self-Contained Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `README.md` sufficient for a zero-context human or mainstream coding model to understand the catalog, translate a user prompt into Skill candidates, inspect compatibility, and recover authoritative source/download links.

**Architecture:** Keep the guide self-contained in `README.md`; point to `reports/overall-catalog.jsonl` as the query index and to leaf-level `skill-atlas.json` plus `SKILL.md` as authoritative per-Skill records. Document a deterministic retrieval funnel instead of implying that the current heuristic tags alone are final recommendations.

**Tech Stack:** Markdown, JSON Lines, `jq`, `rg`, POSIX shell examples.

## Global Constraints

- Do not modify upstream `SKILL.md` or any downloaded bundle content.
- Do not claim that all archived Skills are Codex-compatible or security-audited.
- Distinguish catalog classification risk cues from actual security review.
- Use commands that can be executed from the repository root.
- Treat `skill-atlas.json` provenance as the source of download/view links.
- Keep unstable registry API endpoints out of the public contract; use ClawHub canonical pages plus pinned owner, slug, and version.

---

### Task 1: Expand the self-contained repository guide

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: `config/taxonomy.json`, `reports/overall-catalog.jsonl`, leaf `skill-atlas.json`, leaf `SKILL.md`
- Produces: a single README workflow for humans and models

- [ ] **Step 1: Document the repository map and path semantics**

Add top-level directory responsibilities, GitHub and ClawHub leaf layouts, `_encoded-m-*` decoding rules, and the distinction between primary-category placement and cross-category tags.

- [ ] **Step 2: Document metadata fields and limitations**

Describe `provenance`, `classification`, and `integrity`; include tag coverage, `needs_review`, and the difference between `risk_level` and a security verdict.

- [ ] **Step 3: Add executable retrieval commands**

Include commands for keyword search, tag filters, source filters, minimal Codex frontmatter filtering, candidate inspection, and source-link extraction.

- [ ] **Step 4: Add the model retrieval protocol**

Specify the mandatory sequence: parse prompt, build tag hypotheses, query broad candidates, rerank by `SKILL.md`, inspect dependencies and risks, report evidence, and never auto-run upstream scripts.

- [ ] **Step 5: Add download and installation guidance**

Document GitHub repository/tree/archive link construction, ClawHub canonical URL extraction, local bundle packaging, and selective Codex installation by symlink.

### Task 2: Verify the README as an executable contract

**Files:**
- Verify: `README.md`
- Verify: `reports/overall-catalog.jsonl`
- Verify: sampled leaf `skill-atlas.json` and `SKILL.md`

**Interfaces:**
- Consumes: all shell snippets and field names documented in `README.md`
- Produces: evidence that the guide is internally consistent and runnable

- [ ] **Step 1: Run every catalog query class**

Run one keyword search, one multi-tag query, one source filter, one Codex-structure filter, and one provenance-link extraction. Expected: exit code `0` and at least one result for each positive example.

- [ ] **Step 2: Validate documented counts and JSON fields**

Run:

```bash
wc -l reports/overall-catalog.jsonl
jq -e 'has("catalog_path") and has("classification") and has("provenance") and has("integrity")' reports/overall-catalog.jsonl >/dev/null
```

Expected: `11839` records and exit code `0`.

- [ ] **Step 3: Perform a zero-context completeness audit**

Check that README alone answers: what the repository contains; where authoritative content lives; how paths map to sources; how tags are used; how candidates are filtered; how compatibility is checked; how source/download links are obtained; what must not be assumed; and how a model reports its recommendation.

- [ ] **Step 4: Check Markdown and command placeholders**

Search for unresolved `TODO`, `TBD`, unexplained placeholders, stale counts, and commands that depend on undocumented variables. Expected: no unresolved documentation placeholders.
