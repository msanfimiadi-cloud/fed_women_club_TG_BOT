# План безопасного отвязывания Telegram Mini App от WEB partner API

## 1. Цель и границы PR

Этот документ фиксирует аудит текущих зависимостей Telegram Mini App от API основного сайта `bloomclub.ru` и предлагает поэтапный план переноса партнёрского каталога в независимую TG-базу и локальный TG API.

В рамках этого PR **нет runtime-изменений**:

- не меняются текущие API clients;
- не меняется UI;
- не меняются карточки партнёров;
- не меняются фото/галерея;
- не меняется login;
- не меняется account linking;
- не добавляются секреты и переменные окружения в runtime.

Основной сайт `bloomclub.ru`, VK Mini App, backend основного сайта, account linking backend и сайт `bloomclub.ru` не изменяются.

## 2. Текущая картина зависимостей

Сейчас `telegram-mini-app` настроен как второй frontend к существующему backend Bloom Club: README прямо указывает, что приложение не владеет каталогом партнёров, фото, офферами, подписками, verifications, savings, платежами, админкой или отдельной БД. Базовый frontend API по умолчанию — `https://bloomclub.ru/api/v1`.

Единый API client хранит `API_BASE_URL`, получает access token после Telegram login и затем использует тот же `request(...)` / `fetch(...)` слой для identity-запросов и партнёрских данных. Поэтому при открытии раздела «Партнёры» приложение сейчас обращается к WEB backend основного сайта.

## 3. Найденные WEB API вызовы, связанные с партнёрами

### 3.1 Каталог партнёров

- `GET /clients/catalog/partners` объявлен как `CATALOG_PARTNERS_PATH`.
- `getPartnersAttempt(...)` делает `fetch(target.url)` на этот путь, добавляет `Authorization: Bearer <token>` при наличии токена, парсит ответ и возвращает партнёров через `extractPartnersFromResponse(...)`.
- `getPartners()` выполняет retry для каталога.
- В `App.tsx` каталог загружается при открытии страницы партнёров через `getPartners()`.

Вывод: это основная зависимость раздела «Партнёры» от WEB backend.

### 3.2 Офферы/услуги партнёра

- `getPartnerOffersPath(partnerId)` формирует `GET /clients/partners/{partnerId}/offers`.
- `getPartnerOffers(partnerId)` запрашивает этот путь через общий `request(...)`.
- В `App.tsx` при выборе партнёра вычисляется numeric `partner.id`, диагностический `offersUrlPath`, затем вызывается `getPartnerOffers(...)`.
- README фиксирует важный контракт: для offers используется только numeric `partner.id`, а ответ ожидается как plain array.

Вывод: карточка партнёра и список услуг/офферов зависят от WEB backend.

### 3.3 Фотографии, изображения и галерея

Отдельного endpoint для фото в текущем frontend не найдено. Фото приходят в payload партнёров/офферов и читаются из полей:

- партнёры: `photo_url`, `photos`, `image_url`, `images`, `gallery`;
- офферы: `image_url`, `photo_url`, `photos`.

`PartnerPage` строит галерею из нормализованных изображений партнёра и показывает картинки офферов. README дополнительно фиксирует, что offer cards используют backend/VK поля `image_url`, `photo_url`, `photos`.

Вывод: media-зависимость встроена в WEB payload каталога и offers. После миграции локальный TG API должен отдавать фото/галерею без обращения к `bloomclub.ru`.

### 3.4 Услуги, цены, условия и расчёт выгоды

Frontend берёт из WEB payload офферов поля, связанные с услугами и ценами:

- `title`, `description`, `benefit_text`, `conditions`;
- `base_price`, `discount_percent`, возможную member price;
- `image_url`, `photo_url`, `photos`.

Если готовой member price нет, frontend вычисляет её из `base_price * (1 - discount_percent / 100)` и считает saving как `base_price - memberPrice`. В `PartnerPage` эти значения отображаются в карточках офферов.

Вывод: услуги/офферы, цены, условия и локальный расчёт экономии на карточке оффера сейчас зависят от WEB response по offers.

### 3.5 Проверка/получение кода привилегии

- `verifyPartnerOffer(partnerId, offerId)` вызывает `POST /clients/partners/{partnerId}/verify` и отправляет `{ "privilege_id": offerId }`.
- В `App.tsx` `createVerification(...)` вызывает `verifyPartnerOffer(...)`, кладёт verification в локальное состояние, затем обновляет список через `getVerifications()`.
- README фиксирует такой же контракт, как у VK Mini App.

Вывод: создание кода/проверки привилегии для партнёра сейчас завязано на WEB backend.

### 3.6 Verifications

- `getVerifications()` вызывает `GET /clients/me/verifications`.
- Этот запрос выполняется во время bootstrap параллельно с savings, cities и linking status.
- После создания verification список дополнительно refresh-ится через тот же endpoint.

Вывод: список привилегий/проверок пользователя сейчас находится в WEB backend. Для миграции нужно решить, остаётся ли это единым WEB ledger или переезжает в TG local ledger.

### 3.7 Savings

- `getSavings()` вызывает `GET /clients/me/savings`.
- Этот запрос выполняется во время bootstrap и используется страницей «Экономия».

Вывод: агрегированная экономия сейчас находится в WEB backend. Для миграции нужно решить, считается ли TG-экономия локально только по TG-привилегиям или остаётся общей по всем платформам.

## 4. WEB API вызовы, которые нужно оставить

Эти вызовы должны оставаться связанными с `bloomclub.ru`, потому что они относятся к identity, профилю, подписке, trial protection и синхронизации личного кабинета между Telegram Mini App, VK Mini App и сайтом:

- `POST /auth/telegram-miniapp-login` — Telegram login, backend validation `initData`, выдача access token.
- `GET /clients/me` — профиль клиента.
- `PATCH /clients/me` — обновление профиля клиента, если TG frontend продолжает редактировать общий профиль.
- `GET /clients/me/subscription` — единое состояние подписки.
- `POST /clients/me/trial-subscription` — trial, пока trial protection единый.
- `GET /clients/me/linking-status` — статус account linking.
- `POST /clients/me/linking/start` — старт linking flow.
- `POST /clients/me/linking/confirm` — подтверждение linking flow.

Дополнительно в коде присутствуют платежные `/clients/me/payment-requests` и `/clients/me/payment-requests/{id}/mark-paid`, а также `GET /clients/cities`. Они не являются partner API и не входят в этот план миграции партнёрского каталога, но при проектировании `webIdentityClient` нужно отдельно решить, остаются ли они в WEB identity/account контуре или получают отдельный TG-контур.

## 5. Разделение зависимостей

### A. Оставить WEB API

- Авторизация Telegram: `POST /auth/telegram-miniapp-login`.
- Профиль клиента: `GET /clients/me`, при необходимости `PATCH /clients/me`.
- Подписка и trial: `GET /clients/me/subscription`, `POST /clients/me/trial-subscription`, пока подписка единая для WEB/VK/TG.
- Account linking: `GET /clients/me/linking-status`, `POST /clients/me/linking/start`, `POST /clients/me/linking/confirm`.
- Синхронизация личного кабинета клиента между Telegram Mini App, VK Mini App и сайтом.

### B. Вынести в TG Local API

- Каталог партнёров.
- Карточку/детали партнёра.
- Фотографии партнёров, cover, gallery.
- Услуги/офферы партнёров.
- Цены, скидки, условия и benefit-тексты.
- Получение/создание кода привилегии.
- Список TG-привилегий пользователя.
- Экономию по TG-привилегиям.

### C. Требует продуктового/архитектурного решения

- `verifications`: оставить в WEB как единый ledger для всех платформ или перенести TG-проверки в TG local ledger.
- `savings`: считать глобально в WEB или отдельно в TG по TG-привилегиям.
- `privilege codes`: использовать единые коды на все платформы или отдельные TG-коды.
- `active access`: проверять доступ через WEB subscription/account state, но создавать код в TG backend.
- `cities`: нужен ли каталог городов из WEB для TG-каталога или city должен быть частью локальных TG partner records.
- Платежи/продление: оставить вне partner migration или запланировать отдельный billing-контур.

## 6. Целевая архитектура Telegram Mini App

### 6.1 Разделение клиентов

Предлагаем разделить API слой на два независимых клиента.

#### `webIdentityClient`

Ходит только в `bloomclub.ru` и отвечает за:

- Telegram login;
- профиль клиента;
- подписку и trial state;
- account linking;
- синхронизацию личного кабинета между WEB/VK/TG;
- проверку active access перед выдачей TG-кода, если будет выбран вариант «access проверяем в WEB, code создаём в TG».

`webIdentityClient` не должен иметь методов для каталога партнёров, offers, photos, codes, verifications/savings партнёрского каталога после завершения миграции.

#### `tgCatalogClient`

Ходит только в локальный TG backend/API и отвечает за:

- partners;
- partner details;
- partner photos/gallery;
- offers/services/prices/conditions;
- создание TG privilege code / verification;
- список TG verifications;
- TG savings.

После переключения никакие данные партнёров не должны запрашиваться с `bloomclub.ru`.

### 6.2 Будущие env-переменные

```env
VITE_WEB_IDENTITY_API_BASE_URL=https://bloomclub.ru/api/v1
VITE_TG_API_BASE_URL=<current TG app backend origin>
VITE_TG_LOCAL_CATALOG_ENABLED=true
```

Рекомендации:

- `VITE_WEB_IDENTITY_API_BASE_URL` использовать только в `webIdentityClient`.
- `VITE_TG_API_BASE_URL` использовать только в `tgCatalogClient`.
- `VITE_TG_LOCAL_CATALOG_ENABLED` на первых этапах включает новый catalog flow без удаления старого кода.
- Не хранить `TELEGRAM_BOT_TOKEN`, `BOT_TOKEN`, backend secrets, access token fixtures или Telegram `initData` в frontend env и репозитории.

## 7. Будущие TG local endpoints

Минимальный набор endpoints для независимого TG-каталога:

- `GET /api/tg/partners` — список активных партнёров, фильтры по городу/категории, cover/photo summary.
- `GET /api/tg/partners/{partner_id}` — детали партнёра, контакты, адрес, описание, gallery.
- `GET /api/tg/partners/{partner_id}/offers` — активные офферы партнёра, цены, условия, фото офферов.
- `POST /api/tg/partners/{partner_id}/offers/{offer_id}/verify` — создать TG privilege code / verification. Перед созданием backend может проверить WEB active access.
- `GET /api/tg/me/verifications` — список TG-привилегий/кодов пользователя.
- `GET /api/tg/me/savings` — экономия по TG-привилегиям.

Возможные расширения для TG admin/API:

- `POST /api/tg/admin/partners`;
- `PATCH /api/tg/admin/partners/{partner_id}`;
- `POST /api/tg/admin/partners/{partner_id}/photos`;
- `PATCH /api/tg/admin/partners/{partner_id}/offers/{offer_id}`.

## 8. Будущие TG local DB-модели

### `TelegramPartner`

- `id`;
- `title`;
- `display_name`;
- `description`;
- `city`;
- `category`;
- `address`;
- `phone`;
- `is_active`;
- `sort_order`;
- `created_at`;
- `updated_at`.

### `TelegramPartnerPhoto`

- `id`;
- `partner_id`;
- `image_url` или `file_path`;
- `sort_order`;
- `is_cover`;
- `created_at`.

### `TelegramPartnerOffer`

- `id`;
- `partner_id`;
- `title`;
- `description`;
- `conditions`;
- `base_price`;
- `member_price`;
- `discount_percent`;
- `is_active`;
- `sort_order`;
- `created_at`;
- `updated_at`.

### `TelegramPrivilegeCode` / `TelegramVerification`

- `id`;
- `telegram_user_id` или `linked_client_id` / `reference`;
- `partner_id`;
- `offer_id`;
- `code`;
- `status`;
- `expires_at`;
- `used_at`;
- `created_at`.

Рекомендуемые дополнительные поля для аудита и безопасной миграции:

- `web_client_id` / `linked_account_id`, если code зависит от общего WEB account;
- `source_platform = 'telegram'`;
- `web_subscription_checked_at`;
- `access_snapshot`, чтобы понимать, почему код был выдан;
- `metadata` для диагностик без секретов.

## 9. Этапы внедрения

### Этап 1 — аудит и документ, без runtime-изменений

- Зафиксировать найденные WEB partner-зависимости.
- Согласовать группы A/B/C.
- Не менять frontend runtime и существующий API client.

### Этап 2 — добавить локальный TG backend/API и отдельную БД

- Поднять TG backend рядом с Telegram Mini App deployment.
- Добавить модели `TelegramPartner`, `TelegramPartnerPhoto`, `TelegramPartnerOffer`, `TelegramPrivilegeCode` / `TelegramVerification`.
- Реализовать read-only endpoints для partners/offers/photos.
- Реализовать verify endpoint с проверкой active access через WEB identity API, если выбран такой вариант.

### Этап 3 — добавить TG admin для партнёров/фото/офферов

- Управление партнёрами, фото и офферами в TG-контуре.
- Валидация цен, скидок, условий и активности.
- Роли/доступы к TG admin без хранения секретов во frontend.

### Этап 4 — переключить frontend каталога на TG local API через feature flag

- Добавить `tgCatalogClient`.
- Использовать `VITE_TG_LOCAL_CATALOG_ENABLED=true` для переключения каталога, offers, photos, verify, verifications и savings.
- Оставить WEB identity/login/profile/subscription/linking без изменений.
- В логах/диагностике явно различать `webIdentityClient` и `tgCatalogClient`.

### Этап 5 — убрать fallback на WEB partner API

- После проверки данных удалить fallback на `/clients/catalog/partners`, `/clients/partners/{id}/offers`, `/clients/partners/{id}/verify`, `/clients/me/verifications`, `/clients/me/savings` для partner-сценариев.
- Оставить только identity/account endpoints на `bloomclub.ru`.

### Этап 6 — проверить отсутствие partner-запросов к bloomclub.ru

- Открыть Telegram Mini App.
- Перейти в «Партнёры».
- Открыть карточку партнёра.
- Создать/получить код привилегии.
- Открыть «Привилегии» и «Экономия».
- Подтвердить в Network/логах, что нет запросов к `https://bloomclub.ru/api/v1/clients/catalog/partners` и `https://bloomclub.ru/api/v1/clients/partners/{id}/offers`.
- Подтвердить, что identity-запросы к `bloomclub.ru` продолжают работать: login, `/clients/me`, subscription, linking.

## 10. Риски

- Дубли партнёров между WEB, VK и TG, если не определить owner/source of truth.
- Рассинхрон цен, условий и описаний между платформами.
- Разные коды привилегий на разных платформах могут путать партнёров и поддержку.
- Нужно решить, где источник правды для подписки и active access.
- Нельзя сломать account linking и trial protection: trial eligibility должна оставаться единой на verified identity, а не на платформу.
- Если TG verification будет локальным, поддержка должна видеть TG-коды или иметь экспорт/интеграцию.
- Если savings станут TG-only, пользователь может видеть разные суммы экономии в TG, VK и WEB.
- Если фото хранить локально, нужен понятный storage/CDN, лимиты загрузки, очистка неиспользуемых файлов и резервное копирование.
- Feature flag и fallback нельзя держать бесконечно: иначе нагрузка на WEB partner API может сохраниться.
- Нужно не логировать Telegram `initData`, hashes, access tokens, bot tokens и privilege codes в небезопасные frontend diagnostics.

## 11. Критерии готовности финальной миграции

- В коде нет partner methods, которые ходят в `VITE_WEB_IDENTITY_API_BASE_URL` / `bloomclub.ru`.
- `rg`/Network подтверждают отсутствие `/clients/catalog/partners` и `/clients/partners/{id}/offers` в активном TG catalog flow.
- `webIdentityClient` содержит только login/profile/subscription/trial/linking/account sync.
- `tgCatalogClient` содержит только TG partners/offers/photos/codes/verifications/savings.
- При открытии «Партнёры» сайт `bloomclub.ru` не получает запросы каталога/офферов/фото партнёров от Telegram Mini App.
