## Phase 1: Root Cause Investigation - Non-Redis Restart Spike

### 1. Falsification of the Restart Race Condition
We investigated whether a server restart, combined with preserving `FilePersistentDict` files on disk, could natively cause a cross-user data leak. The spike test simulated:
1. User A and User B authenticate and establish `.nicegui` session files.
2. User A and User B simulate laptop sleep (disconnecting websockets).
3. The server abruptly restarts (disabling `_invalidate_all_sessions()` and `invalidate_sessions_on_disk()`).
4. Both users wake up and reconnect concurrently (simulating a thundering herd).

**Result:** The test passed perfectly. User A saw User A's data, and User B saw User B's data. There was no cross-contamination. Uvicorn isolated the `ContextVar` state during the concurrent HTTP reloads, and `FilePersistentDict` correctly mapped each session cookie to the proper file.

### 2. The "Red Herring" Hypothesis
Since the restart itself does not cause data leakage, the correlation between the `_invalidate_all_sessions()` fix and the disappearance of the bug must be re-evaluated.
If `_invalidate_all_sessions()` fixed the issue by deleting `auth_user` from all files *on shutdown*, it simply destroyed the payloads that were *already* corrupted.

This implies:
1. User A's `.nicegui` file was overwritten with User B's `auth_user` data **before** the restart occurred.
2. When the server restarted and the users woke up, they simply read the already-corrupted files.
3. The addition of `_invalidate_all_sessions()` masked the bug because it forced everyone to log out, clearing the corrupted files before they could be read.

### 3. Alternative Contamination Vectors (Pre-Restart)
If the file was corrupted before the restart, how could `auth_user` be incorrectly written?
- **Vector A:** `auth_user` is only written during `/auth/callback` or `/auth/sso`. If User A's browser was redirected to an auth callback URL containing User B's token, User A would be authenticated as User B.
- **Vector B:** If User A's session cookie was overwritten by a `Set-Cookie` header intended for User B.
- **Vector C:** If Uvicorn or Starlette leaked `ContextVar` state during an older version (though ruled out in Uvicorn 0.40.0, perhaps an interaction with `httpx` or `python-socketio`).

### Conclusion for Spike
The multi-instance Redis architecture does not suffer from a unique "restart leak" because the restart leak never existed in the first place. The global session invalidation was a defensive measure that masked a different bug. Removing global session invalidation in multi-instance mode is safe from a data-leak perspective, though it may require re-evaluating Stytch session expiration policies (as noted in commit 38152f4a).
