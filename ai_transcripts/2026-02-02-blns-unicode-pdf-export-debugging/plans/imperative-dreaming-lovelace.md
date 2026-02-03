# AI Literacy Training - Module 1 Course Design Plan

## Session Date: 2026-01-14
## Participants: Brian Ballsun-Stanton, Jodie Cahir, Claude

---

## Project Context

**Module**: "Driver's Licence for Responsible AI Use"
**Duration**: 30-45 minutes (core) + 15 min extended paths for academics
**Purpose**: Compliance module enabling MQ staff access to ChatMQ advanced features
**Delivery**: Articulate Rise/Storyline via Workday Learning
**Timeline**: Early Feb 2026 (stretch) / End Q1 2026 (latest)
**Budget**: $40,000

---

## Key Design Decisions Established

### 1. Gating Criterion
**Tool Competence (not Judgment Competence)**

The primary question being answered: "Can this person use ChatMQ without creating a data breach, compliance violation, or policy breach?"

Mindset/judgment content is foundational context that makes compliance rules make sense, but tool competence is what's actually gated.

### 2. Assessment Structure

| Component | Format | Attempts | Purpose |
|-----------|--------|----------|---------|
| Formative quizzes | Scenario-based MCQs with ChatMQ screenshots | Unlimited | Learning tool, reveals misconceptions |
| Capstone | AI-mediated dialogue where learner explains course content back to ChatMQ | Submitted artifact | Summative, AI-evaluated with human review for flags |
| Final gate | Scenario-based MCQs ("fiddly" enough to require understanding) | Unlimited | Compliance certification |

**Key insight**: Judgment competence becomes the *mechanism* through which tool competence is tested. Scenarios show Brian using ChatMQ; learners decide if output is correct/allowed.

### 3. Feedback Model
- **Explanatory wrong-answer feedback** (not just "incorrect, try again")
- Wrong answers get specific explanation of *why* that choice reflects a misconception
- AI helps learners improve weak areas in capstone dialogue
- AI should "not be an asshole" but genuinely exercise knowledge and discuss edge cases

### 4. Taxonomy: Marzano's New Taxonomy (MNT)

**Explicit objectives at ALL levels**, including Self-System and Metacognitive (not treating these as implicit scaffolding).

MNT Structure:
1. **Self-System** (activated first) — motivation, importance, efficacy, emotional response
2. **Metacognitive System** (activated second) — goal setting, process monitoring, clarity/accuracy
3. **Cognitive System** (four levels):
   - Retrieval (recognize, recall, execute)
   - Comprehension (integrate, symbolize)
   - Analysis (match, classify, error analysis, generalize, specify)
   - Knowledge Utilization (decision-making, problem-solving, experimenting, investigating)

### 5. MNT Application Across Sections

**NOT 1:1 mapping** (not "Section 1 = Self-System")

Each section touches multiple MNT levels as appropriate:
- **Earlier sections** → more Self-System and Metacognitive emphasis
- **Later sections** → more Metacognitive monitoring and Cognitive emphasis

**Objective density**: 1-2 explicit learning objectives per section (given 5-10 min sections)

**Self-System and Metacognitive delivery**:
- Not always formal objectives
- Often delivered via provocative questions or prompts to discuss in ChatMQ
- "Implicit in the provocations" — activating higher levels without heavy-handed instruction
- **Limit**: ~3 "prompt this into ChatMQ and discuss" moments before novelty wears off

**Metacognitive layer**: Primarily achieved through capstone AI dialogue, not within each section

### 6. Non-Negotiable Content
"What to do and what not to do" — practical compliance boundaries

---

## Course Structure (Revised)

### Section 1: Preface
- Intro video (high-level person: VC or Phil)
- "What you'll learn" outlined by presenter, reinforced in text

### Section 2: Driver's Choice / Mindset
**Learning Objective**: Learners will articulate why they are choosing to use (or not use) AI for a given task before beginning.

Content:
- Driver's Choice video (4:41) — see full script below
- Activity reinforcing "the why" decision

### Section 3: How LLMs Work
Content areas:
- Technical literacy (what LLMs actually are)
- Hallucination risks
- "AI is not a person" — statistical pattern tool
- "Don't rely on it for facts — you supply the facts"
- Accountability for AI-generated outputs

**Three misconceptions to counter**:
- (a) "AI understands what I'm asking" (anthropomorphization) — relates to shaping context
- (b) "AI gives me what I put in" — output quality depends on input quality, source evaluation, context shaping (THIS IS THE CORE ISSUE)
- (c) "AI output is good enough to use without checking" (uncritical acceptance)

All three must be covered. The core issue: learners don't understand that LLM output is shaped by what they provide.

Existing asset: Script for "How LLMs Work" video exists (teacher-bent, may need re-recording for general staff audience)

### Section 4: Introducing ChatMQ
Content areas:
- Data protection obligations
- Difference in data processing AU vs overseas
- Where data is stored
- Why ChatMQ was created
- Privacy and security

Links to MQ policy areas: Fairness and Inclusivity, Privacy and Security

Tasks: Video, Quiz about data storage/safety

### Section 5: Exploring ChatMQ
Content areas:
- Step-by-step: how to access, log on, use web search
- Choosing the right model for what you want to do
- What data can and cannot be uploaded
- Limitations/risks
- Accountability for outputs (practical examples)

Tasks: Series of short videos showing the tool, "now you try" activities

Existing asset: Ethical AI use checklist (Zenodo)

### Section 6: Accountability for AI-Generated Outputs
Content: Video, Reflective prompt

Links to MQ policy: Human Oversight and Responsibility

Existing asset: "Using AI ethically" video (3:30)

### Extended Paths (15 min each) — Academic Staff

**Research Path**: Go through Ethics checklist deep-dive

**Teaching & Learning Path**: How to use ChatMQ for:
- Lesson planning
- Assessment design / rubric creation
- Resource creation

---

## Driver's Choice Video Script (Full)

**Duration**: ~4:41
**Characters**: Brian and Jodie
**Format**: Vyond animation

### SCENE 1: RESIDENTIAL DRIVEWAY
JODIE: Before we drive anywhere, we need to make some decisions. We need to ask: What problem are we trying to solve right now? Do we need to drive there? What vehicle should we take?

(Driver walks toward semi-truck)

JODIE: I wouldn't drive a semi-trailer to pick up groceries five minutes away. That doesn't match the task.

(Driver walks to regular car)

BRIAN: The same is true for AI. Before you choose to use an AI tool, know what problem you're solving.

### SCENE 2: STREET CORNER
BRIAN: Once I know my problem, I ask: What tools could I use to solve it?

BRIAN: With AI, this means asking: Should I use ChatGPT? Claude? A specialised ready-made tool? Or should I do this task myself?

JODIE: Just like choosing a vehicle, I need to consider what I'm trained to use and what the task requires.

JODIE: I might want to choose an SUV, a ute, or even a race car, depending on my needs and the task.

### SCENE 3: GARAGE OR PARKING LOT
JODIE: Before I can drive effectively, I need to understand my vehicle. What type of fuel does it need? What can it do? What are its limitations?

BRIAN: With AI, this means understanding which tool or Large Language Model you're using. What is it good at? What are its limits? If you are using a Large Language Model directly, such as ChatGPT or Claude, how do you give it the right prompts?

BRIAN: And just like driving, using a Large Language Model well requires training. Learning how to prompt, and how to give context, and how to guide the output.

### SCENE 4: INSIDE CAR (DRIVER'S PERSPECTIVE)
JODIE: When I'm driving, I'm not just steering. I'm constantly reading my environment. Traffic lights. Other drivers. Lane markings.

BRIAN: Using a Large Language Model is the same. I'm not just entering a prompt and walking away. I'm reading the output. Does it answer my question? Is there too much information? Not enough?

BRIAN: If the AI goes in the wrong direction, I reroute. I adjust my prompt. I provide more context. Every interaction is a choice. What I give to other people is a choice.

(Car hitting light pole)

JODIE: If you don't check your output, you're just creating work for others. They get something that looks like good work, but doesn't advance the task!

(Citation: Workslop, https://hbr.org/2025/09/ai-generated-workslop-is-destroying-productivity)

### SCENE 5: BUS STOP AND SIDEWALK
JODIE: We could have chosen to use public transport. That's like using a pre-built AI tool with fixed features. If it goes where we need, it's convenient. But we have no control over the route.

JODIE: Or we could have stayed home. That's like choosing not to use AI at all for this task. Each choice is valid for different situations. The key is matching the tool to the task.

### SCENE 6: RESIDENTIAL STREET WITH SCHOOL ZONE
JODIE: A vehicle amplifies my decisions. A small turn of the wheel moves me several metres.

BRIAN: Large Language Models work the same way. It amplifies what I choose to do - both good decisions and bad ones. If I give it unclear prompts, I get unclear results.

JODIE: This is augmentation, not automation. I'm still responsible. I'm still driving.

### SCENE 7: PARKING LOT OR DRIVEWAY
BRIAN: Using AI effectively means making many choices. Which tool do I pick? How do I prompt it? How do I verify the output? Am I happy to put my name on this result?

BRIAN: These choices happen before I use the tool, while I'm using it, and after I get the output.

JODIE: Just like driving, using AI requires constant judgment. Understanding your vehicle. Reading your environment. Making adjustments along the way.

JODIE: The tool amplifies your capability. But you're still the one making the decisions. You're still the one responsible for where you end up.

### SCENE 8: FINAL SCENE - DRIVEWAY
BRIAN: So before you start: Know your problem. Choose your tool. Understand how it works. And stay engaged every step of the way.

[END]

---

## Key Concepts from Video (for reference)

1. **Choice/Agency**: "Before we drive anywhere, we need to make some decisions"
2. **Tool-to-task matching**: "Know what problem you're solving" before choosing AI
3. **Augmentation, not automation**: "I'm still responsible. I'm still driving."
4. **Continuous judgment**: Choices happen before, during, and after using the tool
5. **Accountability**: "Am I happy to put my name on this result?"
6. **Workslop**: Unchecked AI output creates work for others — looks like good work but doesn't advance the task

---

## Learning Design Principles (from Jodie/TLH)

1. **Activate prior knowledge** at start
2. **Retrieval practice / spaced repetition** throughout — bring back language already introduced
3. **Reflections** for learner agency
4. **Cumulative knowledge building** — "this means X, now you've learned Y"
5. **Application opportunities** (decisions/judgments) despite Articulate's constraints
6. **Scenario-based MCQs** for application within platform limits
7. **Pre-plan Articulate interactives** to avoid scrambling later

**Available Articulate interactives**:
- Click to reveal (good for definitions)
- Tabs (more info, don't see all at once)
- Sorting activity
- Flashcard grid/stack
- Timeline
- Button/button stack (click to additional resources)
- Scenarios (NOT accessible — can't be read by screen readers, likely won't use for university-wide)

---

## Existing TLH Assets Available

- Driving analogy animation (Driver's Choice video)
- AI literacy section and activities (10hr ProLearn course)
- AI prompting poster and video
- Ethical AI use checklist (Zenodo)
- "Using AI ethically" video (3:30)
- Articulate course template in MQ branding
- "How LLMs Work" script (teacher-bent, may need adaptation)

---

## Terminology Clarification

- **Module 1** (in agreement docs) = **Lesson** (in Articulate) = the whole 30-45 min course
- **Sections** = the 3-5 minute chunks within the lesson
- This distinction matters for Articulate build

---

## Open Questions for Next Session

1. Section 3 (How LLMs Work) learning objective — needs drafting based on "it gives me what I put in" framing
2. Sections 4-6 learning objectives — not yet drafted
3. Extended paths (Research, Teaching & Learning) — objectives and structure not detailed
4. Specific activities for each section — not yet designed
5. "How LLMs Work" script — needs to be located and potentially adapted for general staff

---

## Session Progress

### Completed:
- Established gating criterion (tool competence)
- Established assessment structure (formative + capstone + final)
- Established feedback model (explanatory)
- Confirmed taxonomy (MNT, explicit at all levels)
- Confirmed MNT application (distributed across sections, not 1:1)
- Confirmed course structure (6 sections + 2 extended paths)
- Drafted Section 2 learning objective
- Captured Driver's Choice video script

### Next steps:
- Draft remaining section objectives
- Design specific activities per section
- Locate and review "How LLMs Work" script
- Map Articulate interactives to specific content needs
