from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_trial_eligibility_contract_is_normalized():
    source = read("src/utils/subscription.ts")
    assert "export function getTrialEligibility" in source
    assert "canUseTrial" in source
    assert "trialUsed" in source
    assert "hasActiveSubscription" in source
    assert "trialAvailable" in source
    assert "isSubscriptionActive(subscription, now)" in source
    assert "profile?.trial_used" in source
    assert "subscription?.trial_available" in source


def test_trial_activation_refreshes_profile_and_subscription():
    source = read("src/App.tsx")
    assert "activateTrialSubscription" in source
    assert "refreshProfileAndSubscription" in source
    assert "setTrialMessage" in source
    assert "getProfile()" in source
    assert "getSubscription()" in source


def test_telegram_login_sends_referral_start_param_to_backend():
    client = read("src/api/client.ts")
    app = read("src/App.tsx")
    webapp = read("src/telegram/webapp.ts")
    assert "referral_code" in client
    assert "start_param" in client
    assert "referralCode: getReferralCodeFromStartParam()" in app
    assert "export function getReferralCodeFromStartParam" in webapp


def test_frontend_referral_blocks_exist_on_home_and_profile():
    home = read("src/pages/HomePage.tsx")
    profile = read("src/pages/ProfilePage.tsx")
    assert "Приглашай подруг и получай бонусы" in home
    assert "За каждого приглашённого — 5 номеров в розыгрыше" in home
    assert "Пригласить" in home
    assert "Моя реферальная ссылка" in profile
    assert "Скопировать ссылку" in profile
    assert "Поделиться" in profile
    assert "navigator.clipboard" in profile
    assert "navigator.share" in profile


def test_database_migration_models_referrals_and_giveaway_entries():
    migration = read("backend/migrations/20260630_referrals_trial_giveaway_entries.sql")
    assert "CREATE TABLE IF NOT EXISTS client_referrals" in migration
    assert "referrer_client_id" in migration
    assert "referred_client_id" in migration
    assert "reward_entries_count INTEGER NOT NULL DEFAULT 5" in migration
    assert "CREATE TABLE IF NOT EXISTS giveaway_entries" in migration
    assert "client_id BIGINT NOT NULL REFERENCES clients(id)" in migration
    assert "source TEXT NOT NULL" in migration
    assert "related_referral_id" in migration
    assert "ux_client_referrals_referred" in migration
    assert "ux_giveaway_entries_referral_reward" in migration
    assert "ux_clients_telegram_user_id" in migration


def test_client_api_proxy_allows_trial_post_only_for_trial_endpoint():
    server = read("server/production-server.js")
    assert "allow: 'GET, POST, HEAD, OPTIONS'" in server
    assert "pathname !== '/api/v1/clients/me/trial-subscription'" in server
    assert "method === 'POST' ? { body } : {}" in server



def test_trial_button_click_posts_to_production_client_api_proxy():
    client = read("src/api/client.ts")
    home = read("src/pages/HomePage.tsx")
    subscription = read("src/pages/SubscriptionPage.tsx")
    app = read("src/App.tsx")

    trial_api_start = client.index("export function activateTrialSubscription")
    trial_api_end = client.index("export function verifyPartnerOffer", trial_api_start)
    trial_api = client[trial_api_start:trial_api_end]
    assert 'getClientApiProxyPath("/clients/me/trial-subscription")' in trial_api
    assert '{ method: "POST" }' in trial_api
    assert '"same-origin"' in trial_api

    activate_trial_start = app.index("const activateTrial = useCallback")
    activate_trial_end = app.index("const createVerification", activate_trial_start)
    activate_trial_flow = app[activate_trial_start:activate_trial_end]
    assert "await activateTrialSubscription()" in activate_trial_flow

    home_button_start = home.index("function renderTrialCta()")
    home_button_end = home.index("function renderLegacyHome()", home_button_start)
    home_button = home[home_button_start:home_button_end]
    assert 'onClick={() => void handleActivateTrial()}' in home_button
    assert "if (!trialAvailable)" in home_button
    assert "preventDefault" not in home_button

    subscription_button_start = subscription.index("async function handleTrial()")
    subscription_button_end = subscription.index('<div className="info-panel info-panel--soft">', subscription_button_start)
    subscription_button = subscription[subscription_button_start:subscription_button_end]
    assert 'onClick={() => void handleTrial()}' in subscription_button
    assert "await onActivateTrial()" in subscription_button
    assert "preventDefault" not in subscription_button


def test_trial_activation_refreshes_referral_summary_after_success():
    app = read("src/App.tsx")
    trial_start = app.index("const activateTrial = useCallback")
    trial_end = app.index("const createVerification", trial_start)
    trial_flow = app[trial_start:trial_end]
    assert "await activateTrialSubscription()" in trial_flow
    assert "await refreshProfileAndSubscription()" in trial_flow
    assert "await getReferralSummary()" in trial_flow
    assert "referralSummary" in trial_flow


def test_referral_summary_contract_fields_are_supported():
    types = read("src/api/types.ts")
    assert "pending_referrals_count" in types
    assert "activated_referrals_count" in types
    assert "earned_entries_count" in types
    assert "reward_entries_per_referral" in types


def test_referral_link_uses_registered_main_app_startapp_link():
    referral = read("src/utils/referral.ts")
    assert "VITE_TELEGRAM_BOT_USERNAME" in referral
    assert "VITE_TELEGRAM_MINI_APP_SHORT_NAME" not in referral
    assert "VITE_TELEGRAM_MINI_APP_DIRECT_LINK" not in referral
    assert "__BLOOM_TG_CONFIG__" in referral
    assert "telegramMiniAppDirectLink" not in referral
    assert "https://t.me/" in referral
    assert "searchParams.set('startapp'" in referral
    assert "hostname !== 't.me'" in referral
    assert "pathParts.length !== 1" in referral
    assert "bloomclub.ru" not in referral
    assert "|| backendLink" not in referral


def test_referral_reward_migration_starts_pending_and_is_idempotent():
    migration = read("backend/migrations/20260630_referrals_trial_giveaway_entries.sql")
    assert "status TEXT NOT NULL DEFAULT 'pending'" in migration
    assert "CONSTRAINT ck_client_referrals_not_self" in migration
    assert "CONSTRAINT ux_client_referrals_referred UNIQUE (referred_client_id)" in migration
    assert "ux_giveaway_entries_referral_reward" in migration
    assert "entries_count INTEGER NOT NULL CHECK (entries_count > 0)" in migration


def test_referral_ui_shares_or_copies_and_shows_pending_activated_entries():
    home = read("src/pages/HomePage.tsx")
    profile = read("src/pages/ProfilePage.tsx")
    util = read("src/utils/referral.ts")
    assert "shareOrCopyReferralLink(referralLink)" in home
    assert "shareOrCopyReferralLink(referralLink)" in profile
    assert "navigator.share" in util and "navigator.clipboard?.writeText" in util
    assert "pending_referrals_count" in home and "activated_referrals_count" in home
    assert "pending_referrals_count" in profile and "activated_referrals_count" in profile


def test_bottom_nav_375_width_spacing_regression():
    css = read("src/styles.css")
    assert "max-width: 20%" in css
    assert "font-size: clamp(0.52rem, 2.35vw, 0.62rem)" in css
    assert "gap: 2px" in css


def test_cms_trial_button_click_without_action_posts_to_trial_endpoint():
    """Regression for CMS CTA text: emulate the click routing decision before fetch()."""
    home = read("src/pages/HomePage.tsx")
    home_cta = read("src/utils/homeCta.ts")
    app = read("src/App.tsx")
    client = read("src/api/client.ts")

    # JSX CMS button onClick must route through the resolver, not raw cta_action.
    assert 'onClick={() => runCta(resolveHomeCtaAction(block))}' in home

    # Emulate clicking a CMS button with only the production text and no cta_action:
    # resolveHomeCtaAction({ cta_text: "Подключить тестовый период", cta_action: "" }) -> "trial".
    assert 'подключить\\s+(?:тестовый|пробный)\\s+период' in home_cta
    assert 'return "trial";' in home_cta

    run_cta_start = home.index("function runCta")
    run_cta_end = home.index("function renderCta", run_cta_start)
    run_cta = home[run_cta_start:run_cta_end]
    assert 'if (normalized === "trial")' in run_cta
    assert 'void handleActivateTrial();' in run_cta
    assert 'return;' in run_cta[run_cta.index('if (normalized === "trial")'):]

    handle_start = home.index("async function handleActivateTrial()")
    handle_end = home.index("function runCta", handle_start)
    handle = home[handle_start:handle_end]
    assert "return" not in handle[:handle.index("try {")]
    assert "const updated = await onActivateTrial();" in handle

    activate_trial_start = app.index("const activateTrial = useCallback")
    activate_trial_end = app.index("const createVerification", activate_trial_start)
    activate_trial_flow = app[activate_trial_start:activate_trial_end]
    assert "await activateTrialSubscription()" in activate_trial_flow

    trial_api_start = client.index("export function activateTrialSubscription")
    trial_api_end = client.index("export function verifyPartnerOffer", trial_api_start)
    trial_api = client[trial_api_start:trial_api_end]
    assert 'getClientApiProxyPath("/clients/me/trial-subscription")' in trial_api
    assert '{ method: "POST" }' in trial_api


def test_production_server_injects_runtime_telegram_referral_config():
    server = read("server/production-server.js")
    assert "TELEGRAM_BOT_USERNAME" in server
    assert "TELEGRAM_MINI_APP_SHORT_NAME" not in server
    assert "TELEGRAM_MINI_APP_DIRECT_LINK" not in server
    assert "function injectRuntimeConfig" in server
    assert "window.__BLOOM_TG_CONFIG__" in server
    assert "telegramBotUsername: TELEGRAM_BOT_USERNAME" in server
    assert "telegramMiniAppShortName" not in server
    assert "telegramMiniAppDirectLink" not in server
    assert "let body = injectRuntimeConfig(indexHtml);" in server

def test_startapp_url_fallback_is_used_for_referral_code():
    webapp = read("src/telegram/webapp.ts")
    assert "function getTelegramStartParamFromUrl" in webapp
    assert "params.get('tgWebAppStartParam')" in webapp
    assert "params.get('startapp')" in webapp
    assert "getTelegramStartParamFromUrl()" in webapp


def test_production_login_proxy_logs_referral_presence_only():
    server = read("server/production-server.js")
    assert "hasReferralCode" in server
    assert "hasStartParam" in server
    assert "referralCodeLength" in server
    assert "startParamLength" in server
    assert "parsed.referral_code" in server
    assert "parsed.start_param" in server


def test_referral_sql_uses_client_ids_for_pending_and_rewards():
    migration = read("backend/migrations/20260630_referrals_trial_giveaway_entries.sql")
    assert "register_client_referral_if_needed" in migration
    assert "activate_pending_referral_reward" in migration
    assert "p_referred_client_id BIGINT" in migration
    assert "referrer_client_id, referred_client_id" in migration
    assert "v_referral.referrer_client_id" in migration
    assert "status = 'successful'" in migration
