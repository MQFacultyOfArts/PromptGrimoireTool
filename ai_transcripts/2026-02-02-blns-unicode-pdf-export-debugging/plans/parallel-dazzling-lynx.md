# Plan: Fix Azure IP Ranges Cache Not Found

## Problem

Production server shows: `"Azure IP ranges cache not found"`

**Root Cause**: The `data/` directory is in `.gitignore` (line 12), so `data/ip-ranges/azure_service_tags.json` (4.3 MB) is never committed to git and doesn't exist on production.

## Solution

Track the IP ranges file in git while keeping `data/` ignored for other purposes (student audio files, etc.).

### Files to Modify

1. **[.gitignore](.gitignore)** - Add exception for ip-ranges directory
2. **Commit** - Stage and commit the azure_service_tags.json file

### Changes

**.gitignore** - Change:
```diff
 data/
+!data/ip-ranges/
```

This keeps `data/` ignored (for audio recordings, etc.) but explicitly tracks `data/ip-ranges/`.

### Verification

1. After the change, verify the file is tracked: `git status data/ip-ranges/`
2. Deploy to production
3. Check logs - warning should no longer appear
