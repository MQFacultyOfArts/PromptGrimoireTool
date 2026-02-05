# Ralph Loop: Fixture Presentation QA

## One-liner invocation

```bash
/ralph-loop "Execute visual QA from docs/wip/ralph-fixture-presentation.md" --completion-promise "ALL FIXTURES PASS" --max-iterations 30
```

## Task

Visual QA of HTML fixture rendering through the annotation page pipeline. Each fixture must display with sensible CSS defaults - readable text, clear structure, and speaker distinction where applicable.

## Setup

Generate screenshots first:

```bash
uv run pytest tests/e2e/test_fixture_screenshots.py -v
```

Screenshots output to: `output/fixture_screenshots/`

## Evaluation Criteria

For each screenshot, verify ALL of the following:

### 1. READABLE TEXT

- Font size appears reasonable (14-18px equivalent, not tiny or huge)
- Line height sufficient (text lines not cramped together)
- Adequate contrast (text not washed out or hard to read)
- CJK characters render correctly (not boxes or garbled)

### 2. CLEAR STRUCTURE

- Headings visually distinct from body text (larger or bolder)
- Lists properly indented with visible markers
- No orphan bullets or empty list items (nav cruft must be stripped)
- Tables have visible alignment (columns readable, not overlapping)
- Paragraphs have vertical spacing between them
- Code blocks visually distinct (monospace, background)
- Blockquotes visually indented (padding or border-left)
- Margin/indentation from source document preserved where meaningful
- `<pre>` blocks preserve whitespace and line breaks
- Math content (KaTeX/MathML) renders as readable inline text, not orphaned digits

### 3. SPEAKER DISTINCTION (chatbot fixtures only)

Applies to all chatbot fixtures: claude_cooking, claude_maths, openai_*, google_*, scienceos_*

- User vs Assistant turns have visual separation
- Either: labels present ("User:", "Assistant:")
- Or: clear visual boundary (spacing, indentation, background)
- **No null/empty rounds**: A speaker label must not appear without associated content. Consecutive labels with no text between them = FAIL.
- **No redundant labels**: If the source already has platform labels ("You said:", "ChatGPT said:"), our injected labels should not duplicate them. Either suppress injection or suppress the original.
- **Thinking vs response**: Claude thinking blocks ("Thought process") must be visually differentiated from words spoken to the user. Multiple consecutive "Assistant:" labels within one turn = FAIL.

### 4. NO DATA LOSS

- Thread titles from source should render (e.g. "Cooking/" in Claude)
- Content should not be truncated or garbled by pipeline processing
- Numbers/text extracted from stripped math containers should be coherent, not orphaned digits on separate lines

## Bugs Fixed This Session

1. **`_remove_empty_elements()` removing speaker divs** (FIXED): Both Python-side (`html_input.py`) and client-side JS (`annotation.py` `removeEmpty()`) now preserve elements with `data-speaker` attribute.
2. **Client-side attribute stripping before platform detection** (FIXED): Speaker label injection now happens client-side in the paste handler JS, before attributes are stripped.
3. **`const html` preventing reassignment** (FIXED): Changed to `let html` so speaker injection `html.replace()` calls work.
4. **Orphan nav/list items** (FIXED): `<nav>` elements and empty `<li>` items are now stripped in the paste handler.

## Open Issues

### P1: Null/empty speaker rounds (affects Gemini, AI Studio, Claude)

**Symptom**: Multiple consecutive "User:" or "Assistant:" labels with no text between them.

**Root cause**: Speaker label injection regex matches nested container elements. For example, Gemini has `<user-query>` wrapping `<user-query-content>` — regex matches both levels.

**Fix approach**: Target only the innermost (leaf) turn marker elements, or deduplicate consecutive same-role labels after injection.

**Affected fixtures**: google_gemini_debug, google_gemini_deep_research, google_aistudio_image, google_aistudio_ux_discussion, claude_cooking

### P2: Claude thinking blocks not differentiated

**Symptom**: Claude "Thought process 18s" followed by multiple "Assistant:" labels, mixing thinking metadata with actual response text.

**Root cause**: Claude exports thinking in `<details><summary>Thought process</summary>...</details>` blocks. The `font-claude-response` class regex matches both thinking and response containers equally.

**Fix approach**: Detect and collapse/remove `<details>` thinking blocks, or inject a distinct "Thinking:" label instead of "Assistant:".

**Affected fixtures**: claude_cooking, claude_maths

### P3: Redundant OpenAI platform labels

**Symptom**: "You said:" (original) followed by "User:" (injected), and "ChatGPT said:" followed by "Assistant:".

**Root cause**: OpenAI exports include their own speaker labels as content text. Our pipeline injects additional labels on top.

**Fix approach**: Either (a) don't inject labels for OpenAI since it already has them, or (b) strip the original "You said:"/"ChatGPT said:" text.

**Affected fixtures**: openai_biblatex, openai_dh_dr, openai_dprk_denmark, openai_software_long_dr

### P4: Math element stripping (KaTeX/MathML)

**Symptom**: Formula `R ≈ 6371km` renders as "R ≈ 6R≈6371km" with orphaned "3", "7", "1" on separate lines.

**Root cause**: KaTeX renders math as deeply nested `<span>` trees with `<math>` MathML fallback. Our pipeline strips the container spans, leaving orphaned text nodes from different representation layers (display text + MathML + accessibility text).

**Fix approach**: Before general stripping, extract text content from `<math>` elements (using `textContent`) and replace the entire KaTeX wrapper with the plain text, OR preserve `<math>` elements through the pipeline.

**Affected fixtures**: openai_dprk_denmark

### P5: Code block whitespace in `<pre>` not preserved

**Symptom**: Python code blocks render as a wall of text without line breaks.

**Root cause**: Line breaks within `<pre>` blocks may be normalised during HTML processing (clipboard paste or iframe round-trip).

**Fix approach**: Ensure `<pre>` content whitespace (especially newlines) survives the paste pipeline. May need special handling to preserve `\n` within `<pre>` elements before the general HTML cleanup.

**Affected fixtures**: openai_dprk_denmark (screenshots 004, 005)

### P6: Blockquote and margin rendering

**Symptom**: AustLII blockquotes not visually indented. Grounds paragraphs don't show margin structure.

**Root cause**: (a) CSS shorthand `margin: 0px 0px 0.75em` isn't captured by `keepStyleProps` regex which only matches individual properties (`margin-left`, etc.). (b) `_PAGE_CSS` may lack explicit blockquote styling.

**Fix approach**: (a) Add `margin` shorthand parsing to `keepStyleProps`. (b) Add blockquote CSS to `_PAGE_CSS` (e.g. `border-left: 3px solid #ccc; padding-left: 1em; margin: 1em 0;`).

**Affected fixtures**: austlii

### Source artefacts (not pipeline bugs)

These are quirks of the source HTML, not issues in our pipeline:

- **spanish_sample**: "GUÍA DE INICIO" is a `<p>` in source (not a heading). The "2." and "3." are standalone `<p>` tags (numbering separated from headers in source).
- **claude_cooking**: "Cooking/" thread title — the slash is in the original Claude export.
- **aistudio_ux_discussion_004**: Code fragments rendered as headings — source Markdown placed code identifiers in `##` heading markup.

## Fixture Checklist

| Fixture | Platform | Type | Screenshots | Status | Issues |
|---------|----------|------|-------------|--------|--------|
| austlii | none | legal doc | 6 (ul, ol, blockquote) | FAIL | P6: blockquote/margin not indented; orphan bullet (fixed) |
| chinese_wikipedia | none | article | 4 (ul, h2) | PASS | CJK renders correctly |
| claude_cooking | claude | chatbot | 6 (ul, ol, h3, speaker) | FAIL | P1: duplicate labels; P2: thinking not differentiated |
| claude_maths | claude | chatbot | 1 (short doc) | FAIL | P2: thinking not differentiated |
| translation_japanese | none | article | 3 (h2) | PASS | |
| translation_korean | none | article | 1 (short doc) | PASS | |
| translation_spanish | none | article | 2 (h2) | PASS | Source artefact: all-caps `<p>`, orphan numbers |
| openai_biblatex | openai | chatbot | 6 (h3, ol, h2) | FAIL | P3: redundant "You said:"/"ChatGPT said:" + our labels |
| openai_dh_dr | openai | chatbot | 6 (ol, h1, blockquote, h2) | FAIL | P3: redundant labels |
| openai_dprk_denmark | openai | chatbot | 6 (h2, pre) | FAIL | P3: redundant labels; P4: math garbled; P5: code whitespace |
| openai_software_long_dr | openai | chatbot | 6 (ul, h1, h2) | FAIL | P3: redundant labels |
| google_aistudio_image | aistudio | chatbot | 2 (ol) | FAIL | P1: null User: rounds at top |
| google_aistudio_ux_discussion | aistudio | chatbot | 6 (h1, ol) | FAIL | P1: null User: rounds; source artefact: code-as-headings |
| google_gemini_debug | gemini | chatbot | 6 (h3, ul, pre, ol) | FAIL | P1: null User: rounds at top |
| google_gemini_deep_research | gemini | chatbot | 3 (h1, pre) | FAIL | P1: null User: rounds at top |
| scienceos_loc | scienceos | chatbot | 6 (h1, h2, speaker, h3) | PASS | Clear speaker distinction |
| scienceos_philsci | none | research report | 6 (h1, h2, h3) | PASS | No platform markers; continuous prose, acceptable |

**Score: 6/17 PASS**

## Evaluation Process

**IMPORTANT:** Update this file's checklist table as you work. This is how you track state between iterations.

For each fixture (work through in order):

1. **Read screenshots:** Use the Read tool on each `output/fixture_screenshots/{fixture}_*.png` file
2. **Evaluate:** Check against ALL FOUR criteria above (readable text, clear structure, speaker distinction, no data loss)
3. **Be critical:** Do not mark PASS if there are null rounds, redundant labels, garbled math, missing whitespace, or broken indentation. These are real issues.
4. **If FAIL:**
   - Update the Issues column in the checklist table with specific issue references (P1, P2, etc.)
   - Identify root cause
   - Fix the CSS or preprocessing code
   - Regenerate ALL screenshots: `uv run pytest tests/e2e/test_fixture_screenshots.py -v`
   - Re-evaluate from the beginning (fixes may affect multiple fixtures)
5. **If PASS:** Update status to PASS in the checklist table, move to next fixture

### Proleptic Discipline

Before marking any fixture PASS or FAIL, apply proleptic challenge:

- **State the claim** you are about to make (e.g. "this fixture passes all four criteria").
- **Generate at least one counterargument** — what could be wrong that you haven't noticed? What assumption are you making about the screenshot? Could a visual artefact be hidden by scroll position, viewport size, or rendering timing?
- **Address the counterargument** with evidence (specific screenshot region, HTML source via `scripts/analyse_fixture.py`, or explicit reasoning).
- Only then commit to PASS or FAIL.

This prevents premature pass assertions that later turn out to be wrong. The cost of one extra paragraph of reasoning per fixture is trivial compared to the cost of a false PASS propagating through the QA loop.

## CSS Fix Location

Most presentation issues will be fixed in:

```
src/promptgrimoire/pages/annotation.py
```

Look for the `_PAGE_CSS` constant which defines the document container styling.
Look for the paste handler JS which does speaker injection and HTML cleanup.

Preprocessing issues (speaker labels, chrome removal) are in:

```
src/promptgrimoire/export/platforms/
```

Input pipeline issues (attribute stripping, empty element removal) are in:

```
src/promptgrimoire/input_pipeline/html_input.py
```

## Do NOT

- Skip fixtures or mark them PASS without reviewing all screenshots
- Mark PASS with "cosmetic" caveats — if the issue is visible and confusing, it's a FAIL
- Create new test files (the pytest screenshot generator is the source of truth)
- Change the test to make it pass instead of fixing the presentation
- Modify fixture files themselves
- Forget to update this file's checklist - it's your state between iterations

## Completion

When ALL 17 fixtures have status PASS (with no handwaving):

```
<promise>ALL FIXTURES PASS</promise>
```
