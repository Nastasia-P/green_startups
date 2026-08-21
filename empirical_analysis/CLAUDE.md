# CLAUDE.md — Chapter 4 Empirical Analysis

## Project Context

ESADE MIM thesis: *Green Start-ups in Europe: An Empirical Analysis of Their Geographic and Funding Patterns*. Chapter 4 produces the geography and funding results over a fixed population of 116,005 European start-ups (8,306 green / 107,699 other).

## Authoritative Documents

Read these before writing any code or spec. If they disagree, the higher entry wins.

| Priority | Document | Role |
|----------|----------|------|
| 1 | `Empirical_Analysis_Specification.md` | Authoritative. Every variable, source table, filter, formula |
| 2 | `HANDOVER.md` | Scope, conventions, acceptance criteria, phase plan |
| 3 | `Output_Register.md` | Every table and figure, with columns, rows and source variables |
| — | `Why_This_Design.md` | Plain-language rationale for every rule |

## Spec Layout

Task specs live in `empirical_analysis/specs/<task_id>/`, following the layered structure below:

```
empirical_analysis/
├── CLAUDE.md                 # this file — project + workflow guide
└── specs/
    └── <task_id>/            # e.g. T4_0
        ├── CLAUDE.md         # feature-level instructions
        ├── design.md         # source of truth for the task
        ├── decisions.md      # resolved ambiguities
        └── implementation.md # progress tracker
```

## Code Locations (when implementation begins)

Planned pipeline root is `07_Final Python/chapter4/` per `HANDOVER.md` §4.1 (`src/p0_base_tables.py` … `p5_verify.py`). No reported number originates in a notebook.

## Output Naming

Outputs are named by register ID with a **zero-padded two-digit** number: `T4_00_field_completeness.csv`, `T4_09_funding_access.csv`, `F4_03_lq_by_country.pdf`. Every output table carries its own `n` column.

## Non-Negotiable Rules (see HANDOVER §5)

- **N1** Funding **amount** comparisons run only within the financed subsample; missing funding is *unobserved*, never *zero*.
- **N2** `financed` = ≥1 completed qualifying deal record, never `total_raised > 0`.
- **N10** Output labels use **"Green start-ups"** and **"Other European start-ups"**, never "non-green".
- **M3** The T4.0 coverage audit appears in the thesis main text, not hidden in an appendix.

## Don't

- Don't add analysis not defined in an authoritative document; raise it instead.
- Don't treat missing funding as zero, or fold Accelerator/Incubator into VC or seed.
- Don't resolve the reserved author decisions (HANDOVER §7) silently.

---

# Claude Code Workflow Guide for AMD Engineers

A practical guide to using Claude Code effectively for spec-first development.

## The Shift in How We Work

When using Claude Code, the developer role changes from writing code to orchestrating it. Claude handles implementation, testing, and documentation. You define **what** to build and **why**. Claude handles **how**.

| Before | After |
|--------|-------|
| Designs in Docx | Designs in Markdown (in repo) |
| Humans write code | Claude writes code |
| Humans write tests | Claude writes tests |
| Humans review code | Claude reviews, human approves |
| Context scattered | Context lives in code |

---

## Spec-First Development

To use Claude Code well, you need to give it the right context. This means keeping design documents **in the repository** where Claude can read them.

### Recommended Structure

Create a `specs/` directory in your repository:

```
your-repo/
├── specs/
│   └── feature-name/
│       ├── CLAUDE.md          # Instructions for Claude Code
│       ├── design.md          # Design spec (source of truth)
│       ├── implementation.md  # What's done, what's in progress
│       ├── decisions.md       # Why decisions were made
│       ├── prompts.md         # Stored prompts you reuse
│       └── future-work.md     # What's deferred
├── src/
├── tests/
└── CLAUDE.md                  # Root-level instructions
```

> **Note:** Keeping specs in-repo ensures they're protected by your repository's group permissions and access controls. This is preferable to private symlinked directories which bypass git protections.

### What Each File Does

| File | Purpose |
|------|---------|
| `design.md` | Source of truth. Claude and you align on details before development starts. No spec, no implementation. |
| `implementation.md` | Tracks progress - what's done, what's blocked. Claude updates this as you go. Crucial for session continuity when context limits are hit. |
| `decisions.md` | Captures the "why" behind choices. Helps future you (and Claude) understand trade-offs. |
| `prompts.md` | Stores reusable prompts for common tasks - syncing docs, reviewing, testing. |
| `future-work.md` | Captures deferred ideas worth revisiting. |

### Example Decision Record

```markdown
## ADR-003: Learning Modes (ALWAYS, AGENTIC, PROPOSE)

### Context
Different use cases need different learning behaviors.

### Options
1. Single mode — Always automatic
2. Per-store modes — Each store can operate differently

### Decision
Per-store LearningMode enum.

### Consequences
- Each store declares which modes it supports
- Invalid combinations fall back gracefully
```

---

## Layered CLAUDE.md Instructions

Claude Code reads `CLAUDE.md` files at multiple levels. Use this to your advantage.

### Root-Level CLAUDE.md

Place at the repository root. Tells Claude how to navigate the codebase:

```markdown
# CLAUDE.md — Project Name

## Code Locations
| What | Where |
|------|-------|
| Core logic | src/core/ |
| API handlers | src/api/ |
| Tests | tests/ |

## Design Documents
The specs/ folder contains design documents. Always check here first.

## Don't
- Don't implement features without checking for a design doc
- Don't skip tests for new functionality
```

### Feature-Level CLAUDE.md

Place inside each `specs/feature-name/` directory:

```markdown
# CLAUDE.md — Feature Name

## Project Context
Brief description of what this feature does.

## Before Starting Work
1. Read specs/feature-name/design.md
2. Check specs/feature-name/implementation.md
3. Look at existing code for patterns

## Code Patterns
- All handlers implement the BaseHandler protocol
- Use existing_module.py as the reference implementation

## Don't
- Don't add features not in design.md
- Don't break existing interfaces
```

When Claude opens your repo, it reads both instruction sets automatically.

---

## The Workflow

Here's how a feature gets built:

1. **Define the feature** - Write or dictate a rough description of what you need
2. **Claude writes the design** - Claude reviews codebase and `specs/`, then drafts `design.md`
3. **You review** - This is where most of your brainpower goes. Refine the design.
4. **Implement in small pieces** - Ask Claude to implement one specific piece at a time
5. **Tests and examples** - Claude writes tests alongside implementation
6. **Review and iterate** - Review output, ask Claude to test and improve
7. **Update tracking** - Claude updates `implementation.md`
8. **Repeat** - Move to the next piece

### The Most Important Rule

**Every PR must be reviewable in under 10 minutes.**

Add this to your root `CLAUDE.md`:

```markdown
## The Most Important Rule
**Every PR must be reviewable in under 10 minutes.**

This means:
- Max 5-7 files changed (excluding tests)
- Max 500 lines changed
- One focused change per PR
- Clear review checklist in PR description

If your change is bigger, **split it into multiple PRs**.
```

---

## Plan Mode: Use It

**Shift + Tab** activates Plan Mode in Claude Code.

For complex codebases, jumping straight into implementation produces poor results. Front-load information instead:

- Architecture decisions
- Edge cases
- Constraints
- Dependencies

Five minutes of planning can save hours of iteration.

---

## Context Management

Claude's context window degrades around 30% utilization. Best practices:

- **One conversation per feature** - Don't mix unrelated work
- **External memory via spec files** - `implementation.md` tracks state between sessions
- **Clear context when needed** - Start fresh when context gets polluted

When you hit context limits and restart, Claude reads `implementation.md` and picks up where it left off.

---

## Quick Reference

| Practice | Why |
|----------|-----|
| Keep specs in repo | Protected by git permissions, visible to Claude |
| CLAUDE.md at two levels | Root for codebase, feature for specific work |
| Save your prompts | Common tasks become copy-paste |
| Tests for everything | If it doesn't run, it's not done |
| Small PRs only | Reviewable in 10 minutes or less |
| Use Plan Mode | Front-load context before implementation |

---

## Getting Started

1. Create a `specs/` directory in your repository
2. Add a root-level `CLAUDE.md` with code locations and conventions
3. For your first feature, create `specs/feature-name/` with at least `design.md`
4. Open Claude Code, activate Plan Mode (Shift+Tab), and start with: "Read specs/feature-name/design.md and propose an implementation plan"

Claude writes the code. You review and approve. That's the workflow.
