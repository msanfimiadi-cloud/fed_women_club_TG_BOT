import asyncio
from types import SimpleNamespace

from admin_bot.bot import (
    advertiser_referral_code,
    format_advertiser_statistics,
    format_new_user_notification,
    notify_new_user,
)
from admin_bot.keyboards import main_menu
from admin_bot.notification_store import NotificationStore


def test_advertiser_link_is_unique_persistent_and_reused_for_the_same_profile(tmp_path) -> None:
    database_path = tmp_path / "notifications.sqlite3"
    store = NotificationStore(database_path)

    first = store.add_advertiser(456, name="Анна Реклама", created_by=123)
    second = store.add_advertiser(789, name="Мария Реклама", created_by=123)
    repeated = store.add_advertiser(456, name="Другое имя", created_by=123)

    assert first["referral_code"].startswith("ad_")
    assert first["referral_code"] != second["referral_code"]
    assert repeated["referral_code"] == first["referral_code"]
    assert repeated["name"] == "Анна Реклама"
    assert NotificationStore(database_path).advertiser_by_code(first["referral_code"])["telegram_user_id"] == 456


def test_referrals_are_counted_once_and_never_reassigned(tmp_path) -> None:
    store = NotificationStore(tmp_path / "notifications.sqlite3")
    first = store.add_advertiser(456, name="Анна", created_by=123)
    second = store.add_advertiser(789, name="Мария", created_by=123)

    is_new, source = store.register_referred_user(
        1001,
        username="client",
        display_name="Клиент",
        referral_code=first["referral_code"],
    )
    assert is_new is True
    assert source["telegram_user_id"] == 456

    is_new_again, source_again = store.register_referred_user(
        1001,
        username="client",
        display_name="Клиент",
        referral_code=second["referral_code"],
    )
    assert is_new_again is False
    assert source_again is None
    assert store.advertiser_statistics(456)["total"] == 1
    assert store.advertiser_statistics(789)["total"] == 0


def test_organic_and_self_referrals_do_not_change_advertiser_statistics(tmp_path) -> None:
    store = NotificationStore(tmp_path / "notifications.sqlite3")
    advertiser = store.add_advertiser(456, name="Анна", created_by=123)

    assert store.register_referred_user(1001, referral_code=None) == (True, None)
    assert store.register_referred_user(456, referral_code=advertiser["referral_code"]) == (True, None)
    assert store.advertiser_statistics(456)["total"] == 0


def test_advertisers_receive_only_users_from_their_own_link(tmp_path) -> None:
    sent = []

    class FakeBot:
        async def send_message(self, chat_id: int, text: str) -> None:
            sent.append((chat_id, text))

    store = NotificationStore(tmp_path / "notifications.sqlite3")
    store.grant_partner_access(321, granted_by=123)
    first = store.add_advertiser(456, name="Анна", created_by=123)
    store.add_advertiser(789, name="Мария", created_by=123)
    first["link"] = f"https://t.me/bloom_bot?start={first['referral_code']}"
    user = SimpleNamespace(id=1001, first_name="Клиент", last_name=None, username="client")

    asyncio.run(notify_new_user(FakeBot(), user, frozenset({123}), store, first))

    assert {chat_id for chat_id, _ in sent} == {123, 321, 456}
    assert all("Рекламодатель: <b>Анна</b>" in text for _, text in sent)
    assert all(first["link"] in text for _, text in sent)
    assert all(chat_id != 789 for chat_id, _ in sent)


def test_advertiser_statistics_are_isolated_and_formatted(tmp_path) -> None:
    store = NotificationStore(tmp_path / "notifications.sqlite3")
    first = store.add_advertiser(456, name="Анна <Bloom>", created_by=123)
    second = store.add_advertiser(789, name="Мария", created_by=123)
    store.register_referred_user(1001, display_name="Первый", referral_code=first["referral_code"])
    store.register_referred_user(1002, display_name="Второй", referral_code=first["referral_code"])
    store.register_referred_user(1003, display_name="Третий", referral_code=second["referral_code"])

    first_statistics = store.advertiser_statistics(456)
    second_statistics = store.advertiser_statistics(789)
    text = format_advertiser_statistics(first_statistics, bot_username="bloom_bot")

    assert first_statistics["total"] == 2
    assert first_statistics["today"] == 2
    assert second_statistics["total"] == 1
    assert len(store.all_advertiser_statistics()) == 2
    assert "Анна &lt;Bloom&gt;" in text
    assert "Всего: <b>2</b>" in text
    assert "Первый" in text and "Второй" in text and "Третий" not in text


def test_referral_start_payload_is_strictly_validated() -> None:
    assert advertiser_referral_code("/start ad_AbCdEfGh1234") == "ad_AbCdEfGh1234"
    assert advertiser_referral_code("/start@bloom_bot ad_AbCdEfGh1234") == "ad_AbCdEfGh1234"
    assert advertiser_referral_code("/start bloomonline_AbCdEfGh1234") is None
    assert advertiser_referral_code("/start ad_short") is None
    assert advertiser_referral_code("/start ad_AbCdEfGh1234 extra") is None


def test_source_is_included_in_notifications_without_breaking_organic_visits() -> None:
    user = SimpleNamespace(id=1001, first_name="Клиент", last_name=None, username=None)
    advertiser = {"name": "Анна", "telegram_user_id": 456, "link": "https://t.me/bloom_bot?start=ad_example12"}

    assert "Источник: прямой переход" in format_new_user_notification(user)
    assert "Рекламодатель: <b>Анна</b>" in format_new_user_notification(user, advertiser)


def test_admin_menu_includes_advertiser_controls() -> None:
    buttons = [button.text for row in main_menu().keyboard for button in row]

    assert "📣 Добавить рекламодателя" in buttons
    assert "📊 Статистика рекламы" in buttons


def test_login_code_requests_are_limited_to_five_per_fifteen_minutes(tmp_path) -> None:
    database_path = tmp_path / "notifications.sqlite3"
    store = NotificationStore(database_path)

    for attempt in range(5):
        assert store.reserve_login_code_request(123, now=1000 + attempt) == (True, 0)

    allowed, retry_after = store.reserve_login_code_request(123, now=1005)
    assert allowed is False
    assert retry_after == 895
    assert NotificationStore(database_path).reserve_login_code_request(123, now=1006) == (False, 894)
    assert store.reserve_login_code_request(456, now=1005) == (True, 0)
    assert store.reserve_login_code_request(123, now=1900) == (True, 0)
