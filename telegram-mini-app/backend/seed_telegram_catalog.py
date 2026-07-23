"""Seed local development data for the Telegram catalog."""
from __future__ import annotations

import os

from backend.telegram_catalog.database import connect, init_db

PARTNERS = [
    {
        "title": "demo-spa",
        "display_name": "Demo Spa",
        "description": "Тестовый wellness-партнёр для локальной TG БД.",
        "city": "Москва",
        "category": "Красота",
        "address": "Демо-улица, 1",
        "phone": "+7 000 000-00-01",
        "sort_order": 10,
        "photo": "https://placehold.co/800x600?text=Demo+Spa",
        "offers": [
            {
                "title": "Демо-массаж",
                "description": "Тестовая услуга без реальных персональных данных.",
                "conditions": "Доступно только в локальной dev-среде.",
                "base_price": 5000,
                "member_price": 3500,
                "discount_percent": 30,
                "sort_order": 10,
            },
            {
                "title": "Демо-уход",
                "description": "Пример оффера для проверки UI на следующем этапе.",
                "conditions": "Не является реальным предложением.",
                "base_price": 7000,
                "member_price": 4900,
                "discount_percent": 30,
                "sort_order": 20,
            },
        ],
    },
    {
        "title": "demo-fitness",
        "display_name": "Demo Fitness",
        "description": "Тестовый fitness-партнёр для локального каталога.",
        "city": "Санкт-Петербург",
        "category": "Спорт",
        "address": "Демо-проспект, 2",
        "phone": "+7 000 000-00-02",
        "sort_order": 20,
        "photo": "https://placehold.co/800x600?text=Demo+Fitness",
        "offers": [
            {
                "title": "Демо-тренировка",
                "description": "Тестовая персональная тренировка.",
                "conditions": "Только для локальной разработки.",
                "base_price": 3000,
                "member_price": 2100,
                "discount_percent": 30,
                "sort_order": 10,
            }
        ],
    },
]


def seed() -> None:
    if os.environ.get("NODE_ENV") == "production":
        print("Skipping Telegram catalog demo seed in production")
        return
    init_db()
    with connect() as connection:
        for partner in PARTNERS:
            existing = connection.execute(
                "SELECT id FROM telegram_partners WHERE title = ?", (partner["title"],)
            ).fetchone()
            if existing:
                continue
            cursor = connection.execute(
                """
                INSERT INTO telegram_partners
                    (title, display_name, description, city, category, address, phone, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    partner["title"],
                    partner["display_name"],
                    partner["description"],
                    partner["city"],
                    partner["category"],
                    partner["address"],
                    partner["phone"],
                    partner["sort_order"],
                ),
            )
            partner_id = int(cursor.fetchone()["id"])
            connection.execute(
                """
                INSERT INTO telegram_partner_photos (partner_id, image_url, sort_order, is_cover)
                VALUES (?, ?, 0, 1)
                """,
                (partner_id, partner["photo"]),
            )
            for offer in partner["offers"]:
                connection.execute(
                    """
                    INSERT INTO telegram_partner_offers
                        (partner_id, title, description, conditions, base_price,
                         member_price, discount_percent, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        partner_id,
                        offer["title"],
                        offer["description"],
                        offer["conditions"],
                        offer["base_price"],
                        offer["member_price"],
                        offer["discount_percent"],
                        offer["sort_order"],
                    ),
                )
        connection.commit()
    print("Telegram catalog development seed data loaded")


if __name__ == "__main__":
    seed()
