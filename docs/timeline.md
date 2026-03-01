# Session 1 2026 — Week-by-Week Timeline

*Last updated: 2026-02-28*

Session 1 runs 13 teaching weeks from 24 February. PromptGrimoire is used across multiple units for the full session. Tool is introduced to classes in Week 2 (3 Mar).

## Week 1 — Pre-Launch (24 Feb)

Session started. No classes using the tool yet. Final MVP push.

- [x] MVP: annotation platform, workspace navigator, sharing, tags, PDF export, copy protection
- [ ] **Deploy to production** at `grimoire.drbbs.org` (target: Monday 3 Mar 9am)
- [ ] LLM Playground prototype (aspirational: 1 Mar)

## Week 2 — Introduced to Classes + LLM Playground (3 Mar)

**Students hit the tool.** Annotation platform is live. Expect breakage. LLM Playground is the feature priority.

| Priority | Item | Issue |
|----------|------|-------|
| P0 | Monitor production, hotfix critical bugs | — |
| P0 | LLM Playground: core chat interface | #151 |
| P0 | OpenRouter + ChatCraft platform handlers | #209 |
| P1 | Paragraph numbers on annotation cards | #191 |
| P1 | Perf: debounce CRDT persistence | #139 |
| P1 | Perf: incremental annotation card add | #140 |

**Milestone: 6 Mar — Testing** (post-launch polish)

## Week 3 — Roleplay + Stabilise (10 Mar)

Roleplay / client interview simulation is the feature priority. First full week of student use on annotation — bug reports come in, performance under real load becomes visible.

| Priority | Item | Issue |
|----------|------|-------|
| P0 | Roleplay: persist sessions to database | #36 |
| P0 | Roleplay: log viewer pagination | #37 |
| P1 | Annotation card overlap fix | #80 |
| P1 | AustLII document extraction | #115 |
| P1 | File upload: HTML, PDF, RTF, DOCX | #109 |
| P2 | PDF export: URL line breaking | #110 |
| P2 | Lua filter selection fix | #135 |

**Milestone: 13 Mar — Post-MVP** (extended polish)

## Week 4 — Stabilise + Polish (17 Mar)

| Priority | Item | Issue |
|----------|------|-------|
| P1 | Drag-scroll zones on Organise tab | #128 |
| P1 | Case Brief Tool: word count limits | #47 |
| P1 | Document switcher for multi-doc workspaces | #186 |
| P2 | Copy protection: drag-and-drop | #163 |

## Week 5 — Documentation & Onboarding (24 Mar)

| Priority | Item | Issue |
|----------|------|-------|
| P1 | MkDocs documentation platform | #208 |
| P2 | Browser back button navigation | #124 |
| P2 | Next/Previous tab navigation | #125 |

## Week 6 — Refinement (31 Mar)

Mid-session checkpoint. Prioritise based on student feedback from Weeks 2–5.

| Priority | Item | Issue |
|----------|------|-------|
| P2 | Move annotation header to nav drawer | #202 |
| P2 | Remote cursor sync | #149 |
| P2 | Margin note alignment | #89 |
| P3 | Extract paste handler JS to static file | #167 |

## Weeks 7–8 — Mid-Session Break / Buffer (7–18 Apr)

Use break weeks to:
- Address accumulated bug reports
- Performance profiling under real data (load tests: #68)
- Refactoring: extract shared DOM walk (#131), select_text_range rewrite (#154)
- SQL consistency cleanup (#205)

## Week 9 — Case Brief Tool (21 Apr)

| Priority | Item | Issue |
|----------|------|-------|
| P2 | AGLC4 citation support | #52 |
| P2 | Click-to-insert paragraph references | #51 |
| P2 | Secondary source database | #53 |

## Week 10 — Access Control Polish (28 Apr)

| Priority | Item | Issue |
|----------|------|-------|
| P2 | Commenter permission level | #166 |
| P2 | Session revocation (boot user) | #102 |
| P2 | Condition-based E2E waits (replace timeouts) | #206 |

## Weeks 11–12 — Presentation & UX (5–16 May)

| Priority | Item | Issue |
|----------|------|-------|
| P2 | Fullscreen presentation view | #25 |
| P2 | Instructor presentation controls | #26 |
| P2 | Multi-user collaboration E2E test | #107 |
| P3 | Named database constraints guard | #169 |
| P3 | E2E: WebSocket revocation push | #171 |

## Week 13 — Hardening + Session End (19 May)

- Feature freeze
- NiceGUI User fixture test tier (#175)
- Input pipeline: AustLII margin-left (#179)
- NiceGUI upgrade evaluation (#180)
- Final bug fixes only
- Post-session retrospective
- Plan Session 2 priorities

---

## Unscheduled / As-Needed

| Item | Issue |
|------|-------|
| Course analytics dashboard | #198 |
| SQLModel session.execute() deprecation audit | #199 |
| E2E text walker timeout | #184 |
| Export fixture cleanup | #147 |
| Highlight range regression test | #146 |
| Copy protection: toast deduplication | #162 |
