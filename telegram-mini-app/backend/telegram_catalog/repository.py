"""Data access helpers for the local Telegram catalog."""
from __future__ import annotations

from typing import Any


def row_to_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in ("is_active", "is_cover"):
        if key in data:
            data[key] = bool(data[key])
    for key in ("base_price", "member_price", "discount_percent"):
        if key in data and data[key] is not None:
            data[key] = round(float(data[key]), 2)
    return data


def list_active_partners(connection: Any) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT p.*,
               (
                   SELECT COALESCE(ph.image_url, ph.file_path)
                   FROM telegram_partner_photos ph
                   WHERE ph.partner_id = p.id
                   ORDER BY ph.is_cover DESC, ph.sort_order ASC, ph.id ASC
                   LIMIT 1
               ) AS cover,
               (
                   SELECT COUNT(*)
                   FROM telegram_partner_offers o
                   WHERE o.partner_id = p.id AND o.is_active = 1
               ) AS offers_count
        FROM telegram_partners p
        WHERE p.is_active = 1
        ORDER BY p.sort_order ASC, p.id ASC
        """
    ).fetchall()
    return [row_to_dict(row) or {} for row in rows]


def get_active_partner(connection: Any, partner_id: int) -> dict[str, Any] | None:
    partner = row_to_dict(
        connection.execute(
            "SELECT * FROM telegram_partners WHERE id = ? AND is_active = 1", (partner_id,)
        ).fetchone()
    )
    if not partner:
        return None
    partner["photos"] = list_partner_photos(connection, partner_id)
    partner["offers_count"] = count_active_offers(connection, partner_id)
    partner["cover"] = next(
        (
            photo.get("image_url") or photo.get("file_path")
            for photo in partner["photos"]
            if photo.get("is_cover")
        ),
        (partner["photos"][0].get("image_url") or partner["photos"][0].get("file_path"))
        if partner["photos"]
        else None,
    )
    return partner


def list_partner_photos(connection: Any, partner_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT * FROM telegram_partner_photos
        WHERE partner_id = ?
        ORDER BY is_cover DESC, sort_order ASC, id ASC
        """,
        (partner_id,),
    ).fetchall()
    return [row_to_dict(row) or {} for row in rows]


def count_active_offers(connection: Any, partner_id: int) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM telegram_partner_offers WHERE partner_id = ? AND is_active = 1",
        (partner_id,),
    ).fetchone()
    return int(row["count"] if row else 0)


def list_active_offers(connection: Any, partner_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT * FROM telegram_partner_offers
        WHERE partner_id = ? AND is_active = 1
        ORDER BY sort_order ASC, id ASC
        """,
        (partner_id,),
    ).fetchall()
    return [row_to_dict(row) or {} for row in rows]


def list_admin_partners(connection: Any) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM telegram_partners ORDER BY sort_order ASC, id ASC"
    ).fetchall()
    return [row_to_dict(row) or {} for row in rows]


def list_admin_offers(connection: Any, partner_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT * FROM telegram_partner_offers
        WHERE partner_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (partner_id,),
    ).fetchall()
    return [row_to_dict(row) or {} for row in rows]
