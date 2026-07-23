# Bloom Club Telegram Admin Bot

Отдельный Telegram-бот для управления контентом Bloom Club / Женский клуб НСК. Бот работает как сервер-сервер интеграция: администратор управляет данными в Telegram, бот обращается к WEB Content Admin API, а клиентский Telegram Mini App остаётся только клиентским приложением.

## Назначение

Stage 1 закрывает базовые операции без админки внутри Mini App:

- создание партнёров;
- загрузка фото партнёров;
- добавление услуг партнёрам;
- загрузка фото услуг;
- просмотр списка партнёров;
- скрытие и показ партнёров и услуг через `is_active`;
- создание, просмотр, редактирование, публикация и скрытие розыгрышей;
- загрузка фото розыгрышей через общий upload endpoint и endpoint фото розыгрышей, если он доступен;
- управление призами розыгрышей: список, создание, редактирование, фото, скрытие и публикация.

Физическое удаление партнёров, услуг и розыгрышей намеренно не реализовано.

## Env переменные

Создайте `.env` в директории `admin_bot/` по примеру `.env.example`:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_IDS=
WEB_CONTENT_API_BASE_URL=https://bloomclub.ru/api/content
WEB_API_BASE_URL=https://bloomclub.ru/api/v1
TELEGRAM_ADMIN_API_TOKEN=
BOT_SERVICE_TOKEN=
BROWSER_APP_PUBLIC_URL=https://app.bloomclub.ru
```

Переменные:

- `TELEGRAM_BOT_TOKEN` — токен Telegram-бота.
- `TELEGRAM_ADMIN_IDS` — Telegram user id администраторов через запятую, например `123,456`.
- `WEB_CONTENT_API_BASE_URL` — базовый URL Content Admin API.
- `WEB_API_BASE_URL` — базовый URL публичного WEB API для server-to-server Login Code endpoint.
- `BOT_SERVICE_TOKEN` — сервисный Bearer-токен бота для `POST /api/v1/internal/login-code`.
- `BROWSER_APP_PUBLIC_URL` — публичный URL browser-приложения; по умолчанию `https://app.bloomclub.ru`.
- `TELEGRAM_ADMIN_API_TOKEN` — токен для WEB Content Admin API.

При обращении к WEB API бот отправляет заголовки:

- `Authorization: Bearer <TELEGRAM_ADMIN_API_TOKEN>`
- `X-Telegram-Admin-Token: <TELEGRAM_ADMIN_API_TOKEN>`

Секреты, JWT и ответы аутентификации не логируются. Кнопка `🌐 Открыть приложение` запрашивает временный Login Code через `POST /api/v1/internal/login-code`, отправляет пользователю код и inline-кнопку на `BROWSER_APP_PUBLIC_URL` без URL-параметров.

## Локальный запуск

```bash
cd admin_bot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполните .env
python -m admin_bot
```

## Команды бота

- `/start` — открыть главное меню.
- `/admin` — открыть главное меню.
- `/cancel` — отменить любой текущий сценарий.

Реализованные разделы главного меню:

- `➕ Создать партнёра`
- `📋 Список партнёров`
- `🎁 Создать розыгрыш`
- `📋 Список розыгрышей`
- `🏠 Управление главной` — пока заглушка.

Кнопка `❌ Отмена` также отменяет текущий FSM-сценарий.

## Доступ администраторов

Бот пропускает только пользователей, чей `Telegram user id` есть в `TELEGRAM_ADMIN_IDS`. Всем остальным пользователям бот отвечает:

```text
Нет доступа.
```

## Как создать партнёра

1. Нажмите `➕ Создать партнёра`.
2. Последовательно укажите:
   - название партнёра;
   - описание;
   - город кнопкой из справочника `GET /api/content/admin/cities`;
   - категорию кнопкой из справочника `GET /api/content/admin/categories`;
   - адрес;
   - телефон.
3. Отправьте фото партнёра или нажмите `Пропустить`.
4. Бот создаст партнёра через `POST /api/content/admin/partners`, передав выбранные `city_id` и `category_id`.
5. Если фото было отправлено, бот загрузит файл и добавит фото партнёра.

Payload создания партнёра соответствует актуальной схеме Content Admin API:

```json
{
  "name": "Bloom Spa",
  "title": "Bloom Spa",
  "description": "Описание",
  "city_id": 1,
  "category_id": 2,
  "address": "Красный проспект",
  "phone": "+79990000000",
  "is_active": true
}
```

После создания бот спросит: `Партнёр создан. Хотите добавить услугу?`

## Как добавить фото партнёра

1. Откройте `📋 Список партнёров`.
2. Выберите партнёра.
3. Нажмите `📷 Фото`.
4. Нажмите `➕ Добавить фото`.
5. Отправьте Telegram photo или document формата `jpg`, `png`, `webp` до 10 MB.

Бот скачает файл через Telegram Bot API во временный файл, отправит его в `POST /api/content/uploads`, получит URL и передаст URL в `POST /api/content/admin/partners/{id}/photos`. Временный файл удаляется после загрузки.

Если endpoint фото возвращает список, бот показывает id и URL фото. Если `PATCH /api/content/admin/partner-photos/{id}` поддерживает `is_main`, доступна кнопка «Сделать главным».

## Как добавить услугу

Добавить услугу можно сразу после создания партнёра или из карточки партнёра:

1. Нажмите `➕ Добавить услугу`.
2. Введите:
   - название услуги;
   - описание услуги;
   - обычную цену;
   - цену для участниц клуба.
3. Бот автоматически рассчитает экономию: `обычная цена - цена клуба`.
4. Введите условия получения услуги.
5. Отправьте фото услуги или нажмите `Пропустить`.

Бот создаст услугу через `POST /api/content/admin/partners/{id}/offers`. Если фото было отправлено, оно добавится через upload endpoint и endpoint фото услуги.

## Как добавить фото услуги

1. Откройте `📋 Список партнёров`.
2. Выберите партнёра.
3. Нажмите `🛍 Услуги`.
4. Выберите услугу.
5. Нажмите `📷 Добавить фото`.
6. Отправьте Telegram photo или document формата `jpg`, `png`, `webp` до 10 MB.

Бот загрузит файл в `POST /api/content/uploads`, затем добавит URL через `POST /api/content/admin/offers/{id}/photos`.


## Как управлять розыгрышами

### Создать розыгрыш

1. Нажмите `🎁 Создать розыгрыш`.
2. Последовательно введите:
   - название;
   - описание;
   - условия участия;
   - дату начала или `-`;
   - дату окончания/дату розыгрыша или `-`.
3. Отправьте фото розыгрыша или нажмите `Пропустить`.

Бот создаёт розыгрыш через `POST /api/content/admin/giveaways`. Для совместимости с разными версиями WEB API в payload передаются варианты полей `title/name`, `terms/conditions`, `starts_at/start_date/date_start`, `ends_at/end_date/draw_date/date`, `is_active/active`. Если фото отправлено, URL также добавляется в payload как `photo_url/image_url/url`; затем бот пробует вызвать `POST /api/content/admin/giveaways/{id}/photos`.

### Посмотреть, изменить, скрыть или опубликовать

1. Нажмите `📋 Список розыгрышей`.
2. Выберите розыгрыш.
3. В карточке доступны:
   - `✏️ Редактировать` — название, описание, условия, дату начала, дату окончания/розыгрыша;
   - `📷 Фото` — загрузить новое фото;
   - `🚫 Скрыть` / `✅ Опубликовать` — обновить `is_active/active`.

Бот читает список через `GET /api/content/admin/giveaways`, карточку через `GET /api/content/admin/giveaways/{id}` и обновляет через `PATCH /api/content/admin/giveaways/{id}`. Если отдельный endpoint фото недоступен, добавление фото выполняется fallback-обновлением полей `photo_url/image_url/url`.

## Как скрыть/показать партнёра

1. Откройте `📋 Список партнёров`.
2. Выберите партнёра.
3. Нажмите `🚫 Скрыть` или `✅ Показать`.

Бот вызывает `PATCH /api/content/admin/partners/{id}` с payload:

```json
{"is_active": false}
```

или

```json
{"is_active": true}
```

## Как скрыть/показать услугу

1. Откройте `📋 Список партнёров`.
2. Выберите партнёра.
3. Нажмите `🛍 Услуги`.
4. Нажмите `🚫 Скрыть` или `✅ Показать` у нужной услуги.

Бот вызывает `PATCH /api/content/admin/offers/{id}` с `is_active=false/true`.

## Используемые WEB endpoints

- `POST /api/content/uploads`
- `GET /api/content/admin/partners`
- `POST /api/content/admin/partners`
- `PATCH /api/content/admin/partners/{id}`
- `GET /api/content/admin/partners/{id}/photos`
- `POST /api/content/admin/partners/{id}/photos`
- `PATCH /api/content/admin/partner-photos/{id}`
- `GET /api/content/admin/partners/{id}/offers`
- `POST /api/content/admin/partners/{id}/offers`
- `PATCH /api/content/admin/offers/{id}`
- `POST /api/content/admin/offers/{id}/photos`
- `GET /api/content/admin/giveaways`
- `GET /api/content/admin/giveaways/{id}`
- `POST /api/content/admin/giveaways`
- `PATCH /api/content/admin/giveaways/{id}`
- `GET /api/content/admin/giveaways/{id}/photos`
- `POST /api/content/admin/giveaways/{id}/photos`
- `PATCH /api/content/admin/giveaway-photos/{id}`
- `GET /api/content/admin/giveaways/{giveaway_id}/items`
- `POST /api/content/admin/giveaways/{giveaway_id}/items`
- `GET /api/content/admin/giveaway-items/{item_id}`
- `PATCH /api/content/admin/giveaway-items/{item_id}`

В клиенте также подготовлены методы для:

- `GET /api/content/admin/offers/{id}/photos`
- `PATCH /api/content/admin/offer-photos/{id}`

## Оставшиеся заглушки

`🏠 Управление главной` остаётся заглушкой: `Раздел управления главной будет добавлен позже.`

Ограничение раздела розыгрышей: точная схема дат и фото зависит от WEB Content Admin API. Бот отправляет несколько совместимых вариантов имён полей и использует fallback на `PATCH /api/content/admin/giveaways/{id}` для фото, если отдельный endpoint фото недоступен.

## Systemd

Пример unit-файла находится в `bloomclub-admin-bot.service.example`.

Установка на сервере может выглядеть так:

```bash
cd /opt/bloomclub/-fed_women_club_mini-app_TELEGA/admin_bot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполните .env
sudo cp bloomclub-admin-bot.service.example /etc/systemd/system/bloomclub-admin-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now bloomclub-admin-bot.service
sudo systemctl status bloomclub-admin-bot.service
```

Если используется virtualenv, замените `ExecStart` в unit-файле на путь к `.venv/bin/python`.

## Как управлять призами розыгрышей

Призы управляются только через WEB Content Admin API из Telegram Admin Bot. Админка в Telegram Mini App не используется.

1. Нажмите `📋 Список розыгрышей`.
2. Выберите нужный розыгрыш.
3. В карточке розыгрыша нажмите `🎁 Призы`.
4. В разделе призов доступны:
   - `📋 Список призов` — открыть список призов выбранного розыгрыша;
   - `➕ Добавить приз` — создать новый приз;
   - `Назад к розыгрышу`.
5. При создании приза бот последовательно попросит:
   - название;
   - описание;
   - `sort_order` числом или `-`;
   - фото приза или `Пропустить`.
6. В карточке приза доступны:
   - `✏️ Редактировать` — название, описание, `sort_order`;
   - `📷 Фото` — загрузить или заменить фото;
   - `🚫 Скрыть` / `✅ Опубликовать` — переключить `is_active`;
   - возврат к списку призов или карточке розыгрыша.

Если список призов пустой, бот показывает понятное сообщение и кнопку добавления первого приза. Физического удаления призов нет: скрытие выполняется через `PATCH /api/content/admin/giveaway-items/{id}` с `is_active=false`.

### Фото призов

Отдельного endpoint для фото призов бот не требует. Фото загружается через общий endpoint:

1. `POST /api/content/uploads` возвращает URL файла.
2. Бот вызывает `PATCH /api/content/admin/giveaway-items/{id}` с payload:

```json
{"image_url": "https://..."}
```

Поддерживаются Telegram photo и document форматов `jpg`, `jpeg`, `png`, `webp` до 10 MB.

### Ручной сценарий проверки призов

1. Запустите бота и выполните `/admin`.
2. Откройте `📋 Список розыгрышей` и выберите существующий розыгрыш.
3. Нажмите `🎁 Призы` → `➕ Добавить приз`.
4. Введите название, описание, `sort_order`, отправьте изображение или нажмите `Пропустить`.
5. Убедитесь, что бот показывает карточку созданного приза.
6. Нажмите `✏️ Редактировать` и измените название, описание или `sort_order`.
7. Нажмите `📷 Фото`, отправьте `jpg/png/webp` до 10 MB и проверьте, что фото обновилось.
8. Нажмите `🚫 Скрыть`, затем `✅ Опубликовать` и проверьте изменение статуса.
9. Вернитесь к списку призов и убедитесь, что приз отображается в списке.

### Endpoints призов розыгрышей

- `GET /api/content/admin/giveaways/{giveaway_id}/items`
- `POST /api/content/admin/giveaways/{giveaway_id}/items`
- `GET /api/content/admin/giveaway-items/{item_id}`
- `PATCH /api/content/admin/giveaway-items/{item_id}`
- `POST /api/content/uploads` — для загрузки фото перед обновлением `image_url`.

## Banner Management

Telegram Admin Bot поддерживает полный цикл управления баннерами `ContentBanner` через существующий Content Admin API. Раздел доступен из главного меню по кнопке «🖼 Баннеры» и содержит список баннеров, создание нового баннера и карточку баннера с действиями редактирования, замены фото, скрытия и публикации.

### Используемые endpoints

- `GET /api/content/admin/banners` — список баннеров для админки.
- `POST /api/content/admin/banners` — создание баннера.
- `PATCH /api/content/admin/banners/{id}` — обновление полей, скрытие/публикация и запись `image_url` после загрузки фото.
- `POST /api/content/uploads` — загрузка jpg/jpeg/png/webp до 10 MB перед обновлением `image_url`.

Бот отправляет и читает поля `title`, `subtitle`, `description`, `image_url`, `link_url`, `cta_text`, `placement`, `sort_order`, `is_active`/`active`. Для совместимости ответы API нормализуются: `active` синхронизируется с `is_active`, альтернативные URL-поля приводятся к `image_url`, альтернативные поля ссылки — к `link_url`, альтернативные CTA-поля — к `cta_text`.

### Ручная проверка

1. Запустите бота и выполните `/admin`.
2. Откройте «🖼 Баннеры» → «📋 Список баннеров». Если баннеров нет, бот покажет сообщение и кнопку создания.
3. Нажмите «➕ Создать баннер» и заполните: заголовок, подзаголовок, описание, ссылку, CTA, placement, sort order и фото либо «Пропустить».
4. После создания бот открывает карточку баннера.
5. В карточке проверьте «✏️ Редактировать» для всех текстовых полей и порядка сортировки.
6. Проверьте «📷 Фото»: бот загружает файл в `POST /api/content/uploads`, затем вызывает `PATCH /api/content/admin/banners/{id}` с `image_url`.
7. Проверьте «🚫 Скрыть» и «✅ Опубликовать»: бот вызывает `PATCH /api/content/admin/banners/{id}` с `is_active` и `active`.

### Ограничения

- Отдельный публичный endpoint `GET /api/content/banners` бот не использует: управление выполняется только через Content Admin API.
- Если WEB API не предоставляет `GET /api/content/admin/banners/{id}`, карточка открывается через fallback из списка баннеров.
- Физическое удаление баннеров не реализовано; доступно только скрытие через `is_active=false`/`active=false`.

## Home Content Management

Telegram Admin Bot поддерживает управление `ContentBlock` для главной страницы через существующий Content Admin API. Раздел доступен из главного меню по кнопке «🏠 Управление главной» / «🏠 Главная»: внутри есть «📋 Контентные блоки», «➕ Создать блок» и возврат назад.

Карточка блока показывает `key`, `placement`, `locale`, `title`, `body`, `metadata_json` и статус. Из карточки доступны редактирование, скрытие и публикация. Список блоков показывает `key`, `placement` и статус.

### Используемые endpoints

- `GET /api/content/admin/blocks` — список контентных блоков.
- `GET /api/content/admin/blocks/{id}` — карточка блока; если endpoint недоступен, бот пробует найти блок в списке по `id` или `key`.
- `POST /api/content/admin/blocks` — создание блока.
- `PATCH /api/content/admin/blocks/{id}` — обновление полей, скрытие и публикация.

Бот отправляет и читает поля `key`, `placement`, `locale`, `title`, `body`, `metadata_json`, `is_active`/`active`. Для совместимости список нормализуется из ключей ответа `blocks`, `results`, `items`, `list` и `data`; статус синхронизируется между `active` и `is_active`.

### Примеры metadata_json

Hero-блок:

```json
{"type":"hero","image_url":"https://cdn.example/hero.jpg","cta_text":"Вступить","cta_url":"https://example.club/join"}
```

CTA-блок:

```json
{"type":"custom_cta","button_text":"Записаться","button_url":"https://example.club/events"}
```

Карусель партнёров:

```json
{"type":"partners_carousel","limit":8,"category":"beauty"}
```

### Ручная проверка

1. Запустите бота и выполните `/admin`.
2. Откройте «🏠 Управление главной» → «📋 Контентные блоки».
3. Нажмите «➕ Создать блок» и заполните `key`, `placement`, `locale`, `title`, `body`, `metadata_json`, активность.
4. Проверьте, что невалидный JSON в `metadata_json` показывает ошибку и не отправляет `POST`/`PATCH` до исправления.
5. Откройте созданный блок из списка и проверьте карточку.
6. Через «✏️ Редактировать» измените `title`, `body`, `metadata_json`, `placement`, `locale`.
7. Проверьте «🚫 Скрыть» и «✅ Опубликовать»: бот вызывает `PATCH /api/content/admin/blocks/{id}` с `is_active` и `active`.

### Ограничения

- Визуальный редактор `metadata_json` не реализован: значение вводится и хранится как текст, но перед отправкой проверяется на валидный JSON.
- Физическое удаление блоков не реализовано; доступно только скрытие через `is_active=false`/`active=false`.
- Управление выполняется только через Content Admin API; WEB backend и Telegram Mini App бот не меняет.

## Reference Management

Раздел «📚 Справочники» в Telegram Admin Bot управляет справочниками Content CMS через существующий WEB Content Admin API. Внутри доступны «🏙 Города» и «🏷 Категории».

### Cities

Поддерживаемые действия:

- список городов;
- создание города с полями `name`, optional `slug`, optional `sort_order`, `is_active/active`;
- редактирование `name`, `slug`, `sort_order`;
- скрытие и публикация через `is_active=false/true` и `active=false/true`.

Используемые endpoints:

- `GET /api/content/admin/cities`
- `POST /api/content/admin/cities`
- `PATCH /api/content/admin/cities/{id}`

### Categories

Поддерживаемые действия:

- список категорий;
- создание категории с полями `title/name`, optional `slug`, optional `sort_order`, `is_active/active`;
- редактирование `title/name`, `slug`, `sort_order`;
- скрытие и публикация через `is_active=false/true` и `active=false/true`.

Используемые endpoints:

- `GET /api/content/admin/categories`
- `POST /api/content/admin/categories`
- `PATCH /api/content/admin/categories/{id}`

### Ручная проверка

1. Запустите бота и выполните `/admin`.
2. Откройте «📚 Справочники».
3. Проверьте «🏙 Города» → «📋 Список городов» и «➕ Добавить город».
4. Создайте город, оставив `slug` или `sort_order` пустыми через «-», затем проверьте карточку.
5. Отредактируйте название, slug и порядок города, затем проверьте скрытие и публикацию.
6. Повторите те же шаги для «🏷 Категории».

### Ограничения

- Физическое удаление городов и категорий не реализовано: отключение выполняется только через `PATCH` с `is_active/active`.
- Отдельные `GET /api/content/admin/cities/{id}` и `GET /api/content/admin/categories/{id}` используются только как best-effort; если WEB API их не поддерживает, бот ищет запись в списке.
- Slug вводится вручную. Если поле оставить пустым, бот не отправляет slug и не выполняет тяжёлую транслитерацию.
- Бот принимает разные форматы list-response: `cities`, `categories`, `items`, `results`, `list`, `data` и plain list.
