# Test Requirements: Lag-Based Admission Gate (#459)

## Overview

Maps every acceptance criterion from the design plan to specific tests, test types, file locations, implementation phases, and verification method.

**Convention:** All test files live under `tests/unit/` unless otherwise noted. The admission gate is pure in-memory logic with no database dependency, so no integration tests are needed. E2E tests are identified only where browser-level verification is required.

---

## AC1: Cap adjusts dynamically based on event loop lag

| Criterion | Text | Test type | Test file | Phase | Verification |
|---|---|---|---|---|---|
| AC1.1 | Cap increases by `batch_size` when lag < `lag_increase_ms` and admitted count >= cap - batch_size | unit | `tests/unit/test_admission.py` | 1 | Automated. Create state with initial_cap=20, batch_size=20. Call `update_cap(lag_ms=5.0, admitted_count=15)`. Assert cap == 40. |
| AC1.2 | Cap unchanged when lag is between `lag_increase_ms` and `lag_decrease_ms` (hysteresis band) | unit | `tests/unit/test_admission.py` | 1 | Automated. Call `update_cap(lag_ms=30.0, admitted_count=15)`. Assert cap unchanged. |
| AC1.3 | Cap halves when lag > `lag_decrease_ms` | unit | `tests/unit/test_admission.py` | 1 | Automated. Set cap to 100. Call `update_cap(lag_ms=60.0, admitted_count=50)`. Assert cap == 50. |
| AC1.4 | After restart, cap starts at `initial_cap` and ramps up naturally via AIMD as lag stays low | unit | `tests/unit/test_admission_restart.py` | 5 | Automated. Create state, modify cap to 100, enqueue users, create tickets. Call `clear()`. Assert cap == initial_cap, queue empty, tokens empty, tickets empty. Also verify `init_admission()` starts at initial_cap and repeated low-lag `update_cap` calls ramp up by batch_size. |
| AC1.5 | Cap never drops below `initial_cap` even under sustained high lag | unit | `tests/unit/test_admission.py` | 1 | Automated. Set cap to initial_cap (20). Call `update_cap(lag_ms=60.0, ...)` repeatedly. Assert cap stays at 20. |
| AC1.6 | Cap does not increase when admitted count is well below current cap (no speculative growth) | unit | `tests/unit/test_admission.py` | 1 | Automated. Cap is 100, admitted is 10 (well below 100-20=80). Call `update_cap(lag_ms=5.0, admitted_count=10)`. Assert cap unchanged. |

---

## AC2: FIFO queue with batch admission and entry tickets

| Criterion | Text | Test type | Test file | Phase | Verification |
|---|---|---|---|---|---|
| AC2.1 | Users arriving when at cap are added to queue in arrival order and receive an opaque queue token (UUID4) | unit | `tests/unit/test_admission.py` | 1 | Automated. Enqueue 3 users. Verify tokens returned are non-empty strings. Verify internal queue order matches insertion order. |
| AC2.2 | When cap rises above admitted count, queued users are popped in FIFO order up to available capacity and granted entry tickets | unit | `tests/unit/test_admission.py` | 1 | Automated. Enqueue 3, call `admit_batch(admitted_count=0)` with cap=2. Verify first 2 popped, third remains. Verify popped users have entries in `_tickets`. |
| AC2.3 | Batch admission admits multiple users per diagnostic cycle (not one-at-a-time) | unit | `tests/unit/test_admission.py` | 1 | Automated. Enqueue 5, cap=5, `admit_batch(admitted_count=0)`. Verify all 5 admitted in one call (return list length == 5). |
| AC2.4 | Users in queue longer than `queue_timeout_seconds` are dropped from queue | unit | `tests/unit/test_admission.py` | 1 | Automated. Enqueue user, mock `time.monotonic` to advance past `queue_timeout_seconds`. Call `sweep_expired()`. Verify user removed from queue, `_enqueue_times`, `_tokens`, and `_user_tokens`. |
| AC2.5 | User already in queue is not double-enqueued on subsequent page loads -- same token returned, same position preserved | unit | `tests/unit/test_admission.py` | 1 | Automated. Enqueue same user_id twice. Verify same token returned, queue length is 1. |
| AC2.6 | Admitted user holds an entry ticket valid for `ticket_validity_seconds`; page_route consumes the ticket on first page load | unit | `tests/unit/test_admission.py` | 1 | Automated. Enqueue, admit. Verify `try_enter(user_id)` returns True. Call `try_enter` again -- returns False (consumed). |
| AC2.7 | User who closes tab and returns while still in queue sees their existing queue position (not re-queued at back) | unit | `tests/unit/test_admission.py` | 1 | Automated. Same test as AC2.5 -- second `enqueue()` returns same token, position unchanged. |
| AC2.8 | User who closes tab and returns after batch admission (ticket still valid) passes through gate directly | unit | `tests/unit/test_admission.py` | 1 | Automated. Enqueue, admit (ticket created), then `try_enter()` returns True (simulates returning from coffee). |
| AC2.9 | User who returns after ticket expires is treated as a fresh arrival | unit | `tests/unit/test_admission.py` | 1 | Automated. Enqueue, admit, advance mock time past `ticket_validity_seconds`. `try_enter()` returns False. |

---

## AC3: Gate only affects new authenticated users

| Criterion | Text | Test type | Test file | Phase | Verification |
|---|---|---|---|---|---|
| AC3.1 | User already in `client_registry._registry` passes through gate freely | unit | `tests/unit/test_admission_gate.py` | 3 | Automated. Mock `_registry` to contain user_id. Verify gate function returns False (pass through), no redirect called. |
| AC3.2 | Privileged users (`is_privileged_user`) bypass gate regardless of cap | unit | `tests/unit/test_admission_gate.py` | 3 | Automated. Mock empty registry, no ticket, `is_privileged_user` returns True. Verify gate returns False. |
| AC3.3 | New authenticated user redirected to `/queue?t=<token>&return=<url>` when admitted count >= cap | unit | `tests/unit/test_admission_gate.py` | 3 | Automated. Mock empty registry, no ticket, not privileged, at cap. Verify `enqueue()` called and `ui.navigate.to` called with URL matching `/queue?t=...&return=...`. |
| AC3.4 | User who disconnects and reconnects within 15s `reconnect_timeout` remains in `_registry` and is not gated | unit + human | `tests/unit/test_admission_gate.py` | 3, 5 | Automated (gate side): AC3.1 test covers gate pass-through when in `_registry`. Human: NiceGUI lifecycle timing (see below). |
| AC3.5 | User with valid entry ticket passes through gate; ticket is consumed on use | unit | `tests/unit/test_admission_gate.py` | 3 | Automated. Mock empty registry, `try_enter` returns True. Verify gate returns False (pass through, ticket consumed). |
| AC3.6 | User still in queue is redirected to `/queue?t=<existing_token>` preserving their position | unit | `tests/unit/test_admission_gate.py` | 3 | Automated. Mock empty registry, no ticket, not privileged, at cap, user already in queue. Verify redirect URL uses the existing token from `_user_tokens`. |

---

## AC4: Queue page is lightweight and functional

| Criterion | Text | Test type | Test file | Phase | Verification |
|---|---|---|---|---|---|
| AC4.1 | Queue page shows user's position and total queue size | unit + human | `tests/unit/test_queue_page.py` | 4 | Automated: verify HTML contains `id="position"` element. Human: visual confirmation of rendered position text. |
| AC4.2 | Queue page polls `/api/queue/status?t=<token>` every 5s and redirects on admission | unit + human | `tests/unit/test_queue_page.py` | 4 | Automated: verify HTML contains polling JS. Human: browser-level poll + redirect cycle. |
| AC4.3 | `/api/queue/status?t=<token>` returns `{position, total, admitted, expired}` JSON | unit | `tests/unit/test_queue_status_api.py` | 4 | Automated. Three sub-cases: queued, admitted, expired/invalid. |
| AC4.4 | Invalid or missing token returns `{admitted: false, expired: true}` | unit | `tests/unit/test_queue_status_api.py` | 4 | Automated. Call with invalid token and no token. Verify response. |
| AC4.5 | Queue page is raw Starlette HTML -- zero NiceGUI overhead | unit | `tests/unit/test_queue_page.py` | 4 | Automated. Verify response is HTMLResponse, no NiceGUI imports in handler. |
| AC4.6 | Queue page shows "your place has expired" with rejoin link when `expired: true` | unit + human | `tests/unit/test_queue_page.py` | 4 | Automated: verify HTML contains `id="expired"` div with rejoin link. Human: visual confirmation. |

---

## AC5: Admission state visible in diagnostic logs

| Criterion | Text | Test type | Test file | Phase | Verification |
|---|---|---|---|---|---|
| AC5.1 | `memory_diagnostic` structlog event includes `admission_cap`, `admission_admitted`, `admission_queue_depth`, `admission_tickets` | unit | `tests/unit/test_admission_diagnostics.py` | 2 | Automated. Mock admission state with known values. Execute diagnostic cycle logic. Assert all four fields present with correct values. |
| AC5.2 | All config values configurable via env vars | unit | `tests/unit/test_admission.py` | 1 | Automated. Verify `AdmissionConfig` fields have correct defaults. Verify `Settings.admission` sub-model exists. |

---

## Security tests

| Test | Test type | Test file | Phase | Verification |
|---|---|---|---|---|
| XSS: token containing `</script>` is JSON-escaped | unit | `tests/unit/test_queue_page.py` | 4 | Automated |
| Open-redirect: `return=javascript:alert(1)` defaults to `/` | unit | `tests/unit/test_queue_page.py` | 4 | Automated |
| Open-redirect: `return=//evil.com` defaults to `/` | unit | `tests/unit/test_queue_page.py` | 4 | Automated |
| Open-redirect: `return=https://evil.com` defaults to `/` | unit | `tests/unit/test_queue_page.py` | 4 | Automated |

---

## Test file summary

| Test file | Phase | AC coverage | Test count (approx) |
|---|---|---|---|
| `tests/unit/test_admission.py` | 1 | AC1.1-AC1.6, AC2.1-AC2.9, AC5.2 | ~18 |
| `tests/unit/test_admission_diagnostics.py` | 2 | AC5.1 | ~2 |
| `tests/unit/test_admission_gate.py` | 3 | AC3.1-AC3.6 | ~6 |
| `tests/unit/test_queue_status_api.py` | 4 | AC4.3, AC4.4 | ~4 |
| `tests/unit/test_queue_page.py` | 4 | AC4.1, AC4.2, AC4.5, AC4.6 + security | ~8 |
| `tests/unit/test_admission_restart.py` | 5 | AC1.4 | ~3 |
| **Total** | | | **~41** |

---

## Human verification items

| Criterion | Why human verification needed | What to check | Automated coverage |
|---|---|---|---|
| AC3.4 (reconnect grace period) | The 15s `reconnect_timeout` is a NiceGUI framework property. Gate pass-through when in `_registry` is unit-tested, but the framework's client lifecycle timing requires a real browser. | Open page, disconnect network <15s, reconnect. Verify no queue redirect. Disconnect >15s, navigate. Verify gated if at cap. | Gate pass-through is automated (AC3.1). |
| AC4.1 (position display) | Unit test verifies HTML element exists, not that polling JS updates it correctly. | With user queued, verify rendered position text updates ("position 3 of 5"). | HTML structure verified. |
| AC4.2 (polling redirect) | Unit test verifies JS source, not browser execution. | Wait for batch admission. Verify auto-redirect to original page. | JS structure verified. |
| AC4.6 (expired state display) | HTML structure verified, JS show/hide needs browser. | Let token expire. Verify expired message and rejoin link. | HTML and JS branching verified. |
| AC1.4 (real-world ramp) | Unit tests verify AIMD arithmetic; real ramp depends on actual event loop lag under load. | Monitor diagnostic logs after restart. Verify cap ramps from `initial_cap`. | Arithmetic fully unit-tested. |

**Recommendation:** AC4.1, AC4.2, and AC4.6 can be covered by a single `@pytest.mark.noci` Playwright E2E test in `tests/e2e/test_admission_queue.py` that configures `initial_cap=1, batch_size=1`, fills the cap, queues a second user, verifies position display, frees a slot, and verifies auto-redirect. This converts 3 of 5 human items to automated, run in the nightly `e2e slow` lane.
