---
name: debug-statements
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*test).*\.py$
  - field: new_text
    operator: regex_match
    pattern: \bprint\(|breakpoint\(\)|pdb\.set_trace\(\)|import\s+pdb
action: warn
---

**Debug Statement Detected in Production Code**

You're adding debug statements (`print()`, `breakpoint()`, `pdb`) to non-test code.

**Before committing:**
- [ ] Remove or convert to proper logging
- [ ] Use `logger.debug()` if logging is needed
- [ ] Debug statements can expose sensitive data

If this is intentional temporary debugging, remember to remove before committing.
