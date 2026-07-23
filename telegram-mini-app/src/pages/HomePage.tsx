import { useMemo, useState } from "react";
import { isApiError, isTimeoutError } from "../api/client";
import { AppImage } from "../components/AppImage";
import type { City, ClientProfile, Partner, ReferralSummary, Subscription } from "../api/types";
import { formatDate } from "../utils/format";
import { getSubscriptionEnd, isSubscriptionActive, isTrialEligible } from "../utils/subscription";
import { useContent, useContentText } from "../content/ContentContext";
import type { HomeBlock } from "../content/clientContentApi";
import { getPartnerAddress, getPartnerCategories, getPartnerCity, getPartnerImage, getPartnerName } from "../utils/partnerDisplay";
import { toText } from "../utils/text";
import { getReferralLink, shareOrCopyReferralLink } from "../utils/referral";
import { sanitizeCmsHtml } from "../utils/sanitizeCmsHtml";
import { resolveHomeCtaAction } from "../utils/homeCta";

interface HomePageProps {
  profile: ClientProfile | null;
  subscription: Subscription | null;
  cities?: City[] | null;
  partners?: Partner[] | null;
  onOpenCatalog: () => void;
  onOpenSubscription: () => void;
  onActivateTrial: () => Promise<Subscription>;
  trialMessage?: string | null;
  referralSummary?: ReferralSummary | null;
}

function getCityName(city: unknown): string {
  return toText(city);
}

function hasVisibleHomeBlockContent(block: HomeBlock): boolean {
  return Boolean(
    block.title?.trim() ||
      block.subtitle?.trim() ||
      block.body?.trim() ||
      block.image_url?.trim() ||
      block.cta_text?.trim() ||
      (block.type === "giveaway" &&
        typeof block.metadata_json.prize === "string" &&
        block.metadata_json.prize.trim()),
  );
}

export function HomePage({
  profile,
  subscription,
  cities,
  partners,
  onOpenCatalog,
  onOpenSubscription,
  onActivateTrial,
  trialMessage,
  referralSummary,
}: HomePageProps) {
  const safeCities = Array.isArray(cities) ? cities : [];
  const safePartners = Array.isArray(partners) ? partners : [];
  const [isActivatingTrial, setIsActivatingTrial] = useState(false);
  const [localTrialMessage, setLocalTrialMessage] = useState<string | null>(null);
  const { homeBlocks } = useContent();

  const hasAccess = isSubscriptionActive(subscription);
  const trialAvailable = isTrialEligible(profile, subscription);
  const selectedCity = safeCities[0] ? getCityName(safeCities[0]) : "Новосибирск";
  const firstName = profile?.first_name || profile?.name || "участница";
  const visibleHomeBlocks = useMemo(
    () => homeBlocks.filter((block) => block.is_active !== false && hasVisibleHomeBlockContent(block)),
    [homeBlocks],
  );

  const catalogCta = useContentText("home.hero.catalog_cta", "Найти привилегии");
  const subscriptionLabel = useContentText("home.hero.subscription_cta", "Оформить доступ");
  const manageSubscriptionLabel = useContentText("home.hero.manage_subscription_cta", "Моя подписка");
  const trialCta = useContentText("home.trial.cta", "Подключить пробный период 15 дней");
  const heroEyebrow = useContentText("home.hero.eyebrow", "Bloom Club · Женский клуб НСК");
  const heroTitle = useContentText("home.hero.title", `Добро пожаловать, ${firstName}`);
  const heroSubtitle = useContentText(
    "home.hero.subtitle",
    "Закрытый клуб привилегий у партнёров города: красота, здоровье, стиль, отдых и забота о себе.",
  );
  const cityTitle = useContentText("home.city.title", "Город");
  const trialTitle = useContentText("home.trial.title", "Попробуйте клуб бесплатно");
  const trialDescription = useContentText("home.trial.description", "Откройте 15 дней доступа к привилегиям Bloom Club.");
  const inviteCount = referralSummary?.pending_referrals_count ?? referralSummary?.invited_count ?? referralSummary?.referrals_count ?? 0;
  const activatedCount = referralSummary?.activated_referrals_count ?? 0;
  const referralLink = getReferralLink(referralSummary, profile);
  const entriesCount = referralSummary?.earned_entries_count ?? referralSummary?.earned_giveaway_entries_count ?? 0;
  const partnersTitle = useContentText("home.partners.title", "Партнёры клуба");
  const partnersDescription = useContentText(
    "home.partners.description",
    "Открывайте каталог и выбирайте привилегии у партнёров Bloom Club.",
  );
  const visiblePartners = safePartners.slice(0, 6);

  async function handleActivateTrial() {
    setIsActivatingTrial(true);
    setLocalTrialMessage(null);

    try {
      const updated = await onActivateTrial();
      const end = getSubscriptionEnd(updated);
      setLocalTrialMessage(
        end
          ? `Тестовый период активирован. Доступ к клубу до ${formatDate(end)}.`
          : "Тестовый период активирован.",
      );
    } catch (caughtError) {
      if (isTimeoutError(caughtError)) {
        setLocalTrialMessage("Не удалось загрузить данные. Проверьте соединение и повторите попытку.");
      } else if (isApiError(caughtError) && [400, 403, 409, 422].includes(caughtError.status || 0)) {
        setLocalTrialMessage("Пробный период уже использован");
      } else {
        setLocalTrialMessage("Не удалось активировать тестовый период. Попробуйте позже.");
      }
    } finally {
      setIsActivatingTrial(false);
    }
  }

  function runCta(action?: string) {
    const normalized = String(action || "").trim().toLowerCase();

    if (!normalized || normalized === "catalog" || normalized === "partners") {
      onOpenCatalog();
      return;
    }

    if (normalized === "subscription" || normalized === "profile") {
      onOpenSubscription();
      return;
    }

    if (normalized === "trial") {
      void handleActivateTrial();
      return;
    }

    if (/^https?:\/\//i.test(action || "")) {
      window.open(action, "_blank", "noopener,noreferrer");
    }
  }

  function renderCta(block: HomeBlock) {
    return block.cta_text ? (
      <button className="button button--primary" type="button" onClick={() => runCta(resolveHomeCtaAction(block))}>
        {block.cta_text}
      </button>
    ) : null;
  }

  function renderHomeBlock(block: HomeBlock) {
    const key = String(block.id);

    if (block.type === "hero") {
      return (
        <div className="hero-card" key={key}>
          {block.subtitle ? <p className="eyebrow">{block.subtitle}</p> : null}
          <h1>{block.title}</h1>
          {block.body ? <p>{block.body}</p> : null}
          <AppImage src={block.image_url} className="home-builder-image" alt={block.title} shellClassName="home-builder-image-shell" placeholderClassName="home-builder-image image-placeholder image-placeholder--wide" loading="eager" />
          <div className="hero-card__actions">{renderCta(block)}</div>
        </div>
      );
    }

    if (block.type === "partners_carousel") {
      return (
        <div className="info-panel" key={key}>
          <strong>{block.title}</strong>
          {block.body ? <p>{block.body}</p> : null}
          <div className="home-partners-carousel" aria-label="Партнёры клуба">
            {safePartners.slice(0, 8).map((partner) => (
              <button
                className="home-partner-card"
                type="button"
                onClick={onOpenCatalog}
                key={String(partner.id ?? getPartnerName(partner))}
              >
                <span>{getPartnerName(partner)}</span>
                <small>{toText(partner.category) || "Партнёр Bloom Club"}</small>
              </button>
            ))}
          </div>
          {renderCta(block)}
        </div>
      );
    }

    if (block.type === "html_text") {
      return (
        <div className="info-panel home-html-text" key={key}>
          {block.title ? <strong>{block.title}</strong> : null}
          {block.body ? <p>{sanitizeCmsHtml(block.body)}</p> : null}
          {renderCta(block)}
        </div>
      );
    }

    if (block.type === "image") {
      return (
        <figure className="info-panel home-image-block" key={key}>
          <AppImage src={block.image_url} className="home-builder-image" alt={block.title || block.subtitle} shellClassName="home-builder-image-shell" placeholderClassName="home-builder-image image-placeholder image-placeholder--wide" />
          <figcaption>
            {block.title ? <strong>{block.title}</strong> : null}
            {block.body ? <p>{block.body}</p> : null}
          </figcaption>
          {renderCta(block)}
        </figure>
      );
    }

    return (
      <div
        className={
          block.type === "custom_cta" || block.type === "banner" || block.type === "giveaway"
            ? "info-panel info-panel--soft"
            : "info-panel"
        }
        key={key}
      >
        <AppImage src={block.image_url} className="home-builder-image" alt={block.title} shellClassName="home-builder-image-shell" placeholderClassName="home-builder-image image-placeholder image-placeholder--wide" />
        {block.subtitle ? <p className="eyebrow">{block.subtitle}</p> : null}
        {block.title ? <strong>{block.title}</strong> : null}
        {block.body ? <p>{block.body}</p> : null}
        {block.type === "giveaway" && typeof block.metadata_json.prize === "string" ? (
          <p className="success-text">Приз: {block.metadata_json.prize}</p>
        ) : null}
        {renderCta(block)}
      </div>
    );
  }



  function renderReferralBanner() {
    return (
      <div className="info-panel info-panel--soft referral-banner">
        <p className="eyebrow">Реферальная программа</p>
        <strong>Приглашай подруг и получай бонусы</strong>
        <p>За каждого приглашённого — 5 номеров в розыгрыше.</p>
        <div className="referral-banner__stats" aria-label="Статистика приглашений">
          <span>{inviteCount} приглашено</span>
          <span>{activatedCount} активировали trial</span>
          <span>{entriesCount} номеров</span>
        </div>
        <button className="button button--primary" type="button" disabled={!referralLink} onClick={() => shareOrCopyReferralLink(referralLink)}>
          Пригласить
        </button>
      </div>
    );
  }

  function renderTrialCta() {
    if (!trialAvailable) {
      return null;
    }

    return (
      <div className="info-panel info-panel--soft trial-cta-panel">
        <strong>{trialTitle}</strong>
        <p>{trialDescription}</p>
        <button className="button button--primary" type="button" onClick={() => void handleActivateTrial()} disabled={isActivatingTrial}>
          {isActivatingTrial ? "Активируем…" : trialCta}
        </button>
      </div>
    );
  }

  function renderLegacyHome() {
    return (
      <>
        <div className="hero-card home-hero">
          <p className="eyebrow">{heroEyebrow}</p>
          <h1>{heroTitle}</h1>
          <p>{heroSubtitle}</p>
          <div className="home-hero__benefits" aria-label="Преимущества Bloom Club">
            <span>Красота</span>
            <span>Здоровье</span>
            <span>Стиль</span>
          </div>
          <div className="hero-card__actions">
            <button className="button button--primary" type="button" onClick={onOpenCatalog}>
              {catalogCta}
            </button>
            <button className="button button--ghost" type="button" onClick={onOpenSubscription}>
              {hasAccess ? manageSubscriptionLabel : subscriptionLabel}
            </button>
          </div>
        </div>

        {safeCities.length ? (
          <div className="info-panel">
            <strong>{cityTitle}</strong>
            <p>
              {selectedCity
                ? `Сейчас показываем партнёров города: ${selectedCity}.`
                : "Выберите город в профиле, чтобы видеть актуальные предложения."}
            </p>
          </div>
        ) : null}

        <section className="home-partners-section" aria-labelledby="home-partners-title">
          <div className="home-section-heading">
            <div>
              <p className="eyebrow">Каталог привилегий</p>
              <h2 id="home-partners-title">{partnersTitle}</h2>
              <p>{partnersDescription}</p>
            </div>
            <button className="link-button" type="button" onClick={onOpenCatalog}>
              Все
            </button>
          </div>

          {visiblePartners.length ? (
            <div className="home-partners-grid">
              {visiblePartners.map((partner) => {
                const image = getPartnerImage(partner);
                const categories = getPartnerCategories(partner).join(" • ") || "Партнёр Bloom Club";
                const place = [getPartnerCity(partner), getPartnerAddress(partner)].filter(Boolean).join(" · ");

                return (
                  <button
                    className="home-partner-tile"
                    type="button"
                    onClick={onOpenCatalog}
                    key={String(partner.id ?? getPartnerName(partner))}
                    aria-label={`Открыть партнёра ${getPartnerName(partner)}`}
                  >
                    <AppImage src={image} alt="" placeholderClassName="home-partner-tile__placeholder image-placeholder image-placeholder--brand" />
                    <span className="home-partner-tile__body">
                      <strong>{getPartnerName(partner)}</strong>
                      <small>{categories}</small>
                      {place ? <em>{place}</em> : null}
                      <span className="home-partner-tile__cta">Смотреть</span>
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="home-empty-state">
              <span aria-hidden="true">♡</span>
              <strong>Скоро добавим партнёров</strong>
              <p>Команда Bloom Club готовит новые места для красоты, отдыха и заботы о себе. Загляните в каталог чуть позже.</p>
              <button className="button button--primary" type="button" onClick={onOpenCatalog}>
                Открыть каталог
              </button>
            </div>
          )}
        </section>
      </>
    );
  }

  return (
    <section className="page">
      {visibleHomeBlocks.length ? (
        <>
          {visibleHomeBlocks.map(renderHomeBlock)}
          {renderTrialCta()}
          {renderReferralBanner()}
        </>
      ) : (
        <>
          {renderTrialCta()}
          {renderReferralBanner()}
          {renderLegacyHome()}
        </>
      )}
      {trialMessage || localTrialMessage ? <p className="success-text">{trialMessage || localTrialMessage}</p> : null}
    </section>
  );
}
