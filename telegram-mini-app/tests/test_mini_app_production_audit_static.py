from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
PARTNER_DISPLAY = (ROOT / "src/utils/partnerDisplay.ts").read_text(encoding="utf-8")
CATALOG = (ROOT / "src/pages/CatalogPage.tsx").read_text(encoding="utf-8")
HOME = (ROOT / "src/pages/HomePage.tsx").read_text(encoding="utf-8")
PARTNER_PAGE = (ROOT / "src/pages/PartnerPage.tsx").read_text(encoding="utf-8")
SUBSCRIPTION = (ROOT / "src/pages/SubscriptionPage.tsx").read_text(encoding="utf-8")
CONTENT_API = (ROOT / "src/content/clientContentApi.ts").read_text(encoding="utf-8")
PRODUCTION_SERVER = (ROOT / "server/production-server.js").read_text(encoding="utf-8")
MAIN = (ROOT / "src/main.tsx").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def test_real_partners_are_filtered_sorted_and_demo_seed_partners_are_excluded() -> None:
    assert "sortPartnersForCatalog" in PARTNER_DISPLAY
    assert "isVisiblePartner" in PARTNER_DISPLAY
    assert "sort_order" in PARTNER_DISPLAY
    assert "is_hidden" in PARTNER_DISPLAY
    assert "is_deleted" in PARTNER_DISPLAY
    assert "archived" in PARTNER_DISPLAY
    assert "demo spa|demo fitness|route-test|route test" in PARTNER_DISPLAY
    assert "partners: sortPartnersForCatalog" in APP


def test_catalog_search_categories_photos_and_friendly_empty_error_states() -> None:
    assert "filterPartnersByCategory" in CATALOG
    assert "getPartnerSearchText" in CATALOG
    assert "getPartnerImage(partner)" in CATALOG
    assert "PartnerCardImage" in CATALOG
    assert "Мы скоро добавим новых партнёров" in CATALOG
    assert "Не удалось загрузить каталог" in CATALOG
    assert "JSON.stringify" not in CATALOG


def test_partner_photos_offers_visibility_sort_and_verify_friendly_errors() -> None:
    assert "sortOffersForPartner" in APP
    assert "isVisibleOffer" in PARTNER_DISPLAY
    assert "sort_order" in PARTNER_DISPLAY
    assert "partner-gallery__main" in PARTNER_PAGE
    assert "getOfferPhotoRecords" in PARTNER_PAGE
    assert "Получить привилегию" in PARTNER_PAGE
    assert "Пока нет активных предложений" in PARTNER_PAGE
    assert "Функция скоро станет доступна" in PARTNER_PAGE
    assert "Получение кода для Telegram-каталога скоро будет доступно" in PARTNER_PAGE
    assert "JSON.stringify" not in PARTNER_PAGE


def test_trial_cta_conditions_are_preserved_on_home_partner_and_subscription() -> None:
    for source in (HOME, PARTNER_PAGE, SUBSCRIPTION):
        assert "isTrialEligible(profile, subscription)" in source
        assert "Подключить пробный период 15 дней" in source


def test_tg_giveaways_route_uses_public_content_api_contract() -> None:
    assert "pathname === '/api/tg/giveaways'" in PRODUCTION_SERVER
    assert "WEB_CONTENT_GIVEAWAYS_URL" in PRODUCTION_SERVER
    assert "normalizeGiveaway" in PRODUCTION_SERVER
    assert "content_api_unavailable" in PRODUCTION_SERVER
    assert "SAFE_EMPTY_GIVEAWAYS_RESPONSE" not in PRODUCTION_SERVER


def test_banners_and_giveaways_are_active_sorted_with_images_and_empty_states() -> None:
    assert "HOME_BLOCK_TYPES" in CONTENT_API
    assert '"banner"' in CONTENT_API
    assert '"giveaway"' in CONTENT_API
    assert "is_active" in CONTENT_API
    assert "sort_order" in CONTENT_API
    assert "image_url" in CONTENT_API
    assert "homeBlocks.filter" in HOME
    assert 'block.type === "giveaway"' in HOME
    assert "Приз:" in HOME
    assert "home-empty-state" in HOME
    assert "extractHomeBlocksFromResponse" in CONTENT_API
    assert "return Array.isArray(candidate) ? normalize(candidate) : []" in CONTENT_API


def test_startup_fallback_and_static_app_import_untouched() -> None:
    assert 'id="bloom-html-fallback-overlay"' in INDEX
    assert 'wrapper.id = "bloom-entry-fallback-overlay"' in MAIN
    assert 'import App from "./App";' in MAIN
    assert 'import("./App")' not in MAIN
    assert "import('./App')" not in MAIN
