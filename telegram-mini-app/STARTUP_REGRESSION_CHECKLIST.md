# Telegram Mini App Startup Regression Checklist

Use this checklist before and after startup/lifecycle changes. Capture the platform, Telegram client version, network profile, build SHA, and whether the run is a fresh install, repeat launch, background resume, BFCache restore, or full WebView recreation.

## 1. First launch Mini App
- **Steps:** Clear app/site storage, open the Mini App from the production bot button, wait for Home to render, then open Profile.
- **Expected result:** App leaves the startup state once, Home renders stable content, Profile opens without a recovery screen.
- **Network expectations:** One Telegram login request if no valid JWT exists, one `getProfile()`, one `getSubscription()`, and no duplicated bootstrap chain.
- **Storage expectations:** Auth token and expected app cache keys are created once; no recovery/catalog flags remain after successful Home startup.
- **Logs to watch:** `app_component_mounted`, `loadAppData_called`, `telegram_login_start`, `stored_token_profile_ok` or `fresh_profile_ok`, `bootstrap_done`, absence of repeated `bootstrapPromiseRef_created` for the same launch.

## 2. Repeat launch Mini App
- **Steps:** Complete a successful first launch, close Telegram Mini App, reopen it from the same bot entry point.
- **Expected result:** App starts from the stored authenticated state and renders Home without forced re-login unless the token is invalid.
- **Network expectations:** Prefer stored-token `getProfile()` and `getSubscription()`; Telegram login should not repeat when JWT is valid.
- **Storage expectations:** Existing token remains intact; no storage cleanup is triggered by active lifecycle events.
- **Logs to watch:** `stored_token_auth_ok` with `hasStoredAuthToken=true`, `loadAppData_called` once for initial launch, no active-event `resume` bootstrap.

## 3. Close while on Home
- **Steps:** Open Home, immediately close/minimize the Mini App, then reopen it.
- **Expected result:** Closing does not corrupt auth state; reopening reaches Home normally.
- **Network expectations:** Inactive event may abort in-flight catalog work only if it exists; reopen should not cascade login/bootstrap requests.
- **Storage expectations:** Auth token remains unless existing inactive invalidation intentionally clears only recovery-related keys; no new active-event cleanup occurs on reopen.
- **Logs to watch:** `webview_inactive`, optional `webview_active`, `telegram_viewport_prepare_called`, no `loadAppData_called` with `reason=resume`.

## 4. Close while on Club
- **Steps:** Open Club/catalog, wait for partner list or loading state, close/minimize, then reopen.
- **Expected result:** Club state recovers according to existing catalog recovery behavior without a startup deadlock.
- **Network expectations:** Catalog request may be aborted on inactive lifecycle; no forced auth/bootstrap starts from active lifecycle events.
- **Storage expectations:** Existing catalog recovery flag behavior is unchanged; active events do not add or clear storage.
- **Logs to watch:** `catalog_load_aborted_on_hide` when applicable, `webview_active`, `webview_resume_prepare_ok`, no `webview_resume_fresh_bootstrap_started`.

## 5. Close while catalog is loading
- **Steps:** Throttle network, open Club, close/minimize before partners finish loading, then reopen.
- **Expected result:** Existing catalog recovery UX appears if the load was interrupted; auth startup does not restart repeatedly.
- **Network expectations:** At most one interrupted partners request per close; no extra Telegram login caused by pageshow/focus/visible/resume/activated.
- **Storage expectations:** Catalog recovery flag behavior remains as before; no active lifecycle storage mutation.
- **Logs to watch:** `catalog_load_aborted_on_hide`, `catalog_recovery_flag_detected`, `webview_active`, absence of `loadAppData_called` with `reason=resume`.

## 6. Close while Telegram login is in progress
- **Steps:** Clear storage, throttle network, open Mini App, close/minimize during Telegram login, then reopen.
- **Expected result:** No competing login owners are created by active lifecycle events; later startup is handled by the normal initial bootstrap path.
- **Network expectations:** Avoid parallel Telegram login calls caused by active events; only explicit initial/retry/manual paths may authenticate.
- **Storage expectations:** No token is partially overwritten by active lifecycle handling; inactive behavior remains unchanged.
- **Logs to watch:** `telegram_login_start`, `webview_inactive`, `webview_active`, no active-event `bootstrapPromiseRef_cleared` or `loadAppData_called` with `reason=resume`.

## 7. Close while `getProfile()` is in progress
- **Steps:** Launch with valid token, throttle API, close/minimize during profile request, reopen.
- **Expected result:** Profile request ownership is not replaced by active lifecycle events; UI does not oscillate between loading and recovery.
- **Network expectations:** No duplicate profile request caused by pageshow/focus/visible/resume/activated.
- **Storage expectations:** Stored JWT remains unchanged by active lifecycle events.
- **Logs to watch:** `stored_token_profile_start`, `webview_active`, `loadAppData_post_auth_isActive_guard_return` only if inactive invalidation occurred, no forced resume bootstrap.

## 8. Close while `getSubscription()` is in progress
- **Steps:** Launch with valid token, throttle API, close/minimize during subscription request, reopen.
- **Expected result:** Subscription load does not spawn a second active-event bootstrap sequence.
- **Network expectations:** No duplicate subscription request from active lifecycle events.
- **Storage expectations:** No active-event storage cleanup; token remains consistent.
- **Logs to watch:** `stored_token_subscription_start`, `webview_inactive`, `webview_active`, no `loadAppData_called` with `reason=resume`.

## 9. Slow internet
- **Steps:** Use slow 3G throttling, perform first launch, repeat launch, Home to Club navigation, and background/foreground once.
- **Expected result:** Slow requests may show loading/recovery UI, but active lifecycle events remain passive.
- **Network expectations:** Requests are slow but not multiplied by focus/pageshow/visible/resume/activated.
- **Storage expectations:** No active-event storage mutation; existing timeout/recovery behavior remains unchanged.
- **Logs to watch:** `bootstrap_timeout`, `bootstrap_hard_timeout` if applicable, `webview_active`, absence of resume forced bootstrap logs.

## 10. Network loss
- **Steps:** Start the app, disable network during bootstrap or catalog load, restore network, then use existing retry/manual flows.
- **Expected result:** Errors are shown through existing paths; foregrounding the app does not silently force auth/bootstrap.
- **Network expectations:** Failed requests remain bounded; retries happen only through existing user/manual/retry mechanisms.
- **Storage expectations:** No active lifecycle cleanup; token is not removed by foreground events.
- **Logs to watch:** `bootstrap_fail`, request-specific fail traces, `webview_active`, no active-event `telegram_login_start`.

## 11. Expired JWT
- **Steps:** Seed storage with an expired/invalid JWT, open Mini App, wait for auth recovery.
- **Expected result:** Existing 401 handling clears the invalid token and performs Telegram login once.
- **Network expectations:** One failed stored-token profile/subscription path, then one Telegram login and fresh profile/subscription requests.
- **Storage expectations:** Expired token is cleared only by existing 401 logic; a fresh token is stored after successful login.
- **Logs to watch:** `stored_token_auth_fail`, `telegram_login_start`, `fresh_profile_ok`, `fresh_subscription_ok`, no duplicate login from active events.

## 12. Empty storage
- **Steps:** Clear localStorage/sessionStorage and launch from Telegram.
- **Expected result:** Normal first-launch login path completes.
- **Network expectations:** One Telegram login, then core profile/subscription requests.
- **Storage expectations:** Required auth storage is created; no recovery flags remain after a clean startup.
- **Logs to watch:** `hasStoredAuthToken=false`, `telegram_login_start`, `bootstrap_done`, no repeated bootstrap on focus/pageshow.

## 13. Old storage
- **Steps:** Populate storage with keys from an older build, launch the current Mini App, navigate Home/Profile/Club.
- **Expected result:** Existing cleanup/migration behavior remains intact and startup completes without active-event forced bootstrap.
- **Network expectations:** Stored-token path is used if valid; invalid-token path follows existing 401 recovery.
- **Storage expectations:** Only existing cleanup paths mutate stale keys; active lifecycle events do not clear or add storage.
- **Logs to watch:** `stale_state_cleanup_start`, `stale_state_cleanup_ok`, `webview_active`, no `reason=resume` bootstrap.

## 14. Return from background
- **Steps:** Open Home, background Telegram for 10-30 seconds, return to the Mini App.
- **Expected result:** Foreground event logs diagnostics and refreshes viewport only; it does not restart auth/bootstrap.
- **Network expectations:** No new login/profile/subscription requests solely because the app became active.
- **Storage expectations:** No active-event storage mutation.
- **Logs to watch:** `pageshow`, `focus`, `visibilitychange`, `webview_active`, `telegram_viewport_prepare_finished`, no `loadAppData_called` with `reason=resume`.

## 15. Full WebView destruction
- **Steps:** Force-close Telegram or destroy the WebView, then open the Mini App again.
- **Expected result:** New app process runs normal initial bootstrap once.
- **Network expectations:** One initial bootstrap sequence for the recreated WebView; no extra active-event forced bootstrap after mount.
- **Storage expectations:** Persisted token is reused if valid; no active-event cleanup occurs.
- **Logs to watch:** New `app_component_mounted`, one `loadAppData_called` with initial reason, no active-event forced bootstrap.

## 16. BFCache / `pageshow.persisted`
- **Steps:** On a platform/browser supporting BFCache, navigate away or background so `pageshow.persisted=true` fires on return.
- **Expected result:** BFCache restore refreshes viewport/diagnostics only and does not reset bootstrap ownership.
- **Network expectations:** No auth/profile/subscription/catalog bootstrap request is started solely from persisted pageshow.
- **Storage expectations:** No active-event storage mutation.
- **Logs to watch:** `pageshow` with `persisted=true`, `webview_active`, `webview_resume_prepare_ok`, no `bootstrapSequenceRef_updated` with `reason=resume`.

## 17. Android Telegram
- **Steps:** Test first launch, background/foreground, Club loading close, and repeat launch in Android Telegram.
- **Expected result:** Android lifecycle events do not trigger forced auth/bootstrap.
- **Network expectations:** No request multiplication from Android `activated`, `focus`, or `visibilitychange=visible` events.
- **Storage expectations:** Token and recovery storage behavior matches existing non-active paths.
- **Logs to watch:** `telegram_activated` via `webview_active`, `visibilitychange`, `webview_resume_prepare_ok`, no `reason=resume` bootstrap.

## 18. iOS Telegram
- **Steps:** Test first launch, app switcher background/foreground, BFCache-like restore if observed, and repeat launch in iOS Telegram.
- **Expected result:** iOS foreground events remain passive and do not reset UI/auth state.
- **Network expectations:** No duplicate login/profile/subscription requests from iOS foreground events.
- **Storage expectations:** Stored token remains stable across foregrounding.
- **Logs to watch:** `pageshow`, `focus`, `telegram_activated`, `webview_active`, no `webview_active_bootstrap_reset`.

## 19. Desktop Telegram
- **Steps:** Open Mini App in Desktop Telegram, switch chats/windows, minimize/restore, repeat launch.
- **Expected result:** Desktop focus/activated events do not start forced bootstrap.
- **Network expectations:** No active-event login/bootstrap requests when the window regains focus.
- **Storage expectations:** No active-event storage cleanup.
- **Logs to watch:** `focus`, `telegram_activated`, `webview_active`, `telegram_viewport_prepare_finished`, no `loadAppData_called` with `reason=resume`.

## 20. No cascading login/bootstrap requests
- **Steps:** With devtools/network open, rapidly switch background/foreground 5-10 times during loading and after Home renders.
- **Expected result:** Bootstrap promise ownership is not reset by active events; no cascade of competing auth sequences appears.
- **Network expectations:** Active events must not create additional Telegram login, profile, subscription, or forced bootstrap requests.
- **Storage expectations:** No storage churn on foreground events.
- **Logs to watch:** Count `bootstrapPromiseRef_created`, `bootstrapSequenceRef_updated`, `telegram_login_start`, and ensure none are caused by active lifecycle `reason=resume`.

## 21. Club / partners / partner card / offers
- **Steps:** Open Club, load partners, open a partner card, load offers, background/foreground, return to Club.
- **Expected result:** Existing catalog and offers behavior remains unchanged; active lifecycle does not reset partner flow.
- **Network expectations:** Partner/offers requests occur from navigation or existing catalog logic only, not from foreground lifecycle events.
- **Storage expectations:** Existing catalog recovery behavior unchanged; no active-event storage mutation.
- **Logs to watch:** `catalog_return`, partner/offers diagnostics, `webview_active`, no `partner_flow_reset_start` caused by active event.

## 22. Home / Profile / Subscription / CMS content
- **Steps:** Open Home, Profile, subscription UI, and CMS-backed content; background/foreground from each screen.
- **Expected result:** Screen content remains stable after active lifecycle events and does not jump back to loading/Home unexpectedly.
- **Network expectations:** No auth/bootstrap repeat from foregrounding; CMS/content requests remain tied to existing screen behavior.
- **Storage expectations:** No active-event token or app-state storage changes.
- **Logs to watch:** `webview_active`, screen-specific content traces, no `stale_state_cleanup_start` or `loadAppData_called` with `reason=resume` after foregrounding.
