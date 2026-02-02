# Spike 6: RTF Text Extraction

## Objective

Validate RTF file processing for Case Brief Tool using pandoc. Store HTML for faithful 1:1 rendering.

## Acceptance Criteria (from Issue #38)

- [ ] Parse RTF files using pypandoc
- [ ] Extract plain text while maintaining paragraph breaks
- [ ] Handle common RTF formatting (bold, italic, lists)
- [ ] Retain both original RTF blob and extracted text
- [ ] Preserve paragraph numbering from source documents

## Test Fixture

**File:** [tests/fixtures/183.rtf](tests/fixtures/183.rtf) (real NSW judgment)

| Property | Value |
|----------|-------|
| Case | *Lawlis v R* [2025] NSWCCA 183 |
| Size | 291KB |
| Features | Tables, italic case names, numbered paragraphs, legislation refs |

## Implementation

### 1. Add Dependency

**File:** [pyproject.toml](pyproject.toml)

```toml
"pypandoc>=1.14",
```

Requires `pandoc` binary on system (`apt install pandoc`).

### 2. Create Data Model

**File:** [src/promptgrimoire/models/case.py](src/promptgrimoire/models/case.py) (new)

```python
@dataclass
class ParsedRTF:
    original_blob: bytes      # Raw RTF for DB storage / re-processing
    html: str                 # Pandoc HTML output for rendering
    plain_text: str           # Plain text for search/indexing
    source_filename: str
```

Export from [src/promptgrimoire/models/__init__.py](src/promptgrimoire/models/__init__.py)

### 3. Create Parser Module

**File:** [src/promptgrimoire/parsers/rtf.py](src/promptgrimoire/parsers/rtf.py) (new)

```python
def parse_rtf(path: Path) -> ParsedRTF:
    """Parse RTF file to HTML and plain text via pandoc."""
```

Implementation:
- Validate file exists and size <= 10MB
- Validate RTF format (starts with `{\rtf`)
- `pypandoc.convert_file(path, 'html')` for faithful rendering
- `pypandoc.convert_file(path, 'plain')` for search indexing
- Return `ParsedRTF` with all three representations

Export from [src/promptgrimoire/parsers/__init__.py](src/promptgrimoire/parsers/__init__.py)

### 4. Create Unit Tests

**File:** [tests/unit/test_rtf_parser.py](tests/unit/test_rtf_parser.py) (new)

Tests against `183.rtf`:
- Returns `ParsedRTF` dataclass
- `original_blob` contains raw RTF bytes
- `html` contains valid HTML with tables, emphasis
- `plain_text` contains readable text
- Case name "Lawlis v R" appears in all outputs
- Paragraph numbers preserved in plain text
- File not found raises `FileNotFoundError`
- Oversized file raises `ValueError`
- Non-RTF file raises `ValueError`

## Error Handling

| Condition | Exception | Message |
|-----------|-----------|---------|
| File not found | `FileNotFoundError` | `"RTF file not found: {path}"` |
| File > 10MB | `ValueError` | `"RTF file exceeds 10MB limit"` |
| Invalid RTF | `ValueError` | `"File does not appear to be valid RTF"` |
| Pandoc failure | `ValueError` | `"Failed to convert RTF: {error}"` |

## Files to Create/Modify

| File | Action |
|------|--------|
| `pyproject.toml` | Add pypandoc dependency |
| `src/promptgrimoire/models/case.py` | Create `ParsedRTF` dataclass |
| `src/promptgrimoire/models/__init__.py` | Export `ParsedRTF` |
| `src/promptgrimoire/parsers/rtf.py` | Create `parse_rtf()` |
| `src/promptgrimoire/parsers/__init__.py` | Export `parse_rtf` |
| `tests/unit/test_rtf_parser.py` | Create tests |

## Verification

1. `uv sync` - install pypandoc
2. `uv run pytest tests/unit/test_rtf_parser.py -v` - all tests pass
3. `uv run ruff check . && uv run ruff format . && uvx ty check` - no errors
4. Manual: Inspect HTML output renders tables and formatting correctly
