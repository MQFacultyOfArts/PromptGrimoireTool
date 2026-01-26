---
source: local investigation
created: 2026-01-26
summary: LibreOffice ODT annotation to PDF export - investigation and dead end
---

# ODT Annotations to PDF Export: Investigation Results

## Goal

Export annotated documents to PDF with visible margin comments, programmatically via LibreOffice headless mode.

## Approach Tested

1. Convert source document to ODT
2. Inject annotations using odfdo Python library
3. Export to PDF via LibreOffice headless with margin comments

## What Works

### GUI Export
LibreOffice Writer GUI export produces clean margin comments:
- File → Export as PDF
- Options: "Comments as PDF annotations" + "Comments in margin"
- Result: Clean, readable margin annotations with author, date, and comment text

### Filter Options Identified
From [LibreOffice PDF Export Parameters](https://help.libreoffice.org/latest/he/text/shared/guide/pdf_params.html):

| GUI Checkbox | Filter Parameter |
|--------------|------------------|
| Comments as PDF annotations | `ExportNotes=true` |
| Comments in margin | `ExportNotesInMargin=true` |

### Headless Command
```bash
libreoffice --headless --convert-to \
  "pdf:writer_pdf_Export:ExportNotes=true,ExportNotesInMargin=true" \
  --outdir output input.odt
```

## What Doesn't Work

### Headless Margin Rendering Bug
Headless mode renders annotation metadata (author, date) **on the same line**, producing garbled/overlapping text:

**GUI export:**
```
Case name

Unknown Author
01/26/2026 15:32
```

**Headless export:**
```
01ase202tt5n2  (garbled - all metadata overlaid)
```

Newlines within the comment body ARE respected - only the metadata header is broken.

### Per-Comment Colours Not Possible
**Dealbreaker:** ODT annotation colours are controlled by **global user preferences**, not per-comment XML attributes.

Setting location: Tools → Options → LibreOffice → Appearance → Custom Colors

Source: [Ask LibreOffice - How to change comment colors](https://ask.libreoffice.org/t/how-to-change-comment-colors/599)

This means we cannot distinguish different annotation types (e.g., instructor vs student comments) by colour.

## Workaround Considered (Not Pursued)

Format comment body with embedded metadata using newlines:
```
Author Name
2026-01-26 15:32

Actual comment text...
```

This would render cleanly but doesn't solve the colour problem.

## Conclusion

**This approach is a dead end for PromptGrimoire's needs.**

The combination of:
1. Headless rendering bugs for margin metadata
2. No per-comment colour support

...makes ODT/LibreOffice unsuitable for our annotation PDF export requirements.

## Alternative Approaches to Consider

- **LaTeX with marginnotes**: Full control over styling, but complex setup
- **HTML to PDF** (WeasyPrint/Playwright): CSS-based styling, sidebar annotations
- **PDF direct manipulation**: Add annotations directly to PDF (but limited styling)

## Files Created During Investigation

- `output/183_manual_annotations.odt` - Manually annotated ODT (reference)
- `output/183_manual_annotations.pdf` - GUI-exported PDF (working target)
- `output/183_headless_test.odt` - Copy used for headless testing
- `output/183_headless_test.pdf` - Headless export (broken metadata)
- `scripts/test_odt_annotations.py` - odfdo annotation injection PoC
