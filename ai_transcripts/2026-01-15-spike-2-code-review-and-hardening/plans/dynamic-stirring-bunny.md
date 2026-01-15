# Plan: Create GitHub Issues and CLAUDE.md

## Overview
Set up project tracking via GitHub issues and create a CLAUDE.md file to give Claude context on this AI literacy training project.

## GitHub Issues to Create

### Milestone: Module 1 Content Draft (Due: 30 Jan 2026)

**Issue 1: Learning Design & Section Structure**
- Assignees: Brian, Jodie
- Due: 17 Jan 2026 (end of this week)
- Tasks:
  - [ ] Map Marzano-style learning objectives to each 5-min section
  - [ ] Define the 4-part structure with clear section boundaries
  - [ ] Align with TLH framework
  - [ ] Send draft to Maryam by Friday 16 Jan

**Issue 2: Audit Existing Materials**
- Assignees: Brian, Jodie
- Due: 24 Jan 2026
- Tasks:
  - [ ] Inventory Brian's teaching materials
  - [ ] Inventory Jodie's TLH materials (videos, activities, quizzes)
  - [ ] Map existing content to module sections
  - [ ] Identify gaps requiring new content

**Issue 3: Content Draft - Core 30-min Module**
- Assignees: Brian, Jodie
- Due: 30 Jan 2026
- Tasks:
  - [ ] Introduction (Mindset around AI) - ~5 min
  - [ ] How LLMs work (hallucination, accountability) - ~5-10 min
  - [ ] Introducing ChatMQ (data protection, AU vs overseas) - ~5-10 min
  - [ ] Exploring ChatMQ (hands-on, what data can/cannot upload) - ~5-10 min
  - [ ] Accountability for AI-generated outputs - ~5 min

**Issue 4: Content Draft - Academic/Research Extensions**
- Assignees: Brian, Jodie
- Due: 30 Jan 2026
- Tasks:
  - [ ] Research path (15 min) - Ethics checklist walkthrough
  - [ ] Teaching & Learning path (15 min) - Lesson planning, assessment design, resources

**Issue 5: Update Project Plan Document**
- Assignees: Brian, Jodie
- Due: Week of 20 Jan 2026
- Tasks:
  - [ ] Incorporate learning design into project plan
  - [ ] Confirm dates with Maryam after Friday review

---

## CLAUDE.md Content

```markdown
# AI Literacy Training - Phase 1

## Project Overview
Developing Module 1: "Driver's Licence for Responsible AI Use" - a 30-45 minute compliance module enabling Macquarie University staff to access ChatMQ advanced features.

**Collaboration:** Central AI (CIO-IT) + Faculty of Arts Humanities Labs
**Budget:** $40,000
**Target Delivery:** Early Feb 2026 (stretch) / End Q1 2026 (latest)

## Module 1 Structure

### Core (30 min) - All Staff
1. **Introduction** - AI mindset, agency, "driver's choice" analogy
2. **How LLMs Work** - Technical literacy, hallucination risks, accountability
3. **Introducing ChatMQ** - Data protection, AU vs overseas processing, privacy
4. **Exploring ChatMQ** - Hands-on usage, what data can/cannot upload
5. **Accountability** - Human oversight, responsibility for outputs

### Extended Paths (15 min each) - Academic Staff
- **Research:** Ethics checklist deep-dive
- **Teaching & Learning:** Lesson planning, assessment design, resources

## Key Requirements
- Approachable, non-technical language
- Empowering tone (not punitive)
- 3-5 min sections for easy updates
- Practical examples throughout
- Format: Quarto → Articulate Rise/Storyline → Workday Learning

## Team
- **Brian Ballsun-Stanton** - Humanities Labs, content development
- **Jodie** - Teachers Learning Hub, instructional design, existing TLH materials
- **Maryam Khalid** - Associate Dean, oversight
- **Phil Laufenberg** - Central AI, policy/stakeholder coordination

## Existing Resources (TLH)
- Driving analogy animation
- AI literacy section and activities (10hr ProLearn course)
- AI prompting poster and video
- Ethical AI use checklist (Zenodo)
- "Using AI ethically" video
- Articulate course template in MQ branding

## Key Dates
- 16 Jan 2026: Learning design draft to Maryam
- 30 Jan 2026: Content draft complete
- Feb 2026: Articulate build, video production
- Feb 2026: Pilot on Workday

## File Structure
- `planning_docs/` - Agreement, project plan PDFs
- `meeting_transcripts/` - Session recordings and transcripts
- `src/` - Meeting transcriber tool

## Commands
```bash
# Transcribe meeting audio (if needed)
uv run python -m meeting_transcriber
```
```

---

## Verification
After implementation:
1. Check issues exist: `gh issue list`
2. Verify CLAUDE.md created at repo root
3. Commit and push changes
