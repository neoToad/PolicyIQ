# Current Task

**Step**: Phase 5.5 — Add rate limiting (in progress, interrupted)
**Status**: Implementation partially complete, debugging a throttle test issue

## What was done
- Created `documents/throttles.py` with `UploadAnonRateThrottle` (scope `upload_anon`) and `UploadUserRateThrottle` (scope `upload_user`)
- Created `queries/throttles.py` with `QueryAnonRateThrottle` (scope `query_anon`) and `QueryUserRateThrottle` (scope `query_user`)
- Added `THROTTLE_QUERY_ANON`, `THROTTLE_QUERY_USER`, `THROTTLE_UPLOAD_ANON`, `THROTTLE_UPLOAD_USER` env-overridable settings in `settings.py` (defaults: 30/h, 120/h, 5/h, 30/h)
- Added `DEFAULT_THROTTLE_RATES` to `REST_FRAMEWORK` config in `settings.py`
- Applied `throttle_classes` to `DocumentUploadAPIView` (upload) and `QueryAPIView` (query)
- Health check (`HealthCheckAPIView`) left without throttles so monitors can poll freely
- Updated `.env` and `.env.example` with new throttle env vars
- Added throttle tests in both `documents/tests/test_views.py` (`UploadThrottleTests`) and `queries/tests/test_views.py` (`QueryThrottleTests`)

## Blocked on
The throttle tests are failing — DRF's `APISettings.DEFAULT_THROTTLE_RATES` is being reloaded by `override_settings`, but when a `SimpleRateThrottle` instance is created inside the override, `self.THROTTLE_RATES` still holds the stale value (likely because `THROTTLE_RATES` is a class attribute populated at class-definition time, not a dynamic lookup).

Need to investigate:
- Why `THROTTLE_RATES` on the throttle class doesn't reflect `override_settings(REST_FRAMEWORK={...})`
- Possible fix: ensure the test sets a low rate without relying on `override_settings` for the throttle rates (e.g., set the env var, or directly patch the throttle class's `THROTTLE_RATES` dict, or mock `allow_request`)
- Test `test_health_check_is_not_throttled` failed because `APIView.throttle_classes` default is `[]`, not `()`. Need to update assertion to `[]`.

## Files modified (uncommitted)
- `policyiq/policyiq/settings.py` (THROTTLE_* vars, REST_FRAMEWORK throttle rates)
- `policyiq/policyiq/.env`, `policyiq/policyiq/.env.example` (new env vars)
- `policyiq/documents/throttles.py` (new)
- `policyiq/queries/throttles.py` (new)
- `policyiq/documents/views.py` (throttle_classes on `DocumentUploadAPIView`)
- `policyiq/queries/views.py` (throttle_classes on `QueryAPIView`)
- `policyiq/documents/tests/test_views.py` (`UploadThrottleTests` class)
- `policyiq/queries/tests/test_views.py` (`QueryThrottleTests` class + `override_settings` import)

## Next step on resume
1. Fix the throttle rate refresh issue in tests — likely by directly patching `THROTTLE_RATES` on the class or by using a different test strategy
2. Fix the `test_health_check_is_not_throttled` assertion (`[]` not `()`)
3. Re-run all tests, confirm 89+ pass with the new throttle tests
4. Update CHANGELOG and CURRENT_TASK, commit as `[Phase5.5]`
5. Move to Phase 5.6 (pre-commit hooks) — the last remaining item
