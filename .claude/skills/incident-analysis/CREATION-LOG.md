# Creation Log: incident-analysis

## RED Phase: Baseline Failures

The RED phase occurred naturally during the 2026-03-16 afternoon incident analysis. Two reviewers (proleptic challenger and Codex) identified 10 errors across two review rounds.

### Source Documents

- Original analysis: `docs/postmortems/2026-03-16-afternoon-analysis.md`
- Incident playbook: `docs/postmortems/2026-03-16-incident-response.md`
- Proposed tools: `docs/postmortems/2026-03-16-proposed-analysis-tools.md`
- New errors observed: `docs/postmortems/2026-03-16-new-errors.md`

### Baseline Failures (verbatim from reviewers)

#### Round 1: Proleptic Challenger

| # | Error | Type | Verbatim |
|---|-------|------|----------|
| 1 | JSONL covered 28 hours, not 2.5 | Failed to verify source boundaries | "The Data Sources table claims the JSONL covers 'Same window'... This is false. The JSONL spans from 2026-03-15T02:57 UTC through 2026-03-16T06:45 UTC. That is 28 hours, not 2.5 hours." |
| 2 | Finding 3 "No PG errors" was wrong | False negative from timezone error | "I checked the PG log directly: 2026-03-16 04:32:52 UTC ERROR... 2026-03-16 04:50:16 UTC FATAL: connection to client lost... That is 10 ERRORs and 3 FATALs during the afternoon window" |
| 3 | 5xx total 106 not 82 | Incomplete enumeration | "The total is 106, not 82. The 24 unaccounted-for 5xx errors include 15 x 500, 5 x 501, and additional 502/505/506/508 errors that are not discussed" |
| 4 | Pool size=5 contamination | Failed to filter by window | "The 66 INVALIDATE events with size=5 and overflow=10/10 are from the morning incident. Their inclusion in the afternoon analysis is a contamination artefact." |
| 5 | "1,967 errors" unreproducible | No provenance chain | "The '1,967 JSONL error events' figure... does not match even the unfiltered JSONL (1,242 errors). It appears to be error + some subset of warnings, but this is never explained." |

#### Round 2: Codex

| # | Error | Type | Verbatim |
|---|-------|------|----------|
| 6 | Finding 7 hedges on post-deploy errors | Confidence understatement despite available evidence | "8 of the 10 PG tag uniqueness errors are at 16:11 AEDT. Those are definitively post-deploy, so the text should stop suggesting they may be from the pre-restart window." |
| 7 | Mixed evidence scopes at same confidence | Confidence level flattening | "mixes unfiltered JSONL duplicate counts, prior-day student-id errors, and post-window 19:38–19:39 share-button evidence... at the same confidence level as afternoon findings" |
| 8 | Tools omit journal analyser | Missing critical source type | "the proposal only defines JSONL, HAProxy, PG, and summary tools. Making journal handling an open question is backwards" |
| 9 | Tools hardcode AEDT | Baking in error-producing assumptions | "bakes in the same class of hidden timezone assumption that already caused this review to go wrong" |
| 10 | Restart provenance overstated | Inference stated as fact | "'This was the deploy of #360/#361 fixes' is still an inference, and the text admits shell history was not checked" |

### Codex's Meta-Critique

"The real repeat failure mode is scope leakage, not arithmetic. Analysts mix time windows, source formats, and post-hoc corroborations, then a summary layer flattens them into one narrative. A toolchain that omits provenance manifests and journal parsing will automate the wrong thing faster."

### Error Audit Analysis

The deeper pattern (from structured error audit): **absent input validation on analytical data.** Every error follows the same shape: the analyst operated on data without first verifying that the data matched the analytical assumptions. This is the analytical equivalent of "validate your inputs at the boundary."

### Rationalizations Observed

During the original analysis, these rationalizations occurred:
- "The JSONL file has the same name as the journal window, so it covers the same period" (assumption, not verified)
- "No PG errors" (reported confidently after a grep that used the wrong timezone offset)
- "82 5xx errors" (counted only the codes expected from the hypothesis, not all codes present)
- "1,967 errors" (number reported without recording the command that produced it)

### Methodology Research

The skill design draws on:
- **Popper/falsification** — frame findings as hypotheses, identify what would disprove them
- **Allspaw/Cook/Hollnagel** — "each necessary but only jointly sufficient"; no single root cause
- **Honeycomb** — hypothesis-driven debugging: validate or falsify with another query
- **Howie Guide (PagerDuty/Jeli)** — track hypothesis disposition (raised → tested → survived/falsified)
- **Etsy Debriefing Facilitation Guide** — catch counterfactuals, premature convergence, hindsight bias
- **Google SRE** — all conclusions linked to data sources with time windows
- **Dekker** — "human error" is the start of investigation, not the conclusion

Full source list in research notes from the internet-researcher agent run during this session.

## GREEN Phase

Skill written addressing each baseline failure as a positive action.

## REFACTOR Phase

(To be completed after subagent testing)
