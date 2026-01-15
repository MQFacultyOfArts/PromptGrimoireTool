# Fix: CLI Fails When Invoked Manually Without stdin JSON

## Problem

The `claude-transcript-archive` CLI crashes with `JSONDecodeError` when run manually because it unconditionally reads JSON from stdin (line 245 in cli.py). The hook system provides this JSON automatically, but manual/interactive invocation has no fallback.

**Error:**
```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

## Root Cause

In [cli.py:245](src/claude_transcript_archive/cli.py#L245):
```python
payload = json.load(sys.stdin)
```

This line blocks waiting for JSON and fails when stdin is empty/TTY.

## Proposed Solution

Add command-line arguments `--transcript` and `--session-id` as alternatives to stdin, with stdin remaining the default for hook invocation.

### Changes to [cli.py](src/claude_transcript_archive/cli.py)

1. **Add new argparse arguments** (around line 220):
   ```python
   parser.add_argument("--transcript", help="Path to transcript file (alternative to stdin)")
   parser.add_argument("--session-id", help="Session ID (alternative to stdin)")
   ```

2. **Modify main() to support both input modes** (around line 245):
   ```python
   # Check for command-line arguments first
   if args.transcript and args.session_id:
       transcript_path = Path(args.transcript)
       session_id = args.session_id
   elif sys.stdin.isatty():
       # No stdin data and no CLI args
       log_error("No input provided. Either pipe JSON via stdin or use --transcript and --session-id", args.quiet)
       sys.exit(1)
   else:
       # Read from stdin (hook mode)
       try:
           payload = json.load(sys.stdin)
       except json.JSONDecodeError as e:
           log_error(f"Invalid JSON input: {e}", args.quiet)
           sys.exit(1)
       transcript_path = Path(payload.get("transcript_path", ""))
       session_id = payload.get("session_id", "")
   ```

### Update Documentation

Update [CLAUDE.md](CLAUDE.md) CLI usage section to document new arguments:
```
--transcript PATH  # Path to transcript file (use instead of stdin)
--session-id ID    # Session ID (use instead of stdin)
```

## Files to Modify

1. [src/claude_transcript_archive/cli.py](src/claude_transcript_archive/cli.py) - Add CLI arguments and input mode detection
2. [CLAUDE.md](CLAUDE.md) - Document new arguments

## Verification

1. **Test hook mode still works:** Ensure stdin JSON input continues to work
2. **Test manual mode:** Run `claude-transcript-archive --transcript /path/to/file.jsonl --session-id test123 --local --title "Test"`
3. **Test error handling:** Run without arguments and verify helpful error message
