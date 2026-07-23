# -fed_women_club_mini-app_TELEGA

Telegram Mini App для Bloom Club. Репозиторий содержит только клиент Telegram Mini App и не должен менять сайт, VK Mini App или серверную часть.

## Account linking / duplicate prevention

В этом PR не реализуется склейка аккаунтов: изменение должно быть отдельной серверной задачей с подтверждением пользователя и поддержкой спорных случаев.

Current duplicate source: backend сейчас может создавать дубли, потому что VK ищет клиента по `vk_user_id`, а Telegram — по `telegram_user_id`. Безопасный flow должен использовать verified phone/email и explicit consent. Trial должен быть один раз на verified identity, а не на платформу.

Целевая архитектура:

- один реальный клиент = один `client_profile` в backend;
- сайт, VK Mini App и Telegram Mini App должны привязываться к одному `client_profile`;
- `client_profile` может иметь `vk_user_id` и `telegram_user_id` одновременно;
- подписка, тестовый период, история экономии и привилегии должны быть общими для сайта, VK Mini App и Telegram Mini App;
- тестовый период нельзя выдавать повторно только потому, что пользователь вошёл с другой платформы;
- нельзя автоматически склеивать аккаунты только по совпавшему phone/email без подтверждения, чтобы не связать разных людей;
- безопасный вариант: подтверждение телефона/email одноразовым кодом, после чего `telegram_user_id`/`vk_user_id` привязывается к существующему профилю;
- если есть конфликт, нужна ручная проверка и админский merge flow.

Будущие backend PR:

- PR A — audit current VK/TG auth duplicate behavior in `fed_women_club_WEB`.
- PR B — add verified phone/email linking flow.
- PR C — prevent repeated trial by verified phone/email/client_profile.
- PR D — admin merge/support tooling for конфликтные профили.
