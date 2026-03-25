# Test Requirements: PDF Paragraph Numbering (#417)

## Automated Tests

| AC | Criterion | Test Type | Expected Test File | Phase |
|----|-----------|-----------|-------------------|-------|
| pdf-para-numbering-417.AC1.1 | HTML passed to Pandoc contains `<span data-paranumber="N">` at the start of each auto-numbered paragraph | Unit | `tests/unit/export/test_paragraph_markers.py` | 1 |
| pdf-para-numbering-417.AC1.1 | End-to-end: `convert_html_with_annotations()` with paragraph map produces LaTeX with `\paranumber{N}` for each numbered paragraph | Smoke (`@requires_pandoc`) | `tests/unit/export/test_paranumber_latex.py` | 2 |
| pdf-para-numbering-417.AC1.2 | No markers injected when `word_to_legal_para` is None (autonumbering off) | Unit | `tests/unit/export/test_paragraph_markers.py` | 1 |
| pdf-para-numbering-417.AC1.3 | No markers injected for empty paragraph map | Unit | `tests/unit/export/test_paragraph_markers.py` | 1 |
| pdf-para-numbering-417.AC1.3 | Empty paragraph map returns HTML unchanged (edge case confirmation) | Unit | `tests/unit/export/test_paragraph_numbering_edge_cases.py` | 4 |
| pdf-para-numbering-417.AC1.4 | LaTeX output contains `\paranumber{N}` matching the paragraph map | Smoke (`@requires_pandoc`) | `tests/unit/export/test_paranumber_latex.py` | 2 |
| pdf-para-numbering-417.AC1.5 | PDF compiles without errors when `\paranumber` commands are present | Smoke (`@requires_latexmk`) | `tests/unit/export/test_paranumber_latex.py` | 2 |
| pdf-para-numbering-417.AC1.6 | Paragraphs with highlight spans at position 0 still get the paranumber marker before the highlight | Unit | `tests/unit/export/test_paragraph_markers.py` | 1 |
| pdf-para-numbering-417.AC2.1 | Long annotations produce `\label{annot-inline:N}` at inline location and `\hyperref[annot-endnote:N]` wrapping superscript | Smoke (`@requires_pandoc`) | `tests/unit/export/test_endnote_crossref.py` | 3 |
| pdf-para-numbering-417.AC2.2 | Endnote entries contain `\label{annot-endnote:N}` and `\hyperref[annot-inline:N]` wrapping endnote number | Smoke (`@requires_pandoc`) | `tests/unit/export/test_endnote_crossref.py` | 3 |
| pdf-para-numbering-417.AC2.3 | Table-safe variants (`\annotref`/`\annotendnote`) produce matching label/hyperref pairs | Smoke (`@requires_pandoc`) | `tests/unit/export/test_endnote_crossref.py` | 3 |
| pdf-para-numbering-417.AC2.4 | Short annotations (margin path) do NOT get hyperref linking | Smoke (`@requires_pandoc`) | `tests/unit/export/test_endnote_crossref.py` | 3 |
| pdf-para-numbering-417.AC2.4 | Only-short-annotations document: LaTeX contains `\annot{` but NO `\label{annot-endnote:` | Smoke (`@requires_pandoc`) | `tests/unit/export/test_paragraph_numbering_edge_cases.py` | 4 |
| pdf-para-numbering-417.AC3.1 | Existing export tests pass without modification | Unit + Smoke | Existing test suite (no new file) | 4 |
| pdf-para-numbering-417.AC3.2 | `format_annot_latex()` output with `para_ref` survives endnote `\write` path | Smoke (`@requires_pandoc`) | `tests/unit/export/test_paragraph_numbering_edge_cases.py` | 4 |

## Human Verification

| AC | Criterion | Justification | Verification Approach |
|----|-----------|---------------|----------------------|
| pdf-para-numbering-417.AC1.5 | Paragraph numbers render in the PDF left margin as small grey sans-serif text | Visual appearance (colour, size, font, margin placement) cannot be asserted programmatically. The automated smoke test confirms compilation succeeds, but the rendered visual result requires human eyes. | UAT (Phase 2): Open exported PDF from a workspace with auto-numbering enabled. Verify small grey numbers appear in the left margin next to each paragraph, matching on-screen numbers. Verify body text is not shifted or indented by the margin numbers. |
| pdf-para-numbering-417.AC2.1 | Bidirectional hyperlinks are clickable in the PDF viewer | The smoke test confirms `\label`/`\hyperref` commands appear in the LaTeX source and the PDF compiles, but whether the links are actually clickable and navigate correctly depends on PDF viewer rendering of `hyperref` anchors. | UAT (Phase 3): Open exported PDF containing long annotations. Click the superscript number in the body text and verify it jumps to the corresponding endnote. Click the endnote number and verify it jumps back to the inline location. |
| pdf-para-numbering-417.AC2.2 | Endnote back-links navigate to the correct inline location | Same justification as AC2.1 — `\write`-deferred `\hyperref` commands are verified structurally in LaTeX source, but runtime navigation requires PDF viewer interaction. | UAT (Phase 3): Same verification as AC2.1 — confirm bidirectional navigation works in both directions across multiple annotations. |

## Coverage Summary

- Total ACs: 12 (AC1.1 through AC1.6, AC2.1 through AC2.4, AC3.1 through AC3.2)
- Automated: 12 (all ACs have at least one automated test)
- Human verification: 3 (AC1.5 visual rendering, AC2.1 clickable links, AC2.2 endnote back-links)
- Coverage: 100%

## Notes

**AC1.5 split coverage:** The automated smoke test (`@requires_latexmk`) in `test_paranumber_latex.py` verifies that `\paranumber` compiles without errors. Human verification covers the visual aspect (grey, sans-serif, left-margin placement) that cannot be machine-asserted without image comparison tooling.

**AC2.1/AC2.2 split coverage:** The automated smoke tests in `test_endnote_crossref.py` verify the structural presence of `\label`/`\hyperref` pairs in the LaTeX source. Human verification covers the runtime behaviour of clicking links in a PDF viewer, which depends on `hyperref` anchor resolution across two LaTeX passes (handled by `latexmk` but not inspectable without a PDF viewer).

**AC3.1 is a meta-criterion:** Verified by running the full existing test suite after Phases 1-3, not by a new dedicated test. The Phase 4 implementation plan explicitly calls for `uv run grimoire test all` and `uv run grimoire test smoke` as the verification step.

**Phase 5 (documentation) has no acceptance criteria.** The design plan explicitly marks it as "Verifies: None — infrastructure/documentation phase." It is verified by `uv run grimoire docs build` succeeding, but this is not tied to any AC.

**Test lane placement:** Files in `tests/unit/export/` that use `@requires_pandoc` or `@requires_latexmk` auto-receive the `smoke` marker and run in the smoke lane, not the unit lane. This matches existing patterns (`test_markdown_to_latex.py`, `test_css_fidelity.py`). Pure unit tests in the same directory (no Pandoc dependency) run in the unit lane via xdist.
