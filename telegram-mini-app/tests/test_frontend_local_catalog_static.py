from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
CLIENT = (ROOT / "src/api/client.ts").read_text(encoding="utf-8")
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
PARTNER_PAGE = (ROOT / "src/pages/PartnerPage.tsx").read_text(encoding="utf-8")
PARTNER_DISPLAY = (ROOT / "src/utils/partnerDisplay.ts").read_text(encoding="utf-8")


def test_feature_flag_false_keeps_web_legacy_catalog_endpoints() -> None:
    assert 'WEB_CATALOG_PARTNERS_PATH = "/clients/catalog/partners"' in CLIENT
    assert 'web_legacy_catalog' in CLIENT
    assert ': `/clients/partners/${partnerId}/offers`' in CLIENT
    assert '`/clients/partners/${partnerId}/verify`' in CLIENT


def test_feature_flag_true_uses_tg_local_catalog_endpoints() -> None:
    assert 'TG_LOCAL_CATALOG_ENABLED' in CLIENT
    assert 'TG_CATALOG_PARTNERS_PATH = "/api/tg/partners"' in CLIENT
    assert 'tg_local_catalog' in CLIENT
    assert 'getSafeRequestTarget(path, apiBase)' in CLIENT
    assert 'fetch(target.url' in CLIENT
    assert '`/api/tg/partners/${partnerId}/offers`' in CLIENT


def test_tg_catalog_absolute_base_url_and_fallback() -> None:
    assert 'VITE_TG_API_BASE_URL' in CLIENT
    assert 'const TG_API_BASE_URL = normalizeTgApiBaseUrl(' in CLIENT
    assert 'import.meta.env.VITE_TG_API_BASE_URL' in CLIENT
    assert 'window.location.origin' in CLIENT
    assert 'if (!TG_API_BASE_URL)' in CLIENT
    assert 'return normalizedPath;' in CLIENT
    assert 'getTgApiUrl(path)' in CLIENT
    assert 'requestUrl: target.url' in CLIENT


def test_tg_catalog_endpoints_share_tg_absolute_request_target() -> None:
    for endpoint in [
        '/api/tg/partners',
        '`/api/tg/partners/${partnerId}/offers`',
        '`/api/tg/partners/${partnerId}/offers/${offerId}/verify`',
        '/api/tg/me/verifications',
        '/api/tg/me/savings',
    ]:
        assert endpoint in CLIENT
    assert 'TG_LOCAL_CATALOG_ENABLED ? "tg" : "web"' in CLIENT
    assert '''request<unknown>(
      "/api/tg/me/verifications",
      { retry: true },
      "tg",
    )''' in CLIENT
    assert '''request<SavingsSummary>("/api/tg/me/savings", { retry: true }, "tg")''' in CLIENT or '''request<SavingsSummary>(
      "/api/tg/me/savings",
      { retry: true },
      "tg",
    )''' in CLIENT
    assert '''request<Verification>(
      `/api/tg/partners/${partnerId}/offers/${offerId}/verify`,
      { method: "POST" },
      "tg",
    )''' in CLIENT


def test_tg_image_url_normalization_preserves_absolute_and_uses_tg_origin_for_relative() -> None:
    assert 'if (!trimmed || /^https?:\\/\\//i.test(trimmed))' in CLIENT
    assert 'return trimmed;' in CLIENT
    assert 'getSafeRequestTarget("/", apiBase)' in CLIENT
    assert 'target.requestOrigin' in CLIENT
    assert 'file_path' in CLIENT
    assert "field(value, 'file_path')" in PARTNER_DISPLAY


def test_verify_uses_tg_endpoint_and_controlled_errors_are_soft() -> None:
    assert '`/api/tg/partners/${partnerId}/offers/${offerId}/verify`' in CLIENT
    assert 'Получение кода для Telegram-каталога скоро будет доступно.' in PARTNER_PAGE
    assert 'access_check_not_configured' in PARTNER_PAGE


def test_web_identity_endpoints_still_use_web_client_paths() -> None:
    for endpoint in [
        '/auth/telegram-miniapp-login',
        '/clients/me',
        '/clients/me/subscription',
        '/clients/me/trial-subscription',
        '/clients/me/linking-status',
        '/clients/me/linking/start',
        '/clients/me/linking/confirm',
    ]:
        assert endpoint in CLIENT
    assert 'DEFAULT_API_BASE_URL = "https://bloomclub.ru/api/v1"' in CLIENT
    assert 'webIdentityClient' in CLIENT
    assert 'tgCatalogClient' in CLIENT


def test_verifications_savings_controlled_empty_state_and_no_secret_diagnostics() -> None:
    assert '/api/tg/me/verifications' in CLIENT
    assert '/api/tg/me/savings' in CLIENT
    assert 'caughtError.status === 501 || caughtError.status === 401' in CLIENT
    assert 'Привилегии Telegram-каталога скоро появятся.' in APP
    assert 'Экономия Telegram-каталога скоро появится.' in APP
    diagnostics_section = CLIENT[CLIENT.index('export interface CatalogErrorDiagnostic'):CLIENT.index('export class CatalogLoadError')]
    for secret in ['initData', 'hash', 'access_token', 'Authorization', 'TELEGRAM_ADMIN_API_TOKEN', 'TELEGRAM_APP_DATABASE_URL']:
        assert secret not in diagnostics_section


def test_empty_tg_partners_state_is_not_error_text() -> None:
    catalog_page = (ROOT / "src/pages/CatalogPage.tsx").read_text(encoding="utf-8")
    assert 'Мы скоро добавим новых партнёров' in catalog_page
    assert 'А пока сохраняйте настроение Bloom Club' in catalog_page
    empty_section = catalog_page[catalog_page.index('catalog-empty-state'):catalog_page.index('cards-grid catalog-grid')]
    assert 'Не удалось загрузить' not in empty_section


def test_tg_catalog_error_state_shows_safe_text_and_details() -> None:
    catalog_page = (ROOT / "src/pages/CatalogPage.tsx").read_text(encoding="utf-8")
    assert 'Не удалось загрузить каталог Telegram' in APP
    assert 'Проверьте подключение и попробуйте снова.' in APP
    assert 'details={debugDetails}' in catalog_page
    assert 'catalogErrorCreatedAt' in catalog_page
    assert 'catalogLoadStartedAt' in catalog_page
    assert 'catalogLoadRequestId' in catalog_page
    for field in ['source', 'requestUrl', 'requestUrlPath', 'requestOrigin', 'httpStatus', 'requestId', 'elapsedMs', 'attempt']:
        assert field in APP


def test_catalog_fetch_uses_fresh_controller_and_timeout_after_start() -> None:
    load_section = CLIENT[CLIENT.index('async function getPartnersAttempt'):CLIENT.index('export async function getPartners')]
    assert 'const controller = new AbortController();' in load_section
    assert 'signalAbortedBeforeFetch: controller.signal.aborted' in load_section
    assert 'timeoutId = window.setTimeout' in load_section
    assert load_section.index('console.info("catalog_fetch_start"') < load_section.index('timeoutId = window.setTimeout')
    assert load_section.index('timeoutId = window.setTimeout') < load_section.index('fetch(target.url')
    assert 'controller.abort("catalog_timeout")' in load_section
    assert 'controllerCreationStack' in load_section


def test_catalog_abort_timeout_is_not_retried_as_second_attempt() -> None:
    retry_section = CLIENT[CLIENT.index('function shouldRetryCatalogError'):CLIENT.index('async function getPartnersAttempt')]
    assert '!error.diagnostic.isAbortError' in retry_section


def test_catalog_request_url_stays_same_origin_relative_without_tg_base() -> None:
    tg_url_section = CLIENT[CLIENT.index('export function getTgApiUrl'):CLIENT.index('function getSameOriginApiUrl')]
    assert 'if (!TG_API_BASE_URL)' in tg_url_section
    assert 'return normalizedPath;' in tg_url_section
    assert 'window.location.origin' not in tg_url_section


def test_catalog_error_diagnostic_is_saved_without_secrets() -> None:
    assert '__BLOOM_LAST_CATALOG_ERROR__' in APP
    assert 'window.__BLOOM_LAST_CATALOG_ERROR__ = diagnostic ?? caughtError;' in APP


def test_production_csp_allows_tg_catalog_origin() -> None:
    production_server = (ROOT / "server/production-server.js").read_text(encoding="utf-8")
    assert "connect-src 'self' https://bloomclub.ru https://tg.bloomclub.ru" in production_server


def test_mini_app_has_no_embedded_admin_entrypoint() -> None:
    assert not (ROOT / "src/admin.tsx").exists()

    src_files = list((ROOT / "src").rglob("*"))
    admin_entrypoints = [
        path.relative_to(ROOT).as_posix()
        for path in src_files
        if path.is_file() and "admin" in path.name.lower()
    ]
    assert admin_entrypoints == []

    client_entrypoints = [
        ROOT / "index.html",
        ROOT / "vite.config.ts",
        ROOT / "src/main.tsx",
    ]
    for path in client_entrypoints:
        source = path.read_text(encoding="utf-8")
        assert "src/admin" not in source
        assert "admin.tsx" not in source
        assert "./admin" not in source
        assert "admin_bot" not in source


def test_admin_bot_exists_as_separate_server_component() -> None:
    admin_bot_root = REPO_ROOT / "admin_bot"
    assert (admin_bot_root / "admin_bot/__main__.py").is_file()
    assert (admin_bot_root / "admin_bot/bot.py").is_file()
    assert (admin_bot_root / "admin_bot/config.py").is_file()
    assert (admin_bot_root / "requirements.txt").is_file()

    mini_app_sources = [
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src").rglob("*")
        if path.is_file()
    ]
    assert all("admin_bot" not in source for source in mini_app_sources)


def test_catalog_diagnostics_ui_does_not_render_secret_fields() -> None:
    details_section = APP[
        APP.index('setPartnersErrorDetails('):APP.index(
            '      } finally {', APP.index('setPartnersErrorDetails(')
        )
    ]
    for allowed_field in [
        'source',
        'requestUrl',
        'requestUrlPath',
        'requestOrigin',
        'httpStatus',
        'requestId',
        'elapsedMs',
        'attempt',
    ]:
        assert allowed_field in details_section
    for secret in [
        'initData',
        'hash',
        'access_token',
        'Authorization',
        'TELEGRAM_ADMIN_API_TOKEN',
        'TELEGRAM_APP_DATABASE_URL',
    ]:
        assert secret not in details_section


def test_mini_app_has_no_src_admin_directory() -> None:
    assert not (ROOT / "src" / "admin").exists()


def test_mini_app_has_no_tg_admin_routes_or_admin_entrypoint_references() -> None:
    checked_files = [ROOT / "index.html", ROOT / "vite.config.ts"] + [
        path for path in (ROOT / "src").rglob("*") if path.is_file()
    ]
    forbidden = ["/tg-admin", "tg-admin", "src/admin", "admin.tsx", "adminMode", "admin toggle"]
    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in source


def test_telegram_admin_api_token_is_not_in_frontend_source_or_build_config() -> None:
    checked_files = [ROOT / ".env.example", ROOT / "vite.config.ts"] + [
        path for path in (ROOT / "src").rglob("*") if path.is_file()
    ]
    for path in checked_files:
        assert "TELEGRAM_ADMIN_API_TOKEN" not in path.read_text(encoding="utf-8")


def test_content_api_usage_is_read_only_in_mini_app_source() -> None:
    client_content = (ROOT / "src" / "content" / "clientContentApi.ts").read_text(encoding="utf-8")
    server_source = (ROOT / "server" / "production-server.js").read_text(encoding="utf-8")
    server_content_section = server_source[server_source.index("async function handleContentBlocksProxy"):server_source.index("async function handleTelegramLoginProxy")]
    combined = f"{client_content}\n{server_content_section}"
    assert "/blocks" in combined
    assert "SAME_ORIGIN_CONTENT_API_BASE_PATH" in combined
    assert "/api/content/admin" not in combined
    assert "WEB_CONTENT_ADMIN_BASE_URL" not in combined
    assert "handleContentAdminProxy" not in combined
    for method in ["POST", "PATCH", "PUT", "DELETE"]:
        assert f"method: '{method}'" not in combined
        assert f'method: "{method}"' not in combined


def test_upload_and_admin_endpoints_are_not_called_or_exposed_by_mini_app() -> None:
    checked_files = [ROOT / ".env.example", ROOT / "vite.config.ts", ROOT / "server" / "production-server.js"] + [
        path for path in (ROOT / "src").rglob("*") if path.is_file()
    ]
    forbidden = [
        "VITE_UPLOAD_CENTER_ENDPOINT",
        "/api/content/uploads",
        "WEB_CONTENT_UPLOAD_URL",
        "handleContentUpload",
        "upload center",
        "Content Admin API",
        "/api/content/admin",
        "X-Telegram-Admin-Token",
    ]
    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in source


def test_reopen_bootstrap_uses_stored_token_before_telegram_login() -> None:
    bootstrap_section = APP[APP.index('const requestProfileAndSubscription'):APP.index('if (!isActive())', APP.index('const requestProfileAndSubscription'))]
    assert 'const storedAuthToken = getStoredAuthToken();' in bootstrap_section
    assert 'if (storedAuthToken && !forceNew)' in bootstrap_section
    assert bootstrap_section.index('await requestProfileAndSubscription()') < bootstrap_section.index('await loginWithTelegramPayload()')
    assert 'getProfile()' in bootstrap_section
    assert 'getSubscription()' in bootstrap_section


def test_empty_init_data_allows_valid_stored_token_reopen() -> None:
    bootstrap_section = APP[APP.index('const requestProfileAndSubscription'):APP.index('if (!isActive())', APP.index('const requestProfileAndSubscription'))]
    stored_token_branch = bootstrap_section[bootstrap_section.index('if (storedAuthToken && !forceNew)'):bootstrap_section.index('} else {')]
    assert 'getTelegramLaunchPayloadWithRetry' not in stored_token_branch
    assert 'Telegram WebApp доступен, но Telegram не передал launch payload' not in stored_token_branch
    assert 'await requestProfileAndSubscription()' in stored_token_branch


def test_unauthorized_stored_token_clears_and_relogins() -> None:
    bootstrap_section = APP[APP.index('const requestProfileAndSubscription'):APP.index('if (!isActive())', APP.index('const requestProfileAndSubscription'))]
    assert 'caughtError.status !== 401' in bootstrap_section
    assert 'clearStoredAuthToken();' in bootstrap_section
    assert 'await loginWithTelegramPayload();' in bootstrap_section
    assert bootstrap_section.count('await requestProfileAndSubscription()') >= 3


def test_stale_token_recovery_retries_init_data_before_final_failure() -> None:
    webapp_source = (ROOT / "src" / "telegram" / "webapp.ts").read_text(encoding="utf-8")
    assert 'INIT_DATA_RETRY_ATTEMPTS = 3' in webapp_source
    assert 'INIT_DATA_RETRY_DELAY_MS = 350' in webapp_source
    assert 'getTelegramLaunchPayloadWithRetry' in webapp_source
    assert 'await waitForInitDataRetry(delayMs)' in webapp_source
    bootstrap_section = APP[APP.index('const loginWithTelegramPayload'):APP.index('let profile: ClientProfile;')]
    assert 'await getTelegramLaunchPayloadWithRetry()' in bootstrap_section


def test_runtime_error_boundary_catches_async_and_window_errors() -> None:
    boundary = (ROOT / "src/components/RuntimeErrorBoundary.tsx").read_text(encoding="utf-8")
    diagnostics = (ROOT / "src/diagnostics.ts").read_text(encoding="utf-8")
    assert "window.addEventListener('error', this.handleWindowError)" in boundary
    assert "window.addEventListener('unhandledrejection', this.handleUnhandledRejection)" in boundary
    assert "window_runtime_error" in diagnostics
    assert "unhandled_promise_rejection" in diagnostics
    assert "Не удалось показать интерфейс Bloom Club" in boundary


def test_reopen_stale_partner_screen_has_safe_fallback() -> None:
    assert 'page === "partner" && !hasValidSelectedPartner' in APP
    assert '? "catalog"' in APP
    assert 'Stale partner screen without selected partner' in APP
    assert 'Не удалось восстановить карточку партнёра' in APP
    assert 'onRetry={openCatalog}' in APP


def test_partner_page_clears_stale_offer_selection() -> None:
    assert 'safeOffers.some((offer) => offer.id === selectedOffer.id)' in PARTNER_PAGE
    assert 'setSelectedOffer(null)' in PARTNER_PAGE
    assert 'setSelectedVerification(null)' in PARTNER_PAGE


def test_react_mount_has_root_fallback_for_pre_mount_errors() -> None:
    main = (ROOT / "src/main.tsx").read_text(encoding="utf-8")
    assert "document.getElementById('root')" in main
    assert "document.body.appendChild(document.createElement('div'))" in main
    assert "ReactDOM.createRoot(getRootElement())" in main
    assert "root.render(" in main


def test_bootstrap_clears_stale_catalog_timeout_state() -> None:
    reset_section = APP[
        APP.index('const resetCatalogStateForForceReload = useCallback') : APP.index(
            'useEffect(() => {', APP.index('const resetCatalogStateForForceReload = useCallback')
        )
    ]
    assert 'partnersPromiseRef.current = null;' in reset_section
    assert 'setPartnersError("");' in reset_section
    assert 'clearCatalogDiagnostic(undefined);' in reset_section
    assert 'setCatalogErrorCreatedAt(undefined);' in reset_section
    assert 'setCatalogLoadStartedAt(undefined);' in reset_section
    assert 'setCatalogLoadRequestId(undefined);' in reset_section
    assert 'setHasPartnersLoaded(false);' in reset_section
    assert 'setIsPartnersLoading(false);' in reset_section
    post_auth_guard_return = 'traceStartup("loadAppData_post_auth_isActive_guard_return"'
    bootstrap_success_section = APP[
        APP.index(post_auth_guard_return) : APP.index(
            'setIsLoading(false);', APP.index(post_auth_guard_return)
        )
    ]
    assert 'resetCatalogStateForForceReload();' in bootstrap_success_section


def test_catalog_tab_uses_non_retry_load_without_changing_page_id() -> None:
    open_catalog_section = APP[APP.index('const openCatalog = useCallback'):APP.index('const navigate = useCallback')]
    assert 'forceReload: false' in open_catalog_section
    assert 'void loadPartners(false);' in open_catalog_section
    assert 'shouldLoadCatalog' not in open_catalog_section
    assert 'already_loaded_with_partners' not in open_catalog_section


def test_retry_force_loads_catalog_and_clears_stale_error() -> None:
    assert 'onRetry={() => void loadPartners(true)}' in APP
    load_partners_section = APP[APP.index('const loadPartners = useCallback'):APP.index('const openCatalog = useCallback')]
    assert 'const loadPartners = useCallback(\n    (forceRetry = true)' in APP
    assert 'resetCatalogStateForForceReload();' in load_partners_section
    assert 'setPartnersError("");' in load_partners_section
    assert 'setPartnersErrorDetails(undefined);' in load_partners_section


def test_startup_starts_core_partners_catalog_before_optional_requests() -> None:
    marker = APP[APP.index('traceOk("app_data_set_ok"'):APP.index('const [', APP.index('traceStart("secondary_requests_start")'))]
    assert 'catalog_reload_after_bootstrap' in marker
    assert 'reason: "startup_core_catalog_load"' in marker
    assert 'void loadPartners(true);' in marker
    assert APP.index('void loadPartners(true);') < APP.index('traceStart("secondary_requests_start")')
    assert 'if (pageRef.current === "catalog")' not in marker


def test_optional_501_requests_remain_all_settled_and_cannot_block_catalog_start() -> None:
    marker = APP[APP.index('traceStart("secondary_requests_start")'):APP.index('setIsBootstrapDone(true);')]
    assert 'Promise.allSettled' in marker
    assert 'getVerifications()' in marker
    assert 'getSavings()' in marker
    assert 'void loadPartners(true);' not in marker

def test_catalog_error_debug_freshness_markers_are_visible() -> None:
    catalog_page = (ROOT / "src/pages/CatalogPage.tsx").read_text(encoding="utf-8")
    assert 'catalogErrorCreatedAt' in catalog_page
    assert 'catalogLoadStartedAt' in catalog_page
    assert 'catalogLoadRequestId' in catalog_page
    assert 'details={debugDetails}' in catalog_page

def test_catalog_console_markers_are_present() -> None:
    for marker in [
        'catalog_open_requested',
        'catalog_load_skipped_with_reason',
        'catalog_load_started',
        'catalog_load_success',
        'catalog_load_failed',
    ]:
        assert marker in APP


def test_node_production_verifications_savings_stubs() -> None:
    server = (ROOT / "server" / "production-server.js").read_text(encoding="utf-8")
    assert "pathname === '/api/tg/me/verifications' || pathname === '/api/tg/me/savings'" in server
    assert "sendJson(response, 501, { detail: 'user_context_not_configured' });" in server


def test_node_server_injects_safe_catalog_bootstrap_from_public_tg_query() -> None:
    server_source = (ROOT / "server" / "production-server.js").read_text(encoding="utf-8")
    assert "window.__BLOOM_TG_CATALOG_BOOTSTRAP__" in server_source
    assert "function serializeBootstrapJson" in server_source
    for escaped in [".replace(/</g, '\\\\u003C')", ".replace(/>/g, '\\\\u003E')", ".replace(/&/g, '\\\\u0026')", ".replace(/\\u2028/g, '\\\\u2028')", ".replace(/\\u2029/g, '\\\\u2029')"]:
        assert escaped in server_source
    assert "function fetchPublicCatalogPartners" in server_source
    bootstrap_query = server_source[server_source.index("async function fetchPublicCatalogPartners"):server_source.index("function serializeBootstrapJson")]
    assert "FROM telegram_partners p" in bootstrap_query
    assert "WHERE p.is_active = 1" in bootstrap_query
    assert "AS cover" in bootstrap_query
    assert "AS offers_count" in bootstrap_query
    for secret in ["initData", "access_token", "Authorization", "TELEGRAM_ADMIN_API_TOKEN"]:
        assert secret not in bootstrap_query


def test_frontend_bootstrap_no_longer_prevents_real_catalog_fetch() -> None:
    assert "__BLOOM_TG_CATALOG_BOOTSTRAP__" in APP
    assert "function consumeCatalogBootstrap" in APP
    consume_section = APP[APP.index("function consumeCatalogBootstrap"):APP.index("function normalizeOffersResponse")]
    assert "bootstrap.consumed" in consume_section
    assert "window.__BLOOM_TG_CATALOG_BOOTSTRAP__ = { items: [], consumed: true }" in consume_section
    load_section = APP[APP.index("const loadPartners = useCallback"):APP.index("const openCatalog = useCallback")]
    assert "const bootstrapPartners = forceRetry ? null : consumeCatalogBootstrap();" in load_section
    assert "const partners = await getPartners();" in load_section
    assert "bootstrapPartners ?? (await getPartners())" not in load_section
    assert "setHasPartnersLoaded(true);" in load_section
    assert 'source: "fetch"' in load_section
    assert "onRetry={() => void loadPartners(true)}" in APP
    open_catalog_section = APP[APP.index("const openCatalog = useCallback"):APP.index("const navigate = useCallback")]
    assert "void loadPartners(false);" in open_catalog_section


def test_catalog_diagnostics_separate_scheduled_fetch_started_and_timeout() -> None:
    assert '| "fetch_started"' in CLIENT
    assert '| "pre_fetch_catch"' in CLIENT
    assert 'fetchStarted?: boolean;' in CLIENT
    assert 'timeoutStarted?: boolean;' in CLIENT
    attempt = CLIENT[CLIENT.index("async function getPartnersAttempt"):CLIENT.index("export async function getPartners")]
    assert attempt.index('fetchStarted = true;') < attempt.index('timeoutStarted = true;') < attempt.index('const response = await fetch(target.url')
    assert 'fetchPhase: fetchStarted ? "network_catch" : "pre_fetch_catch"' in attempt


def test_home_cms_html_blocks_are_rendered_as_inert_text() -> None:
    home_page = (ROOT / "src" / "pages" / "HomePage.tsx").read_text(encoding="utf-8")
    sanitizer = (ROOT / "src" / "utils" / "sanitizeCmsHtml.ts").read_text(encoding="utf-8")

    assert "dangerouslySetInnerHTML" not in home_page
    assert "sanitizeCmsHtml(block.body)" in home_page
    assert "SCRIPT_OR_STYLE_PATTERN" in sanitizer
    assert "TAG_PATTERN" in sanitizer
    assert "event handlers" in sanitizer


def test_regression_trial_cta_uses_required_copy_and_existing_endpoint() -> None:
    home_page = (ROOT / "src/pages/HomePage.tsx").read_text(encoding="utf-8")
    subscription_page = (ROOT / "src/pages/SubscriptionPage.tsx").read_text(encoding="utf-8")
    partner_page = (ROOT / "src/pages/PartnerPage.tsx").read_text(encoding="utf-8")
    required_copy = "Подключить пробный период 15 дней"
    assert required_copy in home_page
    assert required_copy in subscription_page
    assert required_copy in partner_page
    profile_page = (ROOT / "src/pages/ProfilePage.tsx").read_text(encoding="utf-8")
    assert required_copy in profile_page
    assert "trialAvailable = isTrialEligible(profile, subscription)" in home_page
    assert "isTrialEligible(profile, subscription)" in subscription_page
    assert "isTrialEligible(profile, subscription)" in partner_page
    assert 'activateTrialSubscription(): Promise<Subscription>' in CLIENT
    assert 'getClientApiProxyPath("/clients/me/trial-subscription")' in CLIENT
    assert '"/clients/me/subscription"' in CLIENT
    assert '"/clients/me"' in CLIENT


def test_regression_trial_cta_renders_even_with_cms_home_blocks() -> None:
    home_page = (ROOT / "src/pages/HomePage.tsx").read_text(encoding="utf-8")
    assert "function renderTrialCta()" in home_page
    cms_block_section = home_page[home_page.index("visibleHomeBlocks.length ?") : home_page.index("trialMessage || localTrialMessage")]
    assert "visibleHomeBlocks.map(renderHomeBlock)" in cms_block_section
    assert "{renderTrialCta()}" in cms_block_section


def test_regression_partner_image_resolver_supports_backend_photo_aliases() -> None:
    for field in [
        "'image'",
        "'image_url'",
        "'photo'",
        "'photo_url'",
        "'photos'",
        "'gallery'",
        "'media'",
        "'cover'",
        "'cover_url'",
        "'avatar_url'",
    ]:
        assert field in PARTNER_DISPLAY or field.replace("'", '"') in CLIENT
    assert "getPartnerImages(currentPartner).filter((image) => !failedImageUrls.includes(image))" in PARTNER_PAGE
    assert "getPartnerImage(partner)" in (ROOT / "src/pages/CatalogPage.tsx").read_text(encoding="utf-8")


def test_regression_real_partners_not_filtered_by_missing_category_city_photo_or_name() -> None:
    catalog_categories = (ROOT / "src/utils/catalogCategories.ts").read_text(encoding="utf-8")
    catalog_page = (ROOT / "src/pages/CatalogPage.tsx").read_text(encoding="utf-8")
    client = CLIENT
    assert "if (category === 'Все')" in catalog_categories
    assert "return safePartners;" in catalog_categories
    assert "getPartnerCategories(partner).includes(category)" in catalog_categories
    assert "Тест1" not in catalog_page
    assert "Тест2" not in catalog_page
    assert "Demo spa" not in client
    assert "Demo spa" not in catalog_page
