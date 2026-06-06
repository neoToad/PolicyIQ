# Current Task

**Step**: Phase 5.5 — Add rate limiting (resuming from WIP state)
**Status**: Diagnosing and fixing 4 failing tests; implementation is in place

## Active work
The rate limiting implementation is complete (throttles, settings, throttle_classes applied to views), but 4 tests fail. Working through them in order:

### Failure 1: `test_health_check_is_not_throttled` — `[]` vs `()`
`HealthCheckAPIView.throttle_classes` defaults to `[]` (mutable list), not `()`. Fix the assertion to `[]` — actually, set it explicitly to `[]` on the class for clarity.

### Failure 2: `test_authenticated_user_is_throttled_after_limit` (query) — third request gets 200 not 429
DRF's `SimpleRateThrottle` caches `THROTTLE_RATES` at class-definition time. `override_settings(REST_FRAMEWORK=...)` only reloads `api_settings`, but the throttle class's `THROTTLE_RATES` is the populated dict from class definition, not a dynamic lookup. Need a different test strategy:
- Either directly patch the throttle class's `THROTTLE_RATES` and `rate` attributes, or
- Use `mock.patch.object` to patch `allow_request` to return True/False, or
- Use the `cache.clear()` strategy combined with a low default rate env var.

Cleanest fix: set the test to directly patch `THROTTLE_RATES` and `rate` on the throttle class. Tests with `override_settings` are unreliable here.

### Failure 3: `test_authenticated_user_is_throttled_after_limit` (upload) — third request gets 201 not 429
Same root cause as Failure 2.

### Failure 4: `test_anonymous_requests_are_throttled_via_upload_anon_scope` — first request returns 500 not 401/403
The throttle check runs before permission_classes, but the throttle fails to get a "throttle rate" lookup. Probably because the throttle's `THROTTLE_RATES` is stale (same issue as 2/3), or because the mock-storage layer fails. Likely the throttle consumes the slot but then DRF's allow_request on a stale rate says "go ahead", the storage write fails somewhere. Need to investigate.

## Plan
1. Fix the `[]` vs `()` assertion (1-line fix).
2. Refactor the throttle tests to use `mock.patch.object` on the throttle class's `THROTTLE_RATES` and `rate` directly, OR a more robust strategy that exercises `allow_request` returning False.
3. Verify all 95 tests pass.
4. Commit Phase 5.5 and update CHANGELOG.

## Next step after Phase 5.5
Phase 5.6 — Add pre-commit hooks (`.pre-commit-config.yaml` with ruff).
