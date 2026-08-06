# Architecture Decision Register

Index of decisions that outlive the conversation that produced them. A decision
recorded only in a chat log or a terminal pane gets re-litigated next month; this
register is where it stops being oral tradition.

**Scope.** Durable, project-wide rulings — what was decided, why, and what it
costs. Situational or personal working notes belong in `.notes/`; step-by-step
work belongs in `docs/design-plans/` and `docs/implementation-plans/`.

**Adding one.** Next free number, `NNNN-kebab-slug.md`, and a row here in the
same commit. Status is `Proposed`, `Accepted`, `Superseded by NNNN`, or
`Reversed`. Never edit an accepted decision's substance — supersede it with a new
record and mark the old one.

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-shelve-wargame-retain-tables.md) | Shelve the wargame feature, retain its tables | Accepted | 2026-08-06 |
| [0002](0002-expunge-browserstack.md) | Expunge BrowserStack rather than keep it quarantined | Accepted | 2026-08-06 |
