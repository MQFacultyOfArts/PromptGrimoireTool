# Case Brief Tool - UX Decisions

This document captures UX refinements from the Gemini review session (2026-01-23).

## Guiding Principle

**Productive Friction vs Unproductive Friction**

- **Productive**: Hiding the case document in Screen 3 forces synthesis
- **Unproductive**: Losing place, vague citations, navigation fatigue

## Screen 3 (Write) Sidebar Cards

### Visual Hierarchy

1. **Anchor**: Paragraph citation `[48]` is dominant (top-left, bold, high contrast)
2. **Text**: Truncated highlight text below citation
3. **Metadata**: Tag color strip on left edge

### Interactions

| Feature | Behavior |
|---------|----------|
| **Sorting** | LOCKED in Screen 3. Must return to Screen 2 to reorder. |
| **Search** | Fade filter: matching cards stay bright, non-matches fade to 30% opacity. Preserves spatial memory. |
| **Comments** | Bubble icon with count `[💬 2]`. Opens floating popover (not inline) to prevent list jumping. |

### Edit in Context Flow

1. Hover card → reveal pencil icon "Edit in Context"
2. Click → switches to Screen 1, auto-scrolls to highlight, flashes it
3. Screen 1 shows floating "Return to Brief" button
4. Click return → back to Screen 3, cursor position preserved (if feasible)

## Word Limit Enforcement

**Decision**: Soft limit with "snitch" badge

| Behavior | Details |
|----------|---------|
| Warning | Export modal shows: "You are X words over the limit" |
| Allow export | Yes - students can still download |
| PDF output | Red box on page 1: `Word Count: 650 / 500 (Exceeded)` |

**Rationale**: Accountability without gatekeeping. Instructors see violations immediately. No support tickets about blocked exports.

**Future option**: Make hard/soft limit configurable per case.

## Screen 1 (Annotate)

### Tag Toolbar

- Keep flat list (no groupings for MVP)
- Future consideration: visual clusters for Context/Facts/Law/Analysis/Outcome/Student

### Paragraph Feedback

- Immediately show detected `[48]` on new card
- If detection fails, show `[?]` to prompt user to check document structure

## Animations

| Event | Animation |
|-------|-----------|
| Card added by other user | Fade in + slide down (0.3s) |
| Card reorder (Screen 2) | Smooth shuffle via CSS transitions |
| Search filter | Opacity fade (0.2s) |

**Implementation**: Use CSS `@keyframes` and `transition`. Avoid delete/recreate patterns that cause flash.

## Decisions NOT Implemented (Deferred)

1. **Tag grouping in toolbar** - keep simple for MVP
2. **Click-to-insert paragraph refs** - Phase 2
3. **Hard word limit option** - may add later as per-case toggle

## Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| Paragraph numbers on cards | ✅ Done | Shows `[N]` or `[N–M]` for spans |
| Remote card fade-in | ✅ Done | CSS animation class |
| Floating tag menu | ❌ Removed | Was broken, toolbar sufficient |
| Popover comments | 🔲 Pending | Currently inline |
| Search with fade | 🔲 Pending | Screen 3 feature |
| Edit in Context flow | 🔲 Pending | Screen navigation feature |
| Soft limit snitch badge | 🔲 Pending | PDF export feature |
