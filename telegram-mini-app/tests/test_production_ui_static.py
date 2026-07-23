from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
MAIN = (ROOT / "src/main.tsx").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
BOTTOM_NAV = (ROOT / "src/components/BottomNav.tsx").read_text(encoding="utf-8")
STYLES = (ROOT / "src/styles.css").read_text(encoding="utf-8")


def test_production_app_ui_does_not_include_old_startup_diagnostics_cta() -> None:
    assert "Показать диагностику запуска" not in APP


def test_debug_startup_ui_is_dev_or_query_param_gated() -> None:
    assert "import.meta.env.DEV" in APP
    assert 'get("debug") === "1"' in APP
    debug_block = APP[APP.index("function isStartupDebugUiEnabled") : APP.index("export interface PartnerOffersDiagnostic")]
    assert "import.meta.env.DEV" in debug_block
    assert "debug" in debug_block
    render_block = APP[APP.index("{isStartupDebugUiEnabledValue ?") : APP.rindex("</AppShell>")]
    assert "startup-diagnostic-button" in render_block
    assert "DiagnosticOverlay" in render_block
    assert "startupDiagnostics" in render_block


def test_startup_fallbacks_and_static_app_import_are_preserved() -> None:
    assert 'id="bloom-html-fallback-overlay"' in INDEX
    assert 'wrapper.id = "bloom-entry-fallback-overlay"' in MAIN
    assert 'import App from "./App";' in MAIN
    assert 'import("./App")' not in MAIN
    assert "import('./App')" not in MAIN


def test_tabbar_contains_expected_items_and_navigation_handlers() -> None:
    for page_id in ["home", "catalog", "privileges", "savings", "profile"]:
        assert f"id: '{page_id}'" in BOTTOM_NAV
    for label in ["Главная", "Клуб", "Бонусы", "Экономия", "Профиль"]:
        assert label in BOTTOM_NAV
    assert "items.map" in BOTTOM_NAV
    assert "onClick={() => onNavigate(item.id)}" in BOTTOM_NAV
    assert "bottom-nav__item--active" in BOTTOM_NAV
    assert "Мои привилегии" not in BOTTOM_NAV


def test_tabbar_has_safe_area_and_width_protection() -> None:
    bottom_nav_block = STYLES[STYLES.index(".bottom-nav {") : STYLES.index(".bottom-nav__item {")]
    item_block = STYLES[STYLES.index(".bottom-nav__item {") : STYLES.index(".bottom-nav__item span")]
    assert "env(safe-area-inset-bottom)" in bottom_nav_block
    assert "env(safe-area-inset-left)" in bottom_nav_block
    assert "env(safe-area-inset-right)" in bottom_nav_block
    assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in bottom_nav_block
    assert "bottom: max(8px, env(safe-area-inset-bottom))" in STYLES
    assert "repeat(5, minmax(0, 1fr))" in STYLES
    assert "min-width: 0" in item_block
    assert "font-size: 10px" in STYLES
    assert "font-size: 9.5px" in STYLES
    assert "text-overflow: clip" in STYLES
    assert "--bottom-nav-reserved-height" in STYLES


def test_home_screen_restores_lifestyle_sections_without_debug_content() -> None:
    home_page = (ROOT / "src/pages/HomePage.tsx").read_text(encoding="utf-8")
    assert "home-hero" in home_page
    assert "Bloom Club · Женский клуб НСК" in home_page
    assert "home-partners-section" in home_page
    assert "home-partner-tile" in home_page
    assert "getPartnerImage(partner)" in home_page
    assert "getPartnerAddress(partner)" in home_page
    assert "home-empty-state" in home_page
    assert "Скоро добавим партнёров" in home_page
    assert "JSON.stringify" not in home_page
    assert "Тест1" not in home_page


def test_home_screen_styles_keep_card_layout_and_tabbar_untouched() -> None:
    assert ".home-hero" in STYLES
    assert ".home-partners-section" in STYLES
    assert ".home-partner-tile" in STYLES
    assert ".home-empty-state" in STYLES
    assert "linear-gradient(135deg, rgba(255, 250, 250, 0.98), rgba(250, 225, 229, 0.9))" in STYLES
    assert ".bottom-nav" in STYLES


def test_partner_detail_restores_lifestyle_layout_and_empty_offers_state() -> None:
    partner_page = (ROOT / "src/pages/PartnerPage.tsx").read_text(encoding="utf-8")
    assert "partner-detail__hero" in partner_page
    assert "partner-gallery__main" in partner_page
    assert "partner-detail__placeholder" in partner_page
    assert "partner-detail__info-card" in partner_page
    assert "partner-contact-card__rows" in partner_page
    assert "partner.offers.title" in partner_page
    assert "offer-list" in partner_page
    assert "offer-card" in partner_page
    assert "Пока нет активных предложений" in partner_page
    assert 'offersStatus === "empty" || offersStatus === "idle"' in partner_page
    assert "offersDiagnostic?.backendDetail" not in partner_page
    assert "JSON.stringify" not in partner_page
    assert "Тест1" not in partner_page


def test_partner_detail_styles_include_hero_info_card_and_offers() -> None:
    assert ".partner-detail__hero" in STYLES
    assert ".partner-detail__info-card" in STYLES
    assert ".partner-detail__placeholder" in STYLES
    assert ".partner-contact-card__rows" in STYLES
    assert ".offer-list" in STYLES
    assert ".offer-card" in STYLES
    assert "clamp(240px, 62vw, 320px)" in STYLES


def test_api_endpoints_static_import_and_startup_fallbacks_remain_unchanged() -> None:
    client = (ROOT / "src/api/client.ts").read_text(encoding="utf-8")
    assert "getPartnerOffersPath" in client
    assert '`/api/tg/partners/${partnerId}/offers`' in client
    assert '`/api/tg/partners/${partnerId}/offers/${offerId}/verify`' in client
    assert 'id="bloom-html-fallback-overlay"' in INDEX
    assert 'wrapper.id = "bloom-entry-fallback-overlay"' in MAIN
    assert 'import App from "./App";' in MAIN
    assert 'import("./App")' not in MAIN


def test_partner_offers_ux_cards_badges_disabled_and_verify_404_copy() -> None:
    partner_page = (ROOT / "src/pages/PartnerPage.tsx").read_text(encoding="utf-8")
    assert "getOfferAccentBadge" in partner_page
    assert "offer-card__badge" in partner_page
    assert "offer-card--disabled" in partner_page
    assert "Предложение временно недоступно" in partner_page
    assert "Функция скоро станет доступна" in partner_page
    assert "error.status === 404" in partner_page
    assert "offer-card__cta" in partner_page

    assert "grid-template-rows: auto 1fr auto auto auto" in STYLES
    assert ".offer-card__badge" in STYLES
    assert ".offer-card--disabled" in STYLES
    assert ".offer-card__cta" in STYLES
    assert "aspect-ratio: 16 / 10" in STYLES


def test_catalog_restores_production_mobile_ux() -> None:
    catalog_page = (ROOT / "src/pages/CatalogPage.tsx").read_text(encoding="utf-8")
    assert "catalog-search" in catalog_page
    assert "Найти салон, кафе или услугу" in catalog_page
    assert "catalog-search__clear" in catalog_page
    for category in ["Красота", "Здоровье", "Спорт", "Кафе", "Рестораны", "Образование"]:
        assert category in catalog_page
    assert "CatalogSkeleton" in catalog_page
    assert "partner-card--skeleton" in catalog_page
    assert "Мы скоро добавим новых партнёров" in catalog_page
    assert "catalog-empty-state" in catalog_page
    assert "getPartnerAddress(partner)" in catalog_page
    assert "getPartnerDistance(partner)" in catalog_page
    assert "getPartnerDescription(partner)" in catalog_page
    assert "JSON.stringify" not in catalog_page
    assert "Диагностика" not in catalog_page


def test_catalog_styles_include_cards_search_chips_skeleton_and_responsive_grid() -> None:
    assert ".catalog-search" in STYLES
    assert ".catalog-search__icon" in STYLES
    assert ".catalog-search__clear" in STYLES
    assert ".catalog-chip" in STYLES
    assert ".catalog-grid" in STYLES
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in STYLES
    assert ".partner-card__media" in STYLES
    assert ".partner-card__category" in STYLES
    assert ".partner-card__address" in STYLES
    assert ".partner-card__preview" in STYLES
    assert ".catalog-empty-state" in STYLES
    assert ".skeleton-block" in STYLES
    assert "@keyframes catalog-skeleton" in STYLES
    assert "@media (max-width: 390px)" in STYLES


def test_design_system_tokens_unify_colors_spacing_type_and_motion() -> None:
    for token in [
        "--color-primary",
        "--color-secondary",
        "--color-accent",
        "--color-surface",
        "--color-background",
        "--color-success",
        "--color-warning",
        "--color-disabled",
        "--radius-card",
        "--space-card",
        "--shadow-card",
        "--text-h1",
        "--text-h2",
        "--text-h3",
        "--text-body",
        "--text-caption",
        "--motion-fast",
    ]:
        assert token in STYLES
    assert "@keyframes bloom-fade-in" in STYLES


def test_cards_cta_inputs_empty_and_skeleton_share_design_system() -> None:
    empty_state = (ROOT / "src/components/EmptyState.tsx").read_text(encoding="utf-8")
    assert "state__icon" in empty_state
    assert "button button--primary" in empty_state
    assert ".page-header," in STYLES
    assert ".home-partner-tile," in STYLES
    assert ".partner-card," in STYLES
    assert "border-radius: var(--radius-card)" in STYLES
    assert "box-shadow: var(--shadow-card)" in STYLES
    assert ".button," in STYLES
    assert "min-height: 48px" in STYLES
    assert "font-weight: 800" in STYLES
    assert ".catalog-search," in STYLES
    assert "border-radius: var(--radius-input)" in STYLES
    assert ".state--empty," in STYLES
    assert ".state__icon," in STYLES
    assert ".skeleton-block," in STYLES
    assert ".spinner" in STYLES
