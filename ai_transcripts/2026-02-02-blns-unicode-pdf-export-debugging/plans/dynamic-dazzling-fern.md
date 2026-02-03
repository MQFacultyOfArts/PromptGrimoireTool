# Plan: Extract Transcript from Teams HTML

## Goal
Extract the transcript from the Teams meeting HTML file into a clean markdown format.

## Structure Analysis
The HTML contains transcript entries in this structure:
- Each entry is in a `div.listItemWithSpeaker-246`
- Speaker + timestamp in `aria-label` attribute on `div.baseEntry-372` (e.g., "Brian Ballsun-Stanton 38 minutes 32 seconds")
- Transcript text in `div.entryText-373`

## Implementation
Create a Python script using BeautifulSoup (via uv):

```python
# extract_transcript.py
from bs4 import BeautifulSoup
import re
import sys

def extract_transcript(html_path):
    with open(html_path, 'r') as f:
        soup = BeautifulSoup(f, 'html.parser')

    entries = soup.find_all('div', class_=re.compile(r'baseEntry-\d+'))

    lines = []
    for entry in entries:
        aria = entry.get('aria-label', '')
        # Parse "Name X minutes Y seconds" or similar
        text_div = entry.find('div', class_=re.compile(r'entryText-\d+'))
        if text_div:
            lines.append(f"**{aria}**\n{text_div.get_text()}\n")

    return '\n'.join(lines)
```

Setup:
```bash
uv add beautifulsoup4 lxml
```

Run with: `uv run python extract_transcript.py transcripts/20260120-bbs-mk-jk.html`

## Files
- Input: `transcripts/20260120-bbs-mk-jk.html`
- Output: `transcripts/20260120-bbs-mk-jk.md`
- Script: `extract_transcript.py` (new file)

## Verification
Run the script and verify the markdown output contains readable transcript with speaker names, timestamps, and text.
