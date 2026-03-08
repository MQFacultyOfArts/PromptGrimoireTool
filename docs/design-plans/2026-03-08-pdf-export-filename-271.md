# PDF Export Filename Convention Design

**GitHub Issue:** #271

## Summary
<!-- TO BE GENERATED after body is written -->

## Definition of Done
- The PDF export filename follows the format: `UnitCode_LastName_FirstName_ActivityName_WorkspaceTitle_YYYYMMDD.pdf`
- The filename is strictly limited to 100 characters.
- If the filename exceeds 100 characters, we use simple truncation: we truncate `WorkspaceTitle` first, and `ActivityName` second (only if necessary). `UnitCode`, `LastName`, `FirstName`, and Date are never truncated.
- Special characters are transliterated (e.g., using `unidecode` or similar logic), and spaces/punctuation are replaced with underscores to ensure Turnitin/Windows compatibility.

## Acceptance Criteria
<!-- TO BE GENERATED and validated before glossary -->

## Glossary
<!-- TO BE GENERATED after body is written -->
