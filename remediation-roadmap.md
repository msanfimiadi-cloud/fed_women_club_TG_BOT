# Remediation Roadmap — Bloom Club Telegram Layer

Дата повторного анализа: 2026-06-25  
Scope: повторная дедупликация и переприоритизация roadmap после merge первых трёх PR.  
Ограничение: код проекта не изменялся; обновлён только документ `remediation-roadmap.md`.

## 1. Что изменилось после первых трёх PR

Ветка уже содержит merge первых трёх roadmap PR:

- PR-01 / commit `0e80f25`: CMS Home content больше не монтируется как HTML; добавлен `sanitizeCmsHtml`, который конвертирует CMS rich text в инертный plain text, и `HomePage` рендерит очищенный текст обычным `<p>`.
- PR-02 / commit `996132e` (`8bb0190`): в Node production server добавлен repo-owned слой baseline security headers и CSP в report-only режиме по умолчанию; деплой-документация описывает rollout/rollback.
- PR-03 / commit `79e1b1a` (`a715ba1`): frontend auth token больше не пишется в `localStorage` по умолчанию; используется in-memory + `sessionStorage` с TTL и legacy-localStorage gate.

## 2. Итог повторного анализа

Исходный roadmap содержал 45 объединённых roadmap issues из 95 findings трёх аудитов.

После PR-01/PR-02/PR-03:

- Полностью закрыты: **1 roadmap issue**.
- Частично закрыты: **2 roadmap issues**.
- Больше не актуальны в исходной формулировке: **2 roadmap issue/PR formulations**.
- Требуют обновления wording/acceptance criteria: **7 roadmap issues**.
- Новый счётчик активных roadmap issues: **44 активных** + **1 closed**.
- Новый launch verdict: **NO-GO** до закрытия обновлённых P0. Security exposure стал ниже, но production readiness blockers всё ещё открыты.

## 3. Findings, уже устранённые полностью

| ID | Finding | Статус | Почему считается закрытым | Дальнейшее действие |
|---|---|---|---|---|
| RR-001 | Stored XSS через CMS Home block | **Closed** | `HomePage` больше не использует `dangerouslySetInnerHTML` для CMS `body`, а `sanitizeCmsHtml` удаляет scripts/styles/tags, декодирует entities и возвращает plain text. Есть статический regression test на sanitizer/rendering. | Не планировать отдельный PR. Оставить future hardening только если появится новый rich-text renderer. |

## 4. Findings, частично устранённые

| ID | Finding | Статус после PR | Что закрыто | Что осталось |
|---|---|---|---|---|
| RR-002 | JWT/access token хранится в `localStorage` | **Partially closed / downgrade from P0 to P1 residual** | Default `localStorage` persistence убрана; token хранится in-memory + `sessionStorage`, есть TTL 30 минут, max TTL 60 минут, legacy mode gated env flag. | Token всё ещё доступен JS при XSS в текущей вкладке/sessionStorage. HttpOnly/Secure cookie или backend session binding не реализованы. Нужны WEB-backend coordination и acceptance criteria по session model. |
| RR-003 | Нет CSP и baseline security headers | **Partially closed / downgrade from P0 to P1 residual** | Baseline headers добавлены repo-owned middleware: `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS; CSP добавлен как `Content-Security-Policy-Report-Only` по умолчанию; есть deployment docs. | CSP не enforcing по умолчанию; нет evidence по Telegram client matrix/report collection; нет окончательного allowlist для media/connect/script на production. |

## 5. Findings, больше не актуальные в исходной формулировке

| Старый ID/PR | Почему больше не актуально | Новая трактовка |
|---|---|---|
| RR-001 / old PR-01 | Риск unsafe CMS Home HTML закрыт текущей реализацией plain-text sanitizer. | Удалить из First 10 и активных P0. Оставить в разделе Closed. |
| Старый PR-03 wording “no token in localStorage if new model” | Цель “убрать default localStorage” выполнена; повторять PR нельзя. | Заменить на residual P1: HttpOnly/session-binding feasibility + WEB contract, без повторного изменения уже сделанного storage baseline. |

## 6. Roadmap issues, требующие обновления

| ID | Обновление |
|---|---|
| RR-001 | Mark closed. Убрать из P0, phase plan, launch checklist как открытый blocker. |
| RR-002 | Переименовать в “Residual JS-readable auth session hardening”. Снизить с P0 до P1, если владельцы принимают риск sessionStorage + TTL после XSS close. |
| RR-003 | Переименовать в “CSP enforcement and Telegram-compatible security-header rollout”. Снизить с P0 до P1 residual, потому что baseline headers уже есть, но enforcement/evidence отсутствуют. |
| RR-004 | Оставить P0: token storage improvement не заменяет initData validation/replay/rate limiting на auth boundary. |
| RR-013 | Уточнить dependency с RR-003/RR-036: public diagnostics cleanup не должен ломать новые health/header endpoints. |
| RR-014 | Уточнить: login throttling может идти вместе с RR-004; global API/static throttling остаётся отдельным P1/P2 item. |
| RR-022 | Поднять ближе к early P1, потому что дальнейшие auth/session/readiness/proxy изменения требуют явных contracts и tests. |

## 7. Какие PR можно объединить

| Можно объединить | Причина | Условия безопасности |
|---|---|---|
| New PR-01: `/live`/strict `/ready` + missing DB fail-fast | RR-005 и RR-006 имеют общий production failure mode: broken DB/config must fail readiness and catalog must not return fake success. | Один rollout plan для platform healthcheck; explicit no-DB production smoke; не включать migration refactor. |
| New PR-04: release/rollback runbook + BotFather URL guard | RR-008 и RR-025 частично документационные и операционные; BotFather rollback зависит от release runbook. | Docs-only или минимальные checks; no app behavior changes. |
| New PR-05: backup/restore + uploads durability stopgap | RR-010 и RR-012 связаны через data loss/recovery. | Не мигрировать UI/media model в том же PR; include restore drill evidence. |
| New PR-06: auth boundary validation + login throttling | RR-004 и login-specific часть RR-014 лучше тестировать вместе. | Rate limits configurable; separate from global static/API throttling. |
| New PR-08: metrics/alerts + synthetic checks + structured log seed | RR-011 и первый slice RR-026 дают launch observability together. | Не делать полный logging refactor; только requestId/metrics baseline. |
| New PR-10: API contracts + TG backend owner decision | RR-022 и RR-023 связаны: contract tests нужны, чтобы выбрать/зафиксировать production implementation. | Не переписывать обе backend реализации в одном PR; сначала contracts/decision/tests. |

## 8. Какие PR можно удалить или заменить

| Старый PR | Решение | Причина |
|---|---|---|
| Old PR-01: Sanitize CMS content | **Удалить из активного roadmap** | Реализован и merged. |
| Old PR-02: Add CSP/security headers baseline | **Заменить** | Baseline/report-only реализован. Нужен новый P1 PR на CSP enforcement/evidence, не повтор baseline. |
| Old PR-03: Fix token storage/session lifecycle | **Заменить** | Default localStorage устранён. Остался residual session-hardening/Web cookie feasibility. |
| Old PR-08 as “metrics endpoint/exporter full scope” | **Сузить/разделить** | Для launch нужен минимальный metrics + synthetic baseline; full observability можно вынести в P2. |
| Any standalone “public catalog authorization policy” PR before rate limits | **Отложить** | RR-045 зависит от business decision; сначала global abuse controls and launch blockers. |

## 9. Нужно ли изменить приоритеты

Да.

### Priority changes

- RR-001: **P0 → Closed**.
- RR-002: **P0 → P1 residual**, при условии owner acceptance текущей sessionStorage+TTL модели и закрытого Home XSS; если появляются новые unsafe HTML sinks, вернуть residual в P0.
- RR-003: **P0 → P1 residual**, потому что baseline headers уже включены, но CSP enforcement/evidence ещё нужны.
- RR-004: остаётся **P0**, потому что auth boundary/replay/rate limit не закрыты token-storage PR.
- RR-022: **P1, поднять в очереди**, потому что contracts нужны до крупных backend/proxy/sync изменений.
- RR-011: остаётся **P0**, но первый PR должен быть launch-gate minimum viable observability; full dashboards/logging can continue as P2.

## 10. Обновлённые P0/P1/P2/P3

### P0 — launch blockers

| ID | Название | Статус |
|---|---|---|
| RR-004 | Telegram initData validation/replay/login rate limit на auth boundary | Open |
| RR-005 | `/ready` не проверяет зависимости | Open |
| RR-006 | Missing DB URL маскируется пустым каталогом | Open |
| RR-007 | Runtime server выполняет DDL при startup | Open |
| RR-008 | Нет rollback/release runbook и production checklist | Open |
| RR-009 | WEB → TG sync без atomic publish boundary | Open, если catalog production-critical |
| RR-010 | Нет backup/restore runbook и restore drill | Open |
| RR-011 | Нет launch-gate metrics/alerts/synthetic checks | Open |
| RR-012 | Uploads без durable storage/backup policy | Open, если uploads используются |

### P1 — stabilization and security residuals

| ID | Название | Статус |
|---|---|---|
| RR-002R | Residual JS-readable auth session hardening / HttpOnly-session feasibility | New residual from RR-002 |
| RR-003R | CSP enforcement and Telegram-compatible header rollout evidence | New residual from RR-003 |
| RR-013 | Public diagnostics/status раскрывают runtime/details | Open |
| RR-014 | Global API/static/diagnostics rate limiting | Open; login slice can merge with RR-004 |
| RR-015 | Proxy query allowlist/SSRF guard для WEB/Content/Admin API | Open |
| RR-016 | Admin mutations без audit logging и granular permissions | Open |
| RR-017 | Content API failure скрывается как 200 `[]` | Open |
| RR-018 | Frontend state management без единого source of truth | Open |
| RR-019 | URL/router state для partner/offers отсутствует | Open |
| RR-020 | API client смешивает identity/catalog/storage/retry/diagnostics | Open |
| RR-021 | Bootstrap orchestration смешивает critical/secondary requests | Open |
| RR-022 | API contracts/schema отсутствуют | Open; move earlier |
| RR-023 | Две backend реализации TG catalog расходятся | Open |
| RR-024 | Stable identity model: local numeric IDs вместо external_content_id/slug | Open |
| RR-025 | Telegram production validation и BotFather URL guard отсутствуют | Open; docs slice can merge with RR-008 |

### P2 — hardening, scalability, maintainability

| ID | Название | Статус |
|---|---|---|
| RR-026 | Structured logs/requestId/traceId отсутствуют | Open; seed can merge with RR-011 |
| RR-027 | WEB API proxy без circuit breaker/cache/retry policy | Open |
| RR-028 | Frontend retry/recovery/degraded UI model неполная | Open |
| RR-029 | Bundle/chunk/performance budget отсутствует | Open |
| RR-030 | Chunk/assets 404 white screen risk | Open |
| RR-031 | Static asset/cache headers не определены | Open |
| RR-032 | Image/media strategy и external hosts не централизованы | Open |
| RR-033 | DB query performance/indexes/pool sizing не проверены | Open |
| RR-034 | Demo/manual/WEB records ownership и prune policy нестрогие | Open |
| RR-035 | Python sync SQL portability and repository layer | Open |
| RR-036 | Ingress/platform contract under-specified | Open |
| RR-037 | Config inventory and typed validation absent | Open |
| RR-038 | Dependency vulnerability controls absent | Open |
| RR-039 | Admin bot health/observability absent | Open |
| RR-040 | Release versioning not surfaced in runtime/UI | Open |

### P3 — cleanup / refactoring / policy decisions

| ID | Название | Статус |
|---|---|---|
| RR-041 | Node server route abstraction/testability | Open |
| RR-042 | Admin bot god-component decomposition | Open |
| RR-043 | Diagnostics UI visible to all users | Open; can move to P1 if diagnostics expose secrets |
| RR-044 | Versioned routes are alias-only | Open |
| RR-045 | Public catalog authorization/business scraping policy | Open; depends on business decision |

### Closed

| ID | Название | Закрыто в |
|---|---|---|
| RR-001 | Stored XSS через CMS Home block | PR-01 / `0e80f25` |

## 11. Новый roadmap

### Phase 0 — Verify merged PRs and prevent regression

- Keep sanitizer regression tests for CMS Home blocks.
- Verify security headers in report-only mode on staging and collect CSP violations.
- Verify auth token is absent from `localStorage` after login/logout/reopen.
- Add release notes that old PR-01/02/03 are complete and must not be reimplemented.

### Phase 1 — Remaining launch blockers

- RR-005 + RR-006: readiness/dependency checks and missing DB fail-fast.
- RR-007: move schema initialization out of runtime startup.
- RR-008 + RR-025 docs slice: release/rollback/incident/BotFather procedure.
- RR-010 + RR-012: backup/restore and uploads durability stopgap.
- RR-011 + RR-026 seed: launch metrics/synthetic checks/requestId minimum.
- RR-004 + RR-014 login slice: initData contract, replay handling, login throttling.
- RR-009: atomic sync design and first migration if TG catalog is production-critical.

### Phase 2 — Security stabilization

- RR-003R: enforce CSP after Telegram client validation and report review.
- RR-002R: decide HttpOnly cookie/session binding or formally accept sessionStorage TTL residual risk.
- RR-013: restrict public diagnostics.
- RR-014 global slice: API/static/diagnostics rate limiting.
- RR-015: proxy query/host allowlists and SSRF guard.
- RR-016: admin audit logging and granular permissions.
- RR-038: dependency vulnerability controls.

### Phase 3 — Contracts and backend consistency

- RR-022: OpenAPI/JSON Schema/Zod contracts for frontend/Node/Python/WEB boundaries.
- RR-023: choose production owner for TG catalog backend and add shared contract tests.
- RR-017: content degraded/stale-cache contract.
- RR-024: stable external identity model design.

### Phase 4 — Data consistency and sync

- RR-009 implementation: staging/sync_runs/transactional publish/rollback.
- RR-034: ownership/prune policy.
- RR-035: sync repository layer and PostgreSQL integration tests.
- RR-033: indexes, EXPLAIN, pool sizing and load validation.

### Phase 5 — Frontend reliability and architecture

- RR-021: split bootstrap critical vs secondary requests.
- RR-020: split API client domains.
- RR-018 + RR-019: state/router refactor in separate compatibility PRs.
- RR-028: retry/recovery/degraded UI.
- RR-029 + RR-030 + RR-031: performance budget, chunk recovery, static cache headers.

### Phase 6 — Operations hardening and cleanup

- RR-036/RR-037: ingress contract and typed config validation.
- RR-039/RR-040: admin bot health and runtime version metadata.
- RR-041/RR-042/RR-044: route abstraction, bot decomposition, version route semantics.
- RR-032/RR-045: media host strategy and catalog scraping policy.

## 12. Новые First 10 PR

1. **PR-01: Strict `/live`/`/ready` and missing DB fail-fast**
   - Issues: RR-005, RR-006.
   - Touch: Node health/readiness/catalog config behavior, compose/platform docs/tests.
   - Do not touch: migration system, sync architecture.
   - Checks: DB present/missing smoke, production no-DB returns 503, platform health path docs.

2. **PR-02: Move runtime DDL to explicit migration job/runbook**
   - Issues: RR-007.
   - Touch: migration scripts/docs/deploy sequence, runtime schema check.
   - Do not touch: sync staging or identity redesign.
   - Checks: fresh DB migration, existing DB no-op, runtime starts without DDL rights.

3. **PR-03: Release, rollback, incident and BotFather runbooks**
   - Issues: RR-008, RR-025 docs slice.
   - Touch: docs/checklists only unless a tiny validation script is needed.
   - Do not touch: app code.
   - Checks: tabletop rollback checklist review.

4. **PR-04: Backup/restore drill and uploads durability stopgap**
   - Issues: RR-010, RR-012.
   - Touch: backup docs/scripts, volume/object-storage stopgap docs/config.
   - Do not touch: frontend image rendering.
   - Checks: restore on staging, upload survives redeploy, RTO/RPO recorded.

5. **PR-05: Launch-gate metrics, synthetic checks and requestId seed**
   - Issues: RR-011, RR-026 partial.
   - Touch: minimal metrics/synthetic scripts/docs, requestId propagation seed.
   - Do not touch: full logging refactor.
   - Checks: alert fire/resolve, catalog/content/auth synthetic checks.

6. **PR-06: Telegram auth boundary validation, replay handling and login throttling**
   - Issues: RR-004, RR-014 login slice.
   - Touch: login proxy/WEB auth contract/tests/rate limit config.
   - Do not touch: token storage migration already merged.
   - Checks: invalid initData, expired auth_date, replay, rate-limit behavior, normal Telegram login.

7. **PR-07: WEB → TG sync atomic publish design and first migration**
   - Issues: RR-009, RR-034 partial.
   - Touch: sync design docs, `sync_runs` migration/staging scaffolding/tests.
   - Do not touch: frontend router/external identity.
   - Checks: dry-run, migration up/down, no publish behavior change until enabled.

8. **PR-08: CSP enforcement readiness and Telegram client evidence**
   - Issues: RR-003R.
   - Touch: CSP mode rollout docs/tests/report collection, allowlist tuning.
   - Do not touch: large frontend chunk/bundle changes.
   - Checks: `curl -I`, iOS/Android/Desktop Telegram smoke, report-only violations reviewed, enforce canary plan.

9. **PR-09: Residual auth session hardening decision and WEB session contract**
   - Issues: RR-002R.
   - Touch: auth contract docs/tests and, if feasible, backend-supported HttpOnly/session binding plan.
   - Do not touch: already-merged localStorage removal unless fixing regression.
   - Checks: login/logout/reopen, expiry, XSS threat model acceptance or implementation evidence.

10. **PR-10: API contracts and TG backend production-owner decision**
    - Issues: RR-022, RR-023.
    - Touch: OpenAPI/JSON Schema/Zod contracts, shared fixtures, decision record.
    - Do not touch: full backend consolidation rewrite.
    - Checks: contract tests against Node/Python stubs and WEB fixtures.

## 13. Updated launch readiness checklist

### Security

- [x] RR-001 closed: CMS Home HTML is rendered as inert text.
- [~] RR-002 closed for default `localStorage`; residual JS-readable session risk is P1.
- [~] RR-003 baseline headers/report-only CSP present; enforcement/evidence remains P1.
- [ ] RR-004 closed: Telegram initData validation contract, replay handling and login rate limits verified.
- [ ] Public diagnostics restricted or owner-accepted.
- [ ] Dependency audit reviewed and critical/high CVEs resolved or accepted.

### Availability / Operations

- [ ] `/live` and `/ready` semantics documented and configured in platform.
- [ ] Missing DB URL or broken DB fails readiness in production catalog mode.
- [ ] Runtime app does not perform uncontrolled DDL during startup.
- [ ] Release, rollback, incident and BotFather URL procedures rehearsed.
- [ ] Backup/restore drill completed; RTO/RPO documented.
- [ ] Uploads durable storage or explicit no-uploads launch decision documented.

### Data / Sync

- [ ] Sync is atomic or launch plan avoids catalog-critical dependency on unsafe sync.
- [ ] Sync dry-run and post-sync smoke checks are defined.
- [ ] Ownership/prune policy documented.
- [ ] Catalog counts/checksums monitored.

### Observability / QA

- [ ] Metrics/alerts/synthetic checks cover auth, catalog, content, DB, uploads and admin bot.
- [ ] Request/user-safe correlation exists for incident triage.
- [ ] iOS Telegram, Android Telegram, Telegram Desktop/Web smoke completed.
- [ ] Login/reopen/back button/partner/offers/content/profile/subscription smoke passed.
- [ ] Chunk 404/reload behavior tested.
