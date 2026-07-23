from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from backend.telegram_catalog.database import connect, init_db
from telegram_app.scripts.sync_content_to_tg_catalog import map_offer, map_partner, sync_catalog


def setup_db() -> tuple[tempfile.TemporaryDirectory[str], str]:
    temp_dir = tempfile.TemporaryDirectory()
    database_url = f"sqlite:///{Path(temp_dir.name) / 'telegram_app.db'}"
    os.environ["TELEGRAM_APP_DATABASE_URL"] = database_url
    init_db(database_url)
    return temp_dir, database_url


def sample_catalog(active: bool = True, missing: bool = False) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]]]:
    partner = {"id": 101, "name": "WEB Spa", "is_active": active}
    if not missing:
        partner.update({"description": "Desc", "city_name": "Москва", "category_title": "Spa", "address": "A", "phone": "+7", "sort_order": 5})
    offer = {"id": 201, "partner_id": 101, "name": "Massage", "regular_price": 1000, "club_price": 700, "terms": "Terms", "active": active}
    return [partner], {101: [{"id": 301, "image_url": "https://example.test/p.jpg", "active": True}]}, {101: [offer]}, {}


def count_rows(database_url: str, table: str) -> int:
    with connect(database_url) as connection:
        return int(connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def test_map_partner_accepts_web_aliases() -> None:
    mapped = map_partner({"id": "7", "display_name": "Name", "city_name": "City", "category_title": "Cat", "active": False})
    assert mapped == {
        "external_content_id": 7,
        "title": "Name",
        "display_name": "Name",
        "description": None,
        "city": "City",
        "category": "Cat",
        "address": None,
        "phone": None,
        "is_active": 0,
        "sort_order": 0,
    }


def test_map_offer_accepts_web_aliases_and_computes_discount() -> None:
    mapped = map_offer({"id": 9, "name": "Offer", "regular_price": "200", "club_price": "150", "conditions": "C"}, 3)
    assert mapped["external_content_id"] == 9
    assert mapped["partner_id"] == 3
    assert mapped["title"] == "Offer"
    assert mapped["base_price"] == 200
    assert mapped["member_price"] == 150
    assert mapped["discount_percent"] == 25
    assert mapped["conditions"] == "C"


def test_dry_run_does_not_write_records() -> None:
    temp_dir, database_url = setup_db()
    with temp_dir:
        stats = sync_catalog(sample_catalog(), database_url, dry_run=True)
        assert stats.partners_created == 1
        assert stats.offers_created == 1
        assert count_rows(database_url, "telegram_partners") == 0
        assert count_rows(database_url, "telegram_partner_offers") == 0


def test_repeated_sync_does_not_duplicate_records() -> None:
    temp_dir, database_url = setup_db()
    with temp_dir:
        first = sync_catalog(sample_catalog(), database_url)
        second = sync_catalog(sample_catalog(), database_url)
        assert first.partners_created == 1
        assert second.partners_updated == 1
        assert count_rows(database_url, "telegram_partners") == 1
        assert count_rows(database_url, "telegram_partner_offers") == 1
        assert count_rows(database_url, "telegram_partner_photos") == 1


def test_inactive_web_partner_becomes_inactive_tg_partner() -> None:
    temp_dir, database_url = setup_db()
    with temp_dir:
        sync_catalog(sample_catalog(active=True), database_url)
        sync_catalog(sample_catalog(active=False), database_url)
        with connect(database_url) as connection:
            row = connection.execute("SELECT is_active FROM telegram_partners WHERE external_content_id = 101").fetchone()
            assert row["is_active"] == 0


def test_missing_optional_fields_do_not_crash_sync() -> None:
    temp_dir, database_url = setup_db()
    with temp_dir:
        stats = sync_catalog(sample_catalog(missing=True), database_url)
        assert stats.partners_created == 1
        assert stats.offers_created == 1


def test_cleanup_removes_demo_and_route_test_records() -> None:
    temp_dir, database_url = setup_db()
    with temp_dir:
        with connect(database_url) as connection:
            connection.execute("INSERT INTO telegram_partners (title, display_name) VALUES (?, ?)", ("demo-spa", "Demo Spa"))
            connection.execute("INSERT INTO telegram_partners (title, display_name) VALUES (?, ?)", ("demo-fitness", "Demo Fitness"))
            cursor = connection.execute(
                "INSERT INTO telegram_partners (external_content_id, title, display_name) VALUES (?, ?, ?) RETURNING id",
                (999999, "route-test", "route-test"),
            )
            route_id = int(cursor.fetchone()["id"])
            connection.execute(
                "INSERT INTO telegram_partner_photos (partner_id, external_content_id, image_url) VALUES (?, ?, ?)",
                (route_id, 999998, "https://cdn.test/route-test.jpg"),
            )
            connection.execute(
                "INSERT INTO telegram_partners (external_content_id, title, display_name) VALUES (?, ?, ?)",
                (102, "Real", "Real"),
            )
            connection.commit()

        stats = sync_catalog(([], {}, {}, {}), database_url, cleanup=True)
        assert stats.cleanup_partners_removed == 3
        assert stats.cleanup_photos_removed == 1
        with connect(database_url) as connection:
            remaining = connection.execute("SELECT title FROM telegram_partners").fetchall()
            assert [row["title"] for row in remaining] == ["Real"]


def test_backfill_from_content_tables_transfers_partner_and_photo() -> None:
    from telegram_app.scripts.sync_content_to_tg_catalog import fetch_catalog_from_content_tables

    temp_dir, database_url = setup_db()
    with temp_dir:
        with connect(database_url) as connection:
            connection.execute(
                "CREATE TABLE content_partners (id INTEGER PRIMARY KEY, title TEXT, description TEXT, city TEXT, category TEXT, address TEXT, phone TEXT, is_active INTEGER, sort_order INTEGER)"
            )
            connection.execute(
                "CREATE TABLE content_partner_photos (id INTEGER PRIMARY KEY, partner_id INTEGER, image_url TEXT, is_active INTEGER, sort_order INTEGER)"
            )
            connection.execute(
                "INSERT INTO content_partners VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (501, "Тест2", "Desc", "Москва", "Spa", "Addr", "+7", 1, 7),
            )
            connection.execute(
                "INSERT INTO content_partner_photos VALUES (?, ?, ?, ?, ?)",
                (601, 501, "https://cdn.test/test2.jpg", 1, 2),
            )
            connection.commit()

        first = sync_catalog(fetch_catalog_from_content_tables(database_url), database_url, cleanup=True)
        second = sync_catalog(fetch_catalog_from_content_tables(database_url), database_url, cleanup=True)
        assert first.partners_found == 1
        assert first.partners_created == 1
        assert first.partner_photos_created == 1
        assert second.partners_updated == 1
        assert second.partner_photos_updated == 1
        assert count_rows(database_url, "telegram_partners") == 1
        assert count_rows(database_url, "telegram_partner_photos") == 1
        with connect(database_url) as connection:
            partner = connection.execute("SELECT * FROM telegram_partners WHERE external_content_id = 501").fetchone()
            photo = connection.execute("SELECT * FROM telegram_partner_photos WHERE external_content_id = 601").fetchone()
            assert partner["title"] == "Тест2"
            assert partner["is_active"] == 1
            assert photo["image_url"] == "https://cdn.test/test2.jpg"


def test_prune_with_empty_source_deactivates_all_web_owned_partners_and_offers() -> None:
    temp_dir, database_url = setup_db()
    with temp_dir:
        sync_catalog(sample_catalog(), database_url)
        stats = sync_catalog(([], {}, {}, {}), database_url, prune=True, cleanup=False)
        assert stats.partners_pruned == 1
        assert stats.offers_pruned == 1
        with connect(database_url) as connection:
            partner = connection.execute("SELECT is_active FROM telegram_partners WHERE external_content_id = 101").fetchone()
            offer = connection.execute("SELECT is_active FROM telegram_partner_offers WHERE external_content_id = 201").fetchone()
            assert partner["is_active"] == 0
            assert offer["is_active"] == 0


def test_backfill_does_not_resurrect_deleted_partner_when_web_source_is_empty() -> None:
    from backend.telegram_catalog.repository import list_active_partners

    temp_dir, database_url = setup_db()
    with temp_dir:
        sync_catalog(sample_catalog(), database_url)
        with connect(database_url) as connection:
            connection.execute("DELETE FROM telegram_partners WHERE external_content_id = ?", (101,))
            connection.commit()
        stats = sync_catalog(([], {}, {}, {}), database_url, prune=True, cleanup=False)
        assert stats.partners_created == 0
        with connect(database_url) as connection:
            assert connection.execute("SELECT COUNT(*) AS count FROM telegram_partners WHERE external_content_id = 101").fetchone()["count"] == 0
            assert list_active_partners(connection) == []


def test_production_seed_skips_demo_records(monkeypatch) -> None:
    from backend.seed_telegram_catalog import seed

    temp_dir, database_url = setup_db()
    with temp_dir:
        monkeypatch.setenv("NODE_ENV", "production")
        monkeypatch.setenv("TELEGRAM_APP_DATABASE_URL", database_url)
        seed()
        assert count_rows(database_url, "telegram_partners") == 0


def test_public_catalog_contains_backfilled_partner_after_cleanup() -> None:
    from backend.telegram_catalog.repository import list_active_partners

    temp_dir, database_url = setup_db()
    with temp_dir:
        sync_catalog(sample_catalog(), database_url, cleanup=True)
        with connect(database_url) as connection:
            connection.execute("INSERT INTO telegram_partners (title, display_name) VALUES (?, ?)", ("demo-spa", "Demo Spa"))
            connection.commit()
        sync_catalog(sample_catalog(), database_url, cleanup=True)
        with connect(database_url) as connection:
            partners = list_active_partners(connection)
            titles = [partner["title"] for partner in partners]
            assert "WEB Spa" in titles
            assert "demo-spa" not in titles
