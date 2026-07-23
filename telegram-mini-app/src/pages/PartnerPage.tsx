import { useEffect, useRef, useState } from "react";
import { isApiError, isTimeoutError } from "../api/client";
import type { ApiId, ClientProfile, Offer, OfferPhoto, Partner, PartnerPhoto, Subscription, Verification } from "../api/types";
import type { PartnerOffersDiagnostic } from "../App";
import { AppImage } from "../components/AppImage";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { useContentText } from "../content/ContentContext";
import { buildYandexMapsUrl, formatDate, formatMoney } from "../utils/format";
import { getSubscriptionEnd, isSubscriptionActive, isTrialEligible } from "../utils/subscription";
import { toText } from "../utils/text";
import {
  getOfferBenefit,
  getOfferConditions,
  getOfferDescription,
  getOfferPrices,
  getOfferTitle,
  getPartnerAddress,
  getPartnerCategories,
  getPartnerCity,
  getPartnerDescription,
  getPartnerImages,
  getPartnerName,
  getPartnerPhone,
  normalizeTelHref,
  getVerificationCode,
  isNumericApiId,
  resolveNumericPartnerId,
} from "../utils/partnerDisplay";

function photoUrl(photo: unknown): string {
  if (!photo) {
    return "";
  }

  if (typeof photo === "string" || typeof photo === "number") {
    return String(photo);
  }

  if (typeof photo === "object") {
    const record = photo as Record<string, unknown>;
    const value = record.image_url ?? record.photo_url ?? record.url ?? record.src;
    return value === undefined || value === null ? "" : String(value);
  }

  return "";
}

function photoAlt(photo: unknown): string {
  if (!photo || typeof photo !== "object") {
    return "";
  }

  const record = photo as Record<string, unknown>;
  const value = record.alt_text ?? record.alt;
  return value === undefined || value === null ? "" : String(value);
}

function photoSort(photo: unknown, index: number): number {
  if (!photo || typeof photo !== "object") {
    return (index + 1) * 100;
  }

  const raw = (photo as Record<string, unknown>).sort_order;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : (index + 1) * 100;
}

function makePhotoRecord<T extends PartnerPhoto | OfferPhoto>(photo: unknown, index: number): T {
  if (photo && typeof photo === "object") {
    return {
      ...(photo as Record<string, unknown>),
      image_url: photoUrl(photo),
      alt_text: photoAlt(photo),
      sort_order: photoSort(photo, index),
      is_active: (photo as Record<string, unknown>).is_active === false ? false : true,
    } as T;
  }

  return {
    image_url: photoUrl(photo),
    alt_text: "",
    sort_order: photoSort(photo, index),
    is_active: true,
  } as T;
}

function getPartnerPhotoRecords(partner: Partner): PartnerPhoto[] {
  const fromPhotos = Array.isArray(partner.photos) ? partner.photos.map(makePhotoRecord<PartnerPhoto>) : [];
  const fallback = [
    ["cover_url", partner.cover_url],
    ["photo_url", partner.photo_url],
    ["logo_url", partner.logo_url],
    ["image_url", partner.image_url],
    ["avatar_url", partner.avatar_url],
  ]
    .map(([source_field, value], index) => ({ ...makePhotoRecord<PartnerPhoto>(value, index), source_field }))
    .filter((photo) => Boolean(photo.image_url));
  return [...fromPhotos, ...fallback]
    .filter((photo) => photo.is_active !== false && Boolean(photo.image_url))
    .sort((first, second) => Number(first.sort_order ?? 100) - Number(second.sort_order ?? 100));
}

function getOfferPhotoRecords(offer: Offer): OfferPhoto[] {
  const imagePhoto = photoUrl(offer.image_url)
    ? ([{ image_url: photoUrl(offer.image_url), alt_text: getOfferTitle(offer), sort_order: 0, is_active: true }] as OfferPhoto[])
    : [];
  const galleryPhotos = Array.isArray(offer.photos) ? offer.photos.map(makePhotoRecord<OfferPhoto>) : [];
  return [...imagePhoto, ...galleryPhotos]
    .filter((photo) => photo.is_active !== false && Boolean(photo.image_url))
    .sort((first, second) => Number(first.sort_order ?? 100) - Number(second.sort_order ?? 100));
}


function SmoothImage({
  src,
  alt,
  className,
  loading = "lazy",
  onError,
  fit = "cover",
}: {
  src: string;
  alt: string;
  className?: string;
  loading?: "eager" | "lazy";
  onError?: () => void;
  fit?: "cover" | "contain";
}) {
  return (
    <AppImage
      src={src}
      alt={alt}
      className={className}
      loading={loading}
      fit={fit}
      onError={onError}
      placeholderClassName="image-placeholder image-placeholder--brand"
    />
  );
}


function readOfferField(offer: Offer, field: string): unknown {
  return (offer as Record<string, unknown>)[field];
}

function isOfferAvailable(offer: Offer): boolean {
  const record = offer as Record<string, unknown>;
  const disabledFlags = [record.is_active, record.active, record.available, record.is_available];
  return !disabledFlags.some((value) => value === false || value === "false" || value === 0 || value === "0");
}

function getOfferAccentBadge(offer: Offer): string | undefined {
  const prices = getOfferPrices(offer);
  const discountPercent = readOfferField(offer, "discount_percent");
  const discount = toText(offer.discount);
  const gift = toText(offer.gift);
  const value = toText(offer.value);
  const benefit = toText(offer.benefit ?? offer.benefit_text);

  if (discountPercent !== undefined && discountPercent !== null && String(discountPercent).trim()) {
    const percentText = String(discountPercent).trim();
    return percentText.includes("%") ? percentText : `-${percentText}%`;
  }

  if (prices.hasValidSaving) {
    return `Выгода ${formatMoney(prices.saving)}`;
  }

  const textCandidates = [discount, gift, value, benefit].filter(Boolean) as string[];
  return textCandidates.find((text) => /\d|%|скид|бонус|подар|выгод/i.test(text));
}

interface PartnerPageProps {
  partner: Partner | null;
  offers?: Offer[] | null;
  offersStatus: "idle" | "loading" | "success" | "empty" | "error" | "timeout";
  offersError: string;
  offersDiagnostic?: PartnerOffersDiagnostic | null;
  profile: ClientProfile | null;
  subscription: Subscription | null;
  onBack: () => void;
  onVerifyOffer: (partnerId: ApiId, offerId: ApiId) => Promise<Verification>;
  onOpenSubscription: () => void;
  onActivateTrial: () => Promise<Subscription>;
  onRetryOffers: () => void;
}

export function PartnerPage({
  partner,
  offers,
  offersStatus,
  offersError,
  offersDiagnostic,
  profile,
  subscription,
  onBack,
  onVerifyOffer,
  onOpenSubscription,
  onActivateTrial,
  onRetryOffers,
}: PartnerPageProps) {
  const safeOffers = Array.isArray(offers) ? offers : [];
  const [selectedVerification, setSelectedVerification] = useState<Verification | null>(null);
  const [selectedOffer, setSelectedOffer] = useState<Offer | null>(null);
  const [loadingOfferId, setLoadingOfferId] = useState<ApiId | null>(null);
  const [message, setMessage] = useState("");
  const [isActivatingTrial, setIsActivatingTrial] = useState(false);
  const [galleryIndex, setGalleryIndex] = useState<number | null>(null);
  const [copyMessage, setCopyMessage] = useState("");
  const [failedImageUrls, setFailedImageUrls] = useState<string[]>([]);
  const copyMessageTimeoutRef = useRef<number | null>(null);

  const backLabel = useContentText("partner.back_to_catalog", "← В каталог");
  const partnerInfoTitle = useContentText("partner.info.title", "О партнёре");
  const partnerAccessTitle = useContentText("partner.access.title", "Оформите доступ");
  const partnerAccessDescription = useContentText(
    "partner.access.description",
    "Активный доступ нужен, чтобы получить код привилегии у партнёра.",
  );
  const trialCta = useContentText("partner.trial.cta", "Подключить пробный период 15 дней");
  const buyAccessCta = useContentText("partner.access.cta", "Оформить доступ");
  const servicesTitle = useContentText("partner.offers.title", "Услуги");
  const offersLoadingTitle = useContentText("partner.offers.loading", "Загружаем предложения партнёра…");
  const offersEmptyTitle = useContentText("partner.offers.empty.title", "Пока нет активных предложений");
  const offersEmptyDescription = useContentText(
    "partner.offers.empty.description",
    "Когда партнёр добавит услуги или специальные условия, они появятся здесь.",
  );
  const retryLabel = useContentText("common.retry", "Повторить");
  const backToCatalogLabel = useContentText("partner.offers.back_to_catalog", "Назад в каталог");
  const verifyCta = useContentText("partner.offer.verify_cta", "Получить привилегию");

  useEffect(
    () => () => {
      if (copyMessageTimeoutRef.current !== null) {
        window.clearTimeout(copyMessageTimeoutRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    setFailedImageUrls([]);
  }, [partner?.id]);

  useEffect(() => {
    if (
      selectedOffer &&
      !safeOffers.some((offer) => offer.id === selectedOffer.id)
    ) {
      setSelectedOffer(null);
      setSelectedVerification(null);
    }
  }, [safeOffers, selectedOffer]);

  if (!partner) {
    return <EmptyState title="Партнёр не выбран" description="Вернитесь в каталог и выберите карточку партнёра." />;
  }

  const currentPartner = partner;
  const images = getPartnerImages(currentPartner).filter((image) => !failedImageUrls.includes(image));
  const mapsUrl = buildYandexMapsUrl({
    latitude: currentPartner.latitude ?? currentPartner.lat,
    longitude: currentPartner.longitude ?? currentPartner.lon,
    address: getPartnerAddress(currentPartner),
  });
  const phone = getPartnerPhone(currentPartner);
  const telHref = normalizeTelHref(phone);
  const hasAccess = isSubscriptionActive(subscription);
  const trialAvailable = isTrialEligible(profile, subscription);
  const partnerIdForActions = resolveNumericPartnerId(currentPartner)?.numericPartnerId;

  function getVerificationErrorMessage(error: unknown): string {
    if (isTimeoutError(error)) {
      return "Не удалось загрузить данные. Проверьте соединение и повторите попытку.";
    }

    if (isApiError(error)) {
      const backendDetail = toText(error.detail);

      if (error.status === 404) {
        return "Функция скоро станет доступна";
      }

      if ((error.status === 501 || error.status === 403) && /access_check_not_configured|not configured|telegram/i.test(backendDetail)) {
        return "Получение кода для Telegram-каталога скоро будет доступно.";
      }

      return backendDetail || error.message || "Не удалось получить код привилегии. Попробуйте ещё раз.";
    }

    return "Не удалось получить код привилегии. Попробуйте ещё раз.";
  }

  async function handleVerify(offer: Offer) {
    if (partnerIdForActions === undefined) {
      setMessage("Не удалось получить код: id партнёра отсутствует или не является числом.");
      return;
    }

    if (!isNumericApiId(offer.id)) {
      setMessage("Не удалось получить код: id предложения отсутствует или не является числом.");
      return;
    }

    setMessage("");
    setLoadingOfferId(offer.id);

    try {
      const verification = await onVerifyOffer(partnerIdForActions, offer.id);
      setSelectedVerification(verification);
      setSelectedOffer(offer);
    } catch (caughtError) {
      setMessage(getVerificationErrorMessage(caughtError));
    } finally {
      setLoadingOfferId(null);
    }
  }

  async function handleActivateTrial() {
    setIsActivatingTrial(true);
    setMessage("");

    try {
      const updated = await onActivateTrial();
      const end = getSubscriptionEnd(updated);
      setMessage(end ? `Тестовый период активирован. Доступ к клубу до ${formatDate(end)}.` : "Тестовый период активирован.");
    } catch (caughtError) {
      if (isTimeoutError(caughtError)) {
        setMessage("Не удалось загрузить данные. Проверьте соединение и повторите попытку.");
      } else if (isApiError(caughtError) && [400, 403, 409, 422].includes(caughtError.status || 0)) {
        setMessage("Пробный период уже использован");
      } else {
        setMessage("Не удалось активировать тестовый период. Откройте раздел подписки.");
      }
    } finally {
      setIsActivatingTrial(false);
    }
  }

  function showCopyMessage(nextMessage: string) {
    setCopyMessage(nextMessage);

    if (copyMessageTimeoutRef.current !== null) {
      window.clearTimeout(copyMessageTimeoutRef.current);
    }

    copyMessageTimeoutRef.current = window.setTimeout(() => {
      setCopyMessage("");
      copyMessageTimeoutRef.current = null;
    }, 2500);
  }

  function copyCodeWithFallback(codeToCopy: string): boolean {
    const textarea = document.createElement("textarea");
    textarea.value = codeToCopy;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();

    let copied = false;
    try {
      copied = document.execCommand("copy");
    } finally {
      document.body.removeChild(textarea);
    }

    return copied;
  }

  async function copyCode(codeToCopy: string) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(codeToCopy);
        showCopyMessage("Код скопирован");
        return;
      }

      showCopyMessage(copyCodeWithFallback(codeToCopy) ? "Код скопирован" : "Скопируйте код вручную");
    } catch {
      showCopyMessage(copyCodeWithFallback(codeToCopy) ? "Код скопирован" : "Скопируйте код вручную");
    }
  }

  const code = getVerificationCode(selectedVerification);
  const hasGallery = images.length > 0;
  const selectedGalleryImage = galleryIndex !== null ? images[galleryIndex] : null;

  function handleImageError(image: string) {
    setFailedImageUrls((current) => (current.includes(image) ? current : [...current, image]));
  }

  function openGallery(index: number) {
    if (hasGallery) {
      setGalleryIndex(index);
    }
  }

  function shiftGallery(direction: -1 | 1) {
    setGalleryIndex((current) => {
      if (current === null || !images.length) {
        return current;
      }

      return (current + direction + images.length) % images.length;
    });
  }

  return (
    <section className="page partner-page">
      <button className="back-button" type="button" onClick={onBack}>
        {backLabel}
      </button>
      <article className="partner-detail">
        <div className="partner-detail__hero">
          {hasGallery ? (
            <div className="partner-gallery">
              <button className="partner-gallery__main" type="button" onClick={() => openGallery(0)} aria-label="Открыть фото партнёра">
                <SmoothImage className="partner-detail__image" src={images[0]} alt={getPartnerName(currentPartner)} loading="eager" onError={() => handleImageError(images[0])} />
              </button>
              {images.length > 1 ? (
                <div className="partner-gallery__thumbs">
                  {images.slice(1, 5).map((image, index) => (
                    <button className="partner-gallery__thumb" type="button" onClick={() => openGallery(index + 1)} key={image} aria-label={`Открыть фото ${index + 2}`}>
                      <SmoothImage src={image} alt="" onError={() => handleImageError(image)} />
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="partner-detail__placeholder" aria-label="Фото партнёра скоро появится">
              <span>Bloom</span>
              <small>Фото партнёра скоро появится</small>
            </div>
          )}
          <div className="partner-detail__info-card">
            <p className="eyebrow">{[getPartnerCity(currentPartner), getPartnerCategories(currentPartner).join(" • ")].filter(Boolean).join(" • ") || "Bloom Club partner"}</p>
            <h1>{getPartnerName(currentPartner)}</h1>
            <p>{getPartnerDescription(currentPartner)}</p>
            <div className="partner-detail__actions">
              {telHref ? (
                <a className="button button--primary" href={telHref}>
                  Позвонить
                </a>
              ) : null}
              {mapsUrl ? (
                <a className="button button--ghost" href={mapsUrl} target="_blank" rel="noreferrer">
                  На карте
                </a>
              ) : null}
            </div>
          </div>
        </div>

        <div className="info-panel partner-contact-card">
          <strong>{partnerInfoTitle}</strong>
          <div className="partner-contact-card__rows">
            {getPartnerCity(currentPartner) ? <span>📍 {getPartnerCity(currentPartner)}</span> : null}
            {getPartnerAddress(currentPartner) ? <span>🗺️ {getPartnerAddress(currentPartner)}</span> : null}
            {phone ? <span>☎️ {phone}</span> : null}
          </div>
        </div>

        {!hasAccess ? (
          <div className="info-panel info-panel--soft">
            <strong>{partnerAccessTitle}</strong>
            <p>{partnerAccessDescription}</p>
            {trialAvailable ? (
              <button className="button button--primary" type="button" onClick={() => void handleActivateTrial()} disabled={isActivatingTrial}>
                {isActivatingTrial ? "Активируем…" : trialCta}
              </button>
            ) : (
              <button className="button button--primary" type="button" onClick={onOpenSubscription}>
                {buyAccessCta}
              </button>
            )}
          </div>
        ) : null}

        {message ? <p className="error-text">{message}</p> : null}

        <div className="section-heading">
          <h2>{servicesTitle}</h2>
        </div>
        {offersStatus === "loading" ? (
          <LoadingState title={offersLoadingTitle} compact />
        ) : offersStatus === "error" || offersStatus === "timeout" ? (
          <div className="offer-error-panel">
            <EmptyState
              title={offersError || "Не удалось загрузить предложения партнёра"}
              description="Проверьте соединение и повторите попытку."
            />
            <div className="offer-error-panel__actions">
              <button className="button button--secondary" type="button" onClick={onBack}>
                {backToCatalogLabel}
              </button>
              <button className="button button--primary" type="button" onClick={onRetryOffers}>
                {retryLabel}
              </button>
            </div>
          </div>
        ) : safeOffers.length ? (
          <div className="offer-list">
            {safeOffers.map((offer, index) => {
              const prices = getOfferPrices(offer);
              const offerKey = offer.id ?? index;
              const isVerifying = loadingOfferId === offer.id;
              const offerPhotos = getOfferPhotoRecords(offer);
              const offerMainPhoto = offerPhotos[0];
              const offerMainImage = photoUrl(offerMainPhoto);
              const benefit = getOfferBenefit(offer);
              const conditions = getOfferConditions(offer);
              const accentBadge = getOfferAccentBadge(offer);
              const isAvailable = isOfferAvailable(offer);

              return (
                <article className={`offer-card${isAvailable ? "" : " offer-card--disabled"}`} key={String(offerKey)} aria-disabled={!isAvailable}>
                  {offerMainImage ? (
                    <SmoothImage
                      className="offer-card__image"
                      src={offerMainImage}
                      alt={photoAlt(offerMainPhoto)}
                    />
                  ) : null}
                  <div className="offer-card__content">
                    <div className="offer-card__header">
                      <strong>{getOfferTitle(offer)}</strong>
                      {accentBadge ? <span className="offer-card__badge">{accentBadge}</span> : null}
                    </div>
                    <p>{getOfferDescription(offer)}</p>
                    {benefit ? <p className="offer-card__meta">{benefit}</p> : null}
                    {conditions ? <p className="offer-card__meta">{conditions}</p> : null}
                  </div>
                  <div className="price-grid offer-card__prices">
                    {prices.hasValidMemberPrice ? (
                      <span className="offer-card__price offer-card__price--member">
                        <small>Цена для участницы</small>
                        <strong>{formatMoney(prices.memberPrice)}</strong>
                      </span>
                    ) : null}
                    {prices.basePrice !== undefined ? (
                      <span className="offer-card__price offer-card__price--base">
                        <small>Обычная цена</small>
                        <s>{formatMoney(prices.basePrice)}</s>
                      </span>
                    ) : null}
                    {prices.hasValidSaving ? (
                      <span className="offer-card__price offer-card__price--saving">
                        <small>Экономия</small>
                        <strong>{formatMoney(prices.saving)}</strong>
                      </span>
                    ) : null}
                  </div>
                  {!isAvailable ? <p className="offer-card__disabled-note">Предложение временно недоступно</p> : null}
                  <button className="button button--primary offer-card__cta" type="button" onClick={() => void handleVerify(offer)} disabled={isVerifying || !isAvailable}>
                    {isVerifying ? "Получаем код…" : isAvailable ? verifyCta : "Скоро доступно"}
                  </button>
                </article>
              );
            })}
          </div>
        ) : offersStatus === "empty" || offersStatus === "idle" ? (
          <EmptyState title={offersEmptyTitle} description={offersEmptyDescription} />
        ) : null}
      </article>

      {selectedVerification ? (
        <div className="modal" role="dialog" aria-modal="true">
          <div className="modal__sheet">
            <button className="modal__close" type="button" onClick={() => setSelectedVerification(null)} aria-label="Закрыть">
              ×
            </button>
            <p className="eyebrow">Код привилегии</p>
            <h2>{selectedOffer ? getOfferTitle(selectedOffer) : getPartnerName(currentPartner)}</h2>
            {code ? <p className="verification-code">{code}</p> : <p>Покажите этот экран партнёру.</p>}
            {code ? (
              <button className="button button--primary" type="button" onClick={() => void copyCode(code)}>
                Скопировать код
              </button>
            ) : null}
            {copyMessage ? <p className="success-text">{copyMessage}</p> : null}
          </div>
        </div>
      ) : null}

      {selectedGalleryImage ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Галерея фото партнёра">
          <button className="lightbox__close" type="button" onClick={() => setGalleryIndex(null)} aria-label="Закрыть">
            ×
          </button>
          {images.length > 1 ? (
            <button className="lightbox__nav lightbox__nav--prev" type="button" onClick={() => shiftGallery(-1)} aria-label="Предыдущее фото">
              ‹
            </button>
          ) : null}
          <SmoothImage className="lightbox__image" src={selectedGalleryImage} alt={getPartnerName(currentPartner)} loading="eager" fit="contain" />
          {images.length > 1 ? (
            <button className="lightbox__nav lightbox__nav--next" type="button" onClick={() => shiftGallery(1)} aria-label="Следующее фото">
              ›
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
