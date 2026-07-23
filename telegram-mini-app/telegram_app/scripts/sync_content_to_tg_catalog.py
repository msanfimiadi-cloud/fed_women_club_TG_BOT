"""Synchronize WEB Content CMS catalog into the Telegram local catalog.

The sync is intentionally additive/idempotent by default: it upserts rows that
carry WEB CMS ids in ``external_content_id`` and never deletes demo/manual rows.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from backend.telegram_catalog.database import connect, init_db, is_postgres_url

JsonDict = dict[str, Any]


@dataclass
class SyncStats:
    partners_created: int = 0
    partners_updated: int = 0
    partner_photos_created: int = 0
    partner_photos_updated: int = 0
    offers_created: int = 0
    offers_updated: int = 0
    offer_photos_created: int = 0
    offer_photos_updated: int = 0
    partners_found: int = 0
    partner_photos_found: int = 0
    partners_pruned: int = 0
    offers_pruned: int = 0
    cleanup_partners_removed: int = 0
    cleanup_photos_removed: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> JsonDict:
        return self.__dict__.copy()


def first_value(data: JsonDict, *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def to_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_active(data: JsonDict) -> int:
    value = first_value(data, "is_active", "active")
    if value is None:
        return 1
    if isinstance(value, str):
        return 0 if value.strip().lower() in {"0", "false", "no", "off"} else 1
    return 1 if bool(value) else 0


def nested_title(value: Any) -> str | None:
    if isinstance(value, dict):
        return first_value(value, "title", "name", "display_name", "slug")
    if value not in (None, ""):
        return str(value)
    return None


def map_partner(item: JsonDict) -> JsonDict:
    title = str(first_value(item, "title", "name", "display_name") or f"partner-{item.get('id')}")
    city = first_value(item, "city", "city_name") or nested_title(item.get("city_id")) or nested_title(item.get("city"))
    category = (
        first_value(item, "category", "category_title")
        or nested_title(item.get("category_id"))
        or nested_title(item.get("category"))
    )
    return {
        "external_content_id": to_int(item.get("id")),
        "title": title,
        "display_name": first_value(item, "display_name", "name", "title") or title,
        "description": first_value(item, "description"),
        "city": city,
        "category": category,
        "address": first_value(item, "address"),
        "phone": first_value(item, "phone"),
        "is_active": to_active(item),
        "sort_order": to_int(item.get("sort_order")),
    }


def map_offer(item: JsonDict, local_partner_id: int) -> JsonDict:
    base_price = to_float(first_value(item, "regular_price", "base_price"))
    member_price = to_float(first_value(item, "club_price", "member_price"))
    discount = to_float(first_value(item, "discount_percent", "saving"))
    if discount is None and base_price and member_price is not None and base_price > 0:
        discount = round((base_price - member_price) / base_price * 100, 2)
    return {
        "external_content_id": to_int(item.get("id")),
        "partner_id": local_partner_id,
        "title": str(first_value(item, "title", "name") or f"offer-{item.get('id')}"),
        "description": first_value(item, "description"),
        "conditions": first_value(item, "terms", "conditions"),
        "base_price": base_price,
        "member_price": member_price,
        "discount_percent": discount,
        "is_active": to_active(item),
        "sort_order": to_int(item.get("sort_order")),
    }


def extract_url(item: JsonDict) -> str | None:
    value = first_value(item, "cover", "photo_url", "image_url", "url", "src")
    if isinstance(value, dict):
        return extract_url(value)
    return str(value) if value else None


def as_list(data: Any) -> list[JsonDict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "results", "data"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    return []


class ContentClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def get(self, path: str, optional: bool = False) -> list[JsonDict]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}", "X-Telegram-Admin-Token": self.token},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return as_list(json.loads(response.read().decode("utf-8") or "[]"))
        except urllib.error.HTTPError as exc:
            if optional and exc.code in {404, 405}:
                return []
            raise RuntimeError(f"WEB Content API {path} returned HTTP {exc.code}") from exc


def column_exists(connection: Any, table: str, column: str, postgres: bool) -> bool:
    if postgres:
        row = connection.execute(
            "SELECT 1 AS ok FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
            (table, column),
        ).fetchone()
        return bool(row)
    return any(row["name"] == column for row in connection.execute(f"PRAGMA table_info({table})").fetchall())


def table_exists(connection: Any, table: str, postgres: bool) -> bool:
    if postgres:
        return bool(connection.execute("SELECT to_regclass(?) AS name", (table,)).fetchone()["name"])
    return bool(connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def ensure_sync_schema(connection: Any, database_url: str) -> None:
    postgres = is_postgres_url(database_url)
    for table in ("telegram_partners", "telegram_partner_offers"):
        if not column_exists(connection, table, "external_content_id", postgres):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN external_content_id INTEGER")
        connection.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{table}_external_content_id "
            f"ON {table} (external_content_id) WHERE external_content_id IS NOT NULL"
        )
    if table_exists(connection, "telegram_partner_photos", postgres) and not column_exists(connection, "telegram_partner_photos", "external_content_id", postgres):
        connection.execute("ALTER TABLE telegram_partner_photos ADD COLUMN external_content_id INTEGER")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_telegram_partner_photos_external_content_id ON telegram_partner_photos (external_content_id) WHERE external_content_id IS NOT NULL")
    if table_exists(connection, "telegram_offer_photos", postgres) and not column_exists(connection, "telegram_offer_photos", "external_content_id", postgres):
        connection.execute("ALTER TABLE telegram_offer_photos ADD COLUMN external_content_id INTEGER")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_telegram_offer_photos_external_content_id ON telegram_offer_photos (external_content_id) WHERE external_content_id IS NOT NULL")


def fetch_catalog(client: ContentClient) -> tuple[list[JsonDict], dict[int, list[JsonDict]], dict[int, list[JsonDict]], dict[int, list[JsonDict]]]:
    partners = client.get("/admin/partners")
    partner_photos: dict[int, list[JsonDict]] = {}
    offers: dict[int, list[JsonDict]] = {}
    offer_photos: dict[int, list[JsonDict]] = {}
    for partner in partners:
        pid = to_int(partner.get("id"))
        if not pid:
            continue
        partner_photos[pid] = client.get(f"/admin/partners/{pid}/photos", optional=True)
        offers[pid] = client.get(f"/admin/partners/{pid}/offers", optional=True)
        for offer in offers[pid]:
            oid = to_int(offer.get("id"))
            if oid:
                offer_photos[oid] = client.get(f"/admin/offers/{oid}/photos", optional=True)
    return partners, partner_photos, offers, offer_photos


def upsert(connection: Any, table: str, values: JsonDict, stats: SyncStats, created_attr: str, updated_attr: str, dry_run: bool, has_external_id: bool = True) -> int:
    existing = None
    if has_external_id:
        existing = connection.execute(f"SELECT id FROM {table} WHERE external_content_id = ?", (values["external_content_id"],)).fetchone()
    if existing:
        setattr(stats, updated_attr, getattr(stats, updated_attr) + 1)
        if not dry_run:
            cols = [k for k in values if k not in {"external_content_id"}]
            connection.execute(
                f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in cols)}, updated_at = CURRENT_TIMESTAMP WHERE external_content_id = ?",
                tuple(values[c] for c in cols) + (values["external_content_id"],),
            )
        return int(existing["id"])
    setattr(stats, created_attr, getattr(stats, created_attr) + 1)
    if dry_run:
        return -to_int(values["external_content_id"])
    cols = list(values)
    cursor = connection.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)}) RETURNING id",
        tuple(values[c] for c in cols),
    )
    return int(cursor.fetchone()["id"])


def sync_catalog(catalog: tuple[list[JsonDict], dict[int, list[JsonDict]], dict[int, list[JsonDict]], dict[int, list[JsonDict]]], database_url: str, dry_run: bool = False, prune: bool = False, cleanup: bool = False) -> SyncStats:
    stats = SyncStats()
    partners, partner_photos, offers_by_partner, offer_photos = catalog
    stats.partners_found = len(partners)
    stats.partner_photos_found = sum(len(photos) for photos in partner_photos.values())
    if not dry_run:
        init_db(database_url)
    with connect(database_url) as connection:
        if not dry_run:
            ensure_sync_schema(connection, database_url)
        postgres = is_postgres_url(database_url)
        has_partner_external_id = column_exists(connection, "telegram_partners", "external_content_id", postgres)
        has_offer_external_id = column_exists(connection, "telegram_partner_offers", "external_content_id", postgres)
        has_partner_photo_external_id = column_exists(connection, "telegram_partner_photos", "external_content_id", postgres)
        offer_photo_table = table_exists(connection, "telegram_offer_photos", postgres)
        has_offer_photo_external_id = (
            offer_photo_table and column_exists(connection, "telegram_offer_photos", "external_content_id", postgres)
        )
        if cleanup:
            cleanup_demo_test_records(connection, stats, dry_run)
        seen_partner_ids: set[int] = set()
        seen_offer_ids: set[int] = set()
        for partner in partners:
            mapped_partner = map_partner(partner)
            if not mapped_partner["external_content_id"]:
                continue
            local_partner_id = upsert(connection, "telegram_partners", mapped_partner, stats, "partners_created", "partners_updated", dry_run, has_partner_external_id)
            seen_partner_ids.add(mapped_partner["external_content_id"])
            photos = partner_photos.get(mapped_partner["external_content_id"], [])
            if not photos and extract_url(partner):
                photos = [{"id": mapped_partner["external_content_id"], "image_url": extract_url(partner), "is_active": True}]
            active_photos = [p for p in photos if to_active(p)] or photos
            for index, photo in enumerate(active_photos):
                url = extract_url(photo)
                if not url:
                    continue
                ext_id = to_int(photo.get("id"), mapped_partner["external_content_id"] * 100000 + index)
                existing = connection.execute("SELECT id FROM telegram_partner_photos WHERE external_content_id = ?", (ext_id,)).fetchone() if has_partner_photo_external_id else None
                if existing:
                    stats.partner_photos_updated += 1
                    if not dry_run:
                        connection.execute("UPDATE telegram_partner_photos SET partner_id=?, image_url=?, sort_order=?, is_cover=? WHERE external_content_id=?", (local_partner_id, url, to_int(photo.get("sort_order"), index), 1 if index == 0 else 0, ext_id))
                else:
                    stats.partner_photos_created += 1
                    if not dry_run:
                        connection.execute("INSERT INTO telegram_partner_photos (partner_id, image_url, sort_order, is_cover, external_content_id) VALUES (?, ?, ?, ?, ?)", (local_partner_id, url, to_int(photo.get("sort_order"), index), 1 if index == 0 else 0, ext_id))
            for offer in offers_by_partner.get(mapped_partner["external_content_id"], []):
                mapped_offer = map_offer(offer, local_partner_id)
                if not mapped_offer["external_content_id"]:
                    continue
                local_offer_id = upsert(connection, "telegram_partner_offers", mapped_offer, stats, "offers_created", "offers_updated", dry_run, has_offer_external_id)
                seen_offer_ids.add(mapped_offer["external_content_id"])
                if offer_photo_table:
                    for index, photo in enumerate(offer_photos.get(mapped_offer["external_content_id"], [])):
                        url = extract_url(photo)
                        if not url:
                            continue
                        ext_id = to_int(photo.get("id"), mapped_offer["external_content_id"] * 100000 + index)
                        existing = (
                            connection.execute("SELECT id FROM telegram_offer_photos WHERE external_content_id = ?", (ext_id,)).fetchone()
                            if has_offer_photo_external_id
                            else None
                        )
                        if existing:
                            stats.offer_photos_updated += 1
                            if not dry_run:
                                connection.execute("UPDATE telegram_offer_photos SET offer_id=?, image_url=?, sort_order=?, is_cover=? WHERE external_content_id=?", (local_offer_id, url, to_int(photo.get("sort_order"), index), 1 if index == 0 else 0, ext_id))
                        else:
                            stats.offer_photos_created += 1
                            if not dry_run:
                                connection.execute("INSERT INTO telegram_offer_photos (offer_id, image_url, sort_order, is_cover, external_content_id) VALUES (?, ?, ?, ?, ?)", (local_offer_id, url, to_int(photo.get("sort_order"), index), 1 if index == 0 else 0, ext_id))
        if prune:
            partner_filter = ""
            partner_params: tuple[Any, ...] = ()
            if seen_partner_ids:
                placeholders = ", ".join("?" for _ in seen_partner_ids)
                partner_filter = f" AND external_content_id NOT IN ({placeholders})"
                partner_params = tuple(seen_partner_ids)
            rows = connection.execute(
                f"SELECT COUNT(*) AS count FROM telegram_partners WHERE external_content_id IS NOT NULL{partner_filter} AND is_active = 1",
                partner_params,
            ).fetchone()
            stats.partners_pruned = int(rows["count"])
            if not dry_run:
                connection.execute(
                    f"UPDATE telegram_partners SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE external_content_id IS NOT NULL{partner_filter}",
                    partner_params,
                )

            offer_filter = ""
            offer_params: tuple[Any, ...] = ()
            if seen_offer_ids:
                placeholders = ", ".join("?" for _ in seen_offer_ids)
                offer_filter = f" AND external_content_id NOT IN ({placeholders})"
                offer_params = tuple(seen_offer_ids)
            rows = connection.execute(
                f"SELECT COUNT(*) AS count FROM telegram_partner_offers WHERE external_content_id IS NOT NULL{offer_filter} AND is_active = 1",
                offer_params,
            ).fetchone()
            stats.offers_pruned = int(rows["count"])
            if not dry_run:
                connection.execute(
                    f"UPDATE telegram_partner_offers SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE external_content_id IS NOT NULL{offer_filter}",
                    offer_params,
                )
        if not dry_run:
            connection.commit()
    return stats


def table_columns(connection: Any, table: str, postgres: bool) -> set[str]:
    if postgres:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,)
        ).fetchall()
        return {str(row["column_name"]) for row in rows}
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def select_table_dicts(connection: Any, table: str, postgres: bool) -> list[JsonDict]:
    if not table_exists(connection, table, postgres):
        return []
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY id ASC").fetchall()]


def enrich_content_partners(connection: Any, partners: list[JsonDict], postgres: bool) -> None:
    columns = table_columns(connection, "content_partners", postgres) if table_exists(connection, "content_partners", postgres) else set()
    for ref_column, output_key, table_names in (
        ("city_id", "city_name", ("content_cities", "cities")),
        ("category_id", "category_title", ("content_categories", "categories")),
    ):
        if ref_column not in columns:
            continue
        for table_name in table_names:
            if not table_exists(connection, table_name, postgres):
                continue
            ref_columns = table_columns(connection, table_name, postgres)
            title_column = next((name for name in ("title", "name", "display_name", "slug") if name in ref_columns), None)
            if not title_column:
                continue
            rows = connection.execute(f"SELECT id, {title_column} AS title FROM {table_name}").fetchall()
            lookup = {int(row["id"]): row["title"] for row in rows if row["id"] is not None}
            for partner in partners:
                value = partner.get(ref_column)
                if value not in (None, "") and output_key not in partner:
                    partner[output_key] = lookup.get(to_int(value))
            break


def fetch_catalog_from_content_tables(database_url: str) -> tuple[list[JsonDict], dict[int, list[JsonDict]], dict[int, list[JsonDict]], dict[int, list[JsonDict]]]:
    with connect(database_url) as connection:
        postgres = is_postgres_url(database_url)
        partners = select_table_dicts(connection, "content_partners", postgres)
        enrich_content_partners(connection, partners, postgres)
        photos_by_partner: dict[int, list[JsonDict]] = {}
        for photo in select_table_dicts(connection, "content_partner_photos", postgres):
            partner_id = to_int(first_value(photo, "partner_id", "content_partner_id"))
            if partner_id:
                photos_by_partner.setdefault(partner_id, []).append(photo)
        return partners, photos_by_partner, {}, {}


def cleanup_demo_test_records(connection: Any, stats: SyncStats, dry_run: bool) -> None:
    demo_titles = ("demo-spa", "demo-fitness")
    demo_names = ("Demo Spa", "Demo Fitness")
    rows = connection.execute(
        """
        SELECT id FROM telegram_partners
        WHERE title IN (?, ?)
           OR display_name IN (?, ?)
           OR external_content_id = 999999
        """,
        (*demo_titles, *demo_names),
    ).fetchall()
    partner_ids = [int(row["id"]) for row in rows]
    route_photo = connection.execute(
        "SELECT COUNT(*) AS count FROM telegram_partner_photos WHERE external_content_id = ?", (999998,)
    ).fetchone()
    stats.cleanup_partners_removed = len(partner_ids)
    stats.cleanup_photos_removed = int(route_photo["count"] if route_photo else 0)
    if dry_run:
        return
    connection.execute("DELETE FROM telegram_partner_photos WHERE external_content_id = ?", (999998,))
    for partner_id in partner_ids:
        connection.execute("DELETE FROM telegram_partners WHERE id = ?", (partner_id,))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--cleanup", action="store_true", default=True)
    parser.add_argument("--no-cleanup", action="store_false", dest="cleanup")
    parser.add_argument("--source", choices=("tables", "api"), default="tables")
    args = parser.parse_args(argv)
    database_url = os.environ.get("TELEGRAM_APP_DATABASE_URL")
    base_url = os.environ.get("WEB_CONTENT_API_BASE_URL")
    token = os.environ.get("TELEGRAM_ADMIN_API_TOKEN")
    required = [("TELEGRAM_APP_DATABASE_URL", database_url)]
    if args.source == "api":
        required.extend((("WEB_CONTENT_API_BASE_URL", base_url), ("TELEGRAM_ADMIN_API_TOKEN", token)))
    missing = [name for name, value in required if not value]
    if missing:
        print(f"Missing required env: {', '.join(missing)}", file=sys.stderr)
        return 2
    catalog = (
        fetch_catalog(ContentClient(base_url, token))
        if args.source == "api"
        else fetch_catalog_from_content_tables(database_url)
    )
    stats = sync_catalog(catalog, database_url, dry_run=args.dry_run, prune=args.prune, cleanup=args.cleanup)
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
