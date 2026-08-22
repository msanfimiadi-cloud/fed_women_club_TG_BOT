import asyncio
from types import SimpleNamespace

from admin_bot.bot import format_new_user_notification, notify_new_user
from admin_bot.keyboards import main_menu
from admin_bot.notification_store import NotificationStore


def test_first_start_is_registered_only_once_and_persists(tmp_path) -> None:
    database_path = tmp_path / "data" / "notifications.sqlite3"
    store = NotificationStore(database_path)

    assert store.register_user(123, username="bloom", display_name="Bloom User") is True
    assert store.register_user(123, username="bloom", display_name="Bloom User") is False
    assert NotificationStore(database_path).register_user(123) is False


def test_partner_access_is_persistent_and_not_duplicated(tmp_path) -> None:
    database_path = tmp_path / "notifications.sqlite3"
    store = NotificationStore(database_path)

    assert store.grant_partner_access(456, granted_by=123) is True
    assert store.grant_partner_access(456, granted_by=123) is False
    assert store.is_partner(456) is True
    assert NotificationStore(database_path).partner_ids() == frozenset({456})


def test_new_user_notification_contains_profile_and_escapes_names() -> None:
    user = SimpleNamespace(id=789, first_name="Анна <Bloom>", last_name="Клуб", username="anna")

    notification = format_new_user_notification(user)

    assert "Новый пользователь" in notification
    assert "Анна &lt;Bloom&gt; Клуб" in notification
    assert "@anna" in notification
    assert "<code>789</code>" in notification
    assert 'href="tg://user?id=789"' in notification


def test_new_user_notification_goes_to_admins_and_partners_once(tmp_path) -> None:
    sent = []

    class FakeBot:
        async def send_message(self, chat_id: int, text: str) -> None:
            sent.append((chat_id, text))

    store = NotificationStore(tmp_path / "notifications.sqlite3")
    store.grant_partner_access(456, granted_by=123)
    store.grant_partner_access(123, granted_by=123)
    user = SimpleNamespace(id=789, first_name="Анна", last_name=None, username=None)

    asyncio.run(notify_new_user(FakeBot(), user, frozenset({123, 321}), store))

    assert {chat_id for chat_id, _ in sent} == {123, 321, 456}
    assert len(sent) == 3
    assert all("<code>789</code>" in text for _, text in sent)


def test_admin_menu_includes_partner_access_button() -> None:
    buttons = [button.text for row in main_menu().keyboard for button in row]

    assert "🤝 Выдать права партнёра" in buttons
