# Operation Solano Dawn - Wargame Simulation Platform - Product Requirements Document

**Version 1.0 - Draft for Development**
**Prepared for:** [Colleague - Claude Code implementation]
**Prepared by:** [Facilitator] with AI assistance
**Classification:** Internal development document
**Source:** GitHub issue [#256](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/256)

---

## 1. Purpose and Scope

This document specifies the requirements for a web-based simulation platform to support Operation Solano Dawn, a 10-week immersive wargame exercise for ADF Legal Officer Training. The platform replaces the current Teams-based copy-paste workflow and addresses the facilitation, immersion, state management, and pedagogical quality control challenges identified in previous iterations.

The platform mediates between three parties: a Claude instance acting as Game Master (GM), 40-50 cadet groups each pursuing an independent scenario timeline, and a single facilitator who maintains pedagogical oversight across all groups.

---

## 2. Background and Pain Points Addressed

Previous iterations of the exercise were delivered via copy-paste to Microsoft Teams. The following pain points are explicitly addressed by this platform:

| Pain Point | Platform Response |
|---|---|
| Teams copy-paste clunkiness | Native interface eliminates manual relay |
| Lack of immersion in Teams | Tactical operations centre aesthetic with authentic military communication formatting |
| Difficulty tracking multiple groups | Facilitator dashboard with per-group state and flagged triage view |
| Scale challenges (~40-50 groups) | Concurrent state management via pyCRDT; facilitator triage workflow designed for single-person review at scale |
| Facilitator and cadets losing track of developments | Persistent cadet-facing information panels: contacts, state summary, decision log, intelligence log, resource log |
| IHL hallucination risk | Automated flagging of legal citations for facilitator review; cadet-populated IHL concept tracker |
| Narrative length and density | Output length constraints enforced at GM level; length flagged for facilitator review |
| Pedagogical drift | Facilitator intervention workflow: freeform correction instructions to Claude with approval gate before content reaches cadets |

---

## 3. Technical Environment

- **Hosting:** NCI sensitive data cloud provider
- **OS:** Ubuntu 24.04
- **Framework:** NiceGUI (reference implementation: github.com/MQFacultyOfArts/PromptGrimoireTool)
- **Concurrent state:** pyCRDT for managing 40-50 independent group timelines
- **AI backend:** Claude API (system prompt: Operation Solano Dawn Master System Prompt v2.0)
- **Deployment:** Handled by implementing developer
- **Authentication:** Simple passphrase-based login - no institutional SSO required
- **Note:** Prompt Grimoire Tool extension is a viable implementation path and should be evaluated by the developer against a clean build

---

## 4. Users and Roles

### 4.1 Cadet Group Representative

One designated member per group. Receives scenario content on behalf of their group, submits the group's collective decision, and manages their group's information panels. Groups discuss offline (in person or via their own channels) and the representative enters the consensus decision.

### 4.2 Facilitator

Single user. Reviews all group turns before narrative progression. Sends correction instructions to Claude when needed. Approves revised content before release. Monitors group progress and health across the cohort. Accesses debrief analytics at exercise conclusion.

### 4.3 Claude GM

Not a human user - the AI backend. Receives cadet decisions, generates scenario content and State Summary updates per the Master System Prompt, holds output in a pending state for facilitator review before release to cadets.

---

## 5. Interface Requirements

### 5.1 Aesthetic and Tone

The cadet-facing interface must evoke a modern tactical operations centre rather than a chat application or document editor. Design requirements:

- **Colour palette:** Dark background, high-contrast text, muted accent colours consistent with a low-light operations environment
- **Typography:** Military communication aesthetic - monospace or semi-monospace for incoming messages and logs; clean sans-serif for UI chrome
- **Layout:** Multiple simultaneous information panels visible on a single screen without requiring scrolling between sections
- **Message formatting:** Incoming communications must render with timestamps, source callsigns, and appropriate formatting as specified in the GM system prompt (TALON formal military structure; field fighters terse; civilians unstructured; COMPASS precise analytical; etc.)
- **Tone:** The interface should feel like a tool, not a game. No gamification elements, achievement indicators, or consumer app conventions

### 5.2 Cadet Interface - Panel Structure

The cadet interface consists of the following persistent panels:

**INCOMING COMMUNICATIONS**
The primary narrative panel. Displays the current week's scenario content as formatted field communications. New content appears as arriving transmissions, not as a chat feed. Supports scroll-back through current week's communications. Does not display prior weeks by default - accessible via Decision Log.

**CURRENT STATE - WHAT YOUR TEAM KNOWS**
A realistic intelligence summary derived from the State Summary but filtered to what the cadet group's embedded team would actually know. This is not the full GM State Summary - it reflects the cadet team's in-world knowledge state. Updated after each turn. Panels within this view:
- Personnel encountered (not full character profiles - names, callsigns, roles as encountered)
- Resource status (ammunition, medical supplies, communications, finances, logistics network - at the level of realism the scenario supports)
- Environmental and threat indicators (DAF alert status as perceived, civilian trust as perceived, active threads as known to the team)

**INTELLIGENCE LOG**
A running log of intelligence the group has received or sought, with source and confidence level where provided by the GM. Cadets can annotate entries. Supports filtering by week.

**DECISION LOG**
A chronological record of the group's submitted decisions, week by week. Read-only. Used for group self-orientation when returning to the exercise after time away.

**IHL CONCEPT TRACKER**
A cadet-populated panel. Blank at exercise start. Cadets can add, edit, and organise IHL concepts, articles, and principles as they encounter and identify them through the scenario. The system does not populate this automatically - cadets must do the work of identifying and recording relevant law. Supports free text entry with optional tagging by week and theme.

**SUBMIT DECISION**
A text input panel for submitting the group's collective decision. Includes:
- Current week and phase indicator
- Deadline countdown timer (display only - facilitator-configured per cohort schedule)
- Text input field with a character guidance indicator (not a hard limit - a soft prompt to keep submissions focused)
- Submit button
- Confirmation of submission with timestamp

### 5.3 Facilitator Interface - Panel Structure

**GROUP OVERVIEW DASHBOARD**
The facilitator's primary view. Displays all 40-50 groups in a triage-optimised layout. For each group shows:
- Group identifier
- Current week
- Time since last activity
- Response status (awaiting content / awaiting cadet response / pending facilitator review / approved and delivered)
- Flag indicators (see Section 6.2)
- Quick-access button to open individual group view

Default sort: groups with active flags and pending review at top. Secondary sort: groups closest to deadline.

**INDIVIDUAL GROUP VIEW**
Accessible on demand for any group. Displays:
- Full current State Summary (GM version - all variables, not the cadet-filtered version)
- Claude's generated output for the current turn, formatted as it would appear to cadets
- Automated flag summary (see Section 6.2) with specific flagged passages highlighted in context
- Facilitator action panel: approve as-is / send correction instruction / approve with manual edit note
- Full group history: all prior turns, decisions, and State Summaries accessible by week
- IHL citations extracted from the current turn's output, listed separately for rapid review

**CORRECTION INSTRUCTION WORKFLOW**
When the facilitator selects `send correction instruction`:
- Freeform text field for instruction to Claude
- Current turn content visible alongside for reference
- Submit instruction -> Claude regenerates -> revised output returns to facilitator review (does not go to cadets)
- Facilitator can iterate correction instructions until satisfied
- Approve revised output -> releases to cadet group

**COHORT MANAGEMENT PANEL**
Global controls for the facilitator:
- Current week and phase indicator for the cohort
- Deadline configuration: set response deadline per week, enable/disable countdown timer display
- Advance cohort week (moves all groups to next week's phase - individual groups can be held back manually)
- Broadcast message: send a facilitator note to all groups or selected groups (displayed as a system message in the communications panel, not as a character communication)
- Group status export: snapshot of all group states at any point

**DEBRIEF ANALYTICS VIEW**
Available at exercise conclusion (or at facilitator discretion during the exercise):
- Cross-group comparison of decisions by week
- IHL concepts identified per group (drawn from cadet-populated IHL trackers)
- Fault line states across groups at any given week
- Outcome variables compared across groups (civilian trust, international awareness, evidence quality, etc.)
- Flag history: which groups triggered which flag types and how many correction iterations were required
- Exportable as structured report (PDF and/or CSV)

---

## 6. State Management Requirements

### 6.1 Group Timeline Isolation

Each of the 40-50 groups maintains a completely independent scenario timeline. Group timelines must not contaminate each other. The same canonical world bible and GM system prompt underlies all groups, but each group's State Summary, decision history, and scenario variables are entirely their own.

**Implementation note:** pyCRDT is available and appropriate for managing concurrent state across groups. The developer should evaluate its application to the State Summary update cycle specifically, given that State Summaries are updated after every turn and must be reliably versioned per group.

### 6.2 Flag Generation

Claude's output for each turn is automatically analysed before reaching the facilitator review queue. The following flag types are generated:

| Flag Type | Trigger Condition | Priority |
|---|---|---|
| LEGAL CITATION | Any specific IHL article, convention, or case reference appears in the output | Review |
| CHARACTER ANOMALY | A character who has not been introduced to this group appears; a character's established voice or status appears inconsistent with their State Summary record | Review |
| OUTPUT LENGTH | Turn output exceeds a defined word count threshold (recommended: 800 words for standard weeks, 1200 words for Week 4 extended week) | Review |
| MISSED PEDAGOGICAL BEAT | GM output does not appear to engage the week's primary IHL theme based on keyword and thematic analysis | Alert |
| DEADLINE APPROACHING | Group has not submitted a response and is within 2 hours of deadline | Info |
| DEADLINE PASSED | Group has not submitted a response and deadline has passed | Alert |
| CORRECTION ITERATION | A turn has required more than one correction instruction cycle | Info |

**Flag display:** Flags appear as colour-coded indicators on the Group Overview Dashboard and as highlighted annotations in the Individual Group View. Facilitator can dismiss flags after review with an optional note.

### 6.3 State Summary Lifecycle

The State Summary is the authoritative record of each group's scenario state. Its lifecycle per turn:

1. Facilitator approves cadet decision for processing (or deadline passes and system advances)
2. Cadet decision + current State Summary sent to Claude
3. Claude generates scenario content + updated State Summary
4. Output held in pending state
5. Facilitator reviews - flags surfaced
6. Facilitator approves or sends correction instruction
7. On approval: scenario content released to cadet interface; updated State Summary stored as new canonical state for group; previous State Summary archived (all versions retained)
8. Cadet-facing state panels updated from new State Summary (filtered to realistic intel view)

### 6.4 Narrative Advancement Without Response

If a group does not submit a decision before the deadline:
- System flags the group (DEADLINE PASSED)
- Facilitator can trigger narrative advancement manually, or configure the system to advance automatically after a defined grace period
- Claude generates the turn's content with a note in the State Summary that no cadet decision was received - scenario consequences applied as per GM system prompt (the narrative moves without them)
- Turn content delivered to the group on their next login

---

## 7. Claude Integration Requirements

### 7.1 System Prompt

The Master System Prompt (Operation Solano Dawn v2.0) is loaded as Claude's system prompt for all group interactions. It is not editable through the interface - changes to the system prompt are a development-level action.

### 7.2 Per-Turn Context Package

Each Claude call includes:
- The Master System Prompt
- The group's current State Summary
- The group's decision history (summarised for prior weeks, full for current week)
- The cadet group's submitted decision (or a null decision flag if deadline passed)
- Any facilitator correction instruction (if this is a regeneration call)

### 7.3 Output Structure

Claude's output for each turn must be structured to support automated flag generation and facilitator review. The output schema should include:
- **Scenario content:** The narrative and communications content for cadets
- **Updated State Summary:** In the standardised template format specified in the Master System Prompt
- **IHL citations list:** A machine-readable list of any IHL articles, conventions, or legal principles referenced in the scenario content
- **GM notes:** Internal notes for the facilitator (not visible to cadets) flagging anything Claude considers pedagogically significant, uncertain, or worth facilitator attention

### 7.4 Output Length Management

The system enforces a soft length guidance on Claude's output via the system prompt and a hard display threshold in the interface. If scenario content exceeds the week's word count threshold, an OUTPUT LENGTH flag is generated for facilitator review before the content is released. The facilitator can approve the longer output or send a correction instruction to condense.

---

## 8. Authentication and Access

### 8.1 Cadet Group Access

- Each group is assigned a unique group code and passphrase at exercise setup
- One login session per group at a time (the designated representative logs in)
- Session persistence: cadets can close and reopen without losing state
- No email or institutional credentials required

### 8.2 Facilitator Access

- Single facilitator account with separate credentials
- Full read access to all group states, histories, and pending content
- Write access to correction instructions, approvals, cohort management controls, and debrief analytics
- Session persistence with appropriate timeout for security given NCI hosting environment

### 8.3 No Public Access

The platform is not publicly accessible. Access is via NCI environment only.

---

## 9. Exercise Setup Requirements

Before an exercise cohort begins, the facilitator must be able to configure:
- Number of groups and generate group credentials
- Cohort schedule: week start dates, response deadlines per week, grace period before automatic advancement
- Countdown timer display: on/off per week
- Output length thresholds per week (with defaults pre-configured per the Master System Prompt's week structure)
- Flag sensitivity settings: which flag types generate alerts vs review vs info indicators

---

## 10. Data and Export Requirements

### 10.1 Data Retention

All group State Summaries (all versions), all cadet decisions, all Claude outputs (including pre-correction versions), all facilitator correction instructions, and all flag histories are retained for the duration of the exercise and for a defined period afterward.

### 10.2 Debrief Export

At exercise conclusion, the facilitator can export:
- Full cohort summary report (PDF) including cross-group analytics as specified in Section 5.3
- Raw data export (CSV) of group decisions, State Summary variables, and IHL tracker content for facilitator analysis
- Individual group transcript export (PDF) suitable for providing to each group as a record of their exercise timeline

### 10.3 Data Sensitivity

Given NCI hosting, all data handling must comply with NCI's data classification and retention requirements. The developer is responsible for ensuring compliance as part of deployment.

---

## 11. Out of Scope for This Iteration

The following are explicitly out of scope for the initial build and should not be designed around, though the architecture should not preclude them being added later:

- Structured (non-freeform) correction instruction options
- Real-time cross-group comparison during the live exercise
- Integration with institutional LMS or SSO
- Mobile-optimised interface (desktop browser is the primary target)
- Automated IHL hallucination detection beyond citation flagging (facilitator review remains the verification mechanism)
- Multi-facilitator access with role differentiation

---

## 12. Success Criteria

The platform is considered fit for purpose when:

1. A facilitator can review a summarised, flagged view of 40-50 group turns and make approve/correct decisions for all of them within a reasonable single session
2. Cadet groups can receive scenario content, orient themselves using their information panels, discuss, and submit decisions without requiring any facilitator relay action
3. The interface aesthetic meaningfully enhances scenario immersion relative to Teams delivery
4. No group's timeline is contaminated by another group's decisions or state
5. Legal citations in Claude's output are surfaced for facilitator review before reaching cadets in 100% of cases
6. A full exercise cohort can be run, archived, and exported for debrief without data loss

---

## 13. Open Questions for Developer

1. **Prompt Grimoire extension vs clean build:** The developer should assess whether extending the existing Prompt Grimoire Tool is more efficient than a clean NiceGUI build given the specific state management requirements (pyCRDT, per-group Claude context packaging, flag generation pipeline). This PRD does not mandate either approach.
2. **Claude context window management:** With 40-50 groups each accumulating multi-week decision histories, context window management for the per-turn Claude call needs careful design. The developer should advise on the approach to summarising prior week history without losing State Summary fidelity.
3. **Flag generation implementation:** The automated flag generation described in Section 6.2 requires some form of output analysis. The developer should advise on whether this is best implemented as a second Claude call, a rules-based parser, or a hybrid approach, and flag any cost implications.
4. **Countdown timer:** Noted as a desired but non-essential feature. Developer to advise on implementation complexity and include if straightforward within scope.
5. **Concurrent session handling:** With 40-50 groups potentially submitting decisions in the same window, the developer should confirm pyCRDT is the right tool for this specific concurrency pattern and advise if an alternative is preferable.

---

*End of PRD v1.0*
