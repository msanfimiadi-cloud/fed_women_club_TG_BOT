import { useMemo, useState } from "react";
import type React from "react";
import type { CatalogErrorDiagnostic } from "../api/client";
import type { Partner } from "../api/types";
import { AppImage } from "../components/AppImage";
import { EmptyState } from "../components/EmptyState";
import { useContentText } from "../content/ContentContext";
import {
  buildCatalogCategories,
  filterPartnersByCategory,
} from "../utils/catalogCategories";
import {
  getPartnerAddress,
  getPartnerCategories,
  getPartnerCity,
  getPartnerDescription,
  getPartnerImage,
  getPartnerName,
  getPartnerPrivilege,
  hasEmbeddedOffers,
  pickReadableValue,
} from "../utils/partnerDisplay";

interface CatalogPageProps {
  partners?: Partner[] | null;
  isLoading?: boolean;
  error?: string;
  errorTitle?: string;
  errorDetails?: Pick<
    CatalogErrorDiagnostic,
    | "source"
    | "requestUrl"
    | "requestUrlPath"
    | "requestOrigin"
    | "httpStatus"
    | "requestId"
    | "elapsedMs"
    | "attempt"
  >;
  errorCreatedAt?: string;
  loadStartedAt?: string;
  loadRequestId?: number;
  onRetry?: () => void;
  onCancel?: () => void;
  isRecovery?: boolean;
  onOpenPartner: (partner: Partner) => void;
}

const LIFESTYLE_CATEGORIES = [
  "Все",
  "Красота",
  "Здоровье",
  "Спорт",
  "Кафе",
  "Рестораны",
  "Образование",
  "Фитнес",
  "Стиль",
  "Отдых",
];

function PartnerCardImage({ src, name }: { src?: string; name: string }) {
  return (
    <AppImage
      src={src}
      alt=""
      placeholder={name.slice(0, 1) || "Bloom"}
      placeholderClassName="partner-card__placeholder image-placeholder image-placeholder--brand"
    />
  );
}


function getOfferAvailabilityText(partner: Partner): string | null {
  const availability = hasEmbeddedOffers(partner);

  if (availability === false) {
    return "Предложения скоро появятся";
  }

  return getPartnerPrivilege(partner);
}


function getPartnerDistance(partner: Partner): string | undefined {
  return pickReadableValue(
    (partner as Partner & Record<string, unknown>).distance,
    (partner as Partner & Record<string, unknown>).distance_text,
    (partner as Partner & Record<string, unknown>).distance_km,
  );
}

function getPartnerSearchText(partner: Partner): string {
  return [
    getPartnerName(partner),
    getPartnerDescription(partner),
    getPartnerAddress(partner),
    getPartnerCity(partner),
    getPartnerCategories(partner).join(" "),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function CatalogSkeleton({ onCancel }: { onCancel?: () => void }) {
  return (
    <section className="page catalog-page" aria-busy="true" aria-label="Загружаем каталог партнёров">
      <div className="page-header catalog-hero catalog-hero--skeleton">
        <span className="skeleton-line skeleton-line--eyebrow" />
        <span className="skeleton-line skeleton-line--title" />
        <span className="skeleton-line skeleton-line--text" />
      </div>
      <div className="catalog-loading-actions">
        <p>Каталог загружается. Пожалуйста, не закрывайте Mini App до завершения.</p>
        {onCancel ? (
          <button className="button button--secondary" type="button" onClick={onCancel}>
            Отменить и вернуться
          </button>
        ) : null}
      </div>
      <div className="catalog-search catalog-search--skeleton">
        <span className="skeleton-line skeleton-line--text" />
      </div>
      <div className="chips catalog-chips" aria-hidden="true">
        {Array.from({ length: 6 }).map((_, index) => (
          <span className="chip catalog-chip catalog-chip--skeleton" key={index} />
        ))}
      </div>
      <div className="cards-grid catalog-grid">
        {Array.from({ length: 4 }).map((_, index) => (
          <article className="partner-card partner-card--skeleton" key={index}>
            <span className="partner-card__media skeleton-block" />
            <span className="partner-card__body">
              <span className="skeleton-line skeleton-line--title" />
              <span className="skeleton-line skeleton-line--text" />
              <span className="skeleton-line skeleton-line--short" />
            </span>
          </article>
        ))}
      </div>
    </section>
  );
}

export function CatalogPage({
  partners,
  isLoading = false,
  error = "",
  errorTitle = "Не удалось загрузить каталог",
  errorDetails,
  errorCreatedAt,
  loadStartedAt,
  loadRequestId,
  onRetry,
  onCancel,
  isRecovery = false,
  onOpenPartner,
}: CatalogPageProps) {
  const safePartners = Array.isArray(partners) ? partners : [];
  const dataCategories = useMemo(
    () => buildCatalogCategories(safePartners),
    [safePartners],
  );
  const categories = useMemo(
    () => Array.from(new Set([...LIFESTYLE_CATEGORIES, ...dataCategories])),
    [dataCategories],
  );
  const [selectedCategory, setSelectedCategory] = useState("Все");
  const [searchQuery, setSearchQuery] = useState("");
  const visiblePartners = useMemo(() => {
    const categoryFiltered = filterPartnersByCategory(safePartners, selectedCategory);
    const normalizedQuery = searchQuery.trim().toLowerCase();

    if (!normalizedQuery) {
      return categoryFiltered;
    }

    return categoryFiltered.filter((partner) => getPartnerSearchText(partner).includes(normalizedQuery));
  }, [safePartners, selectedCategory, searchQuery]);

  const retryLabel = useContentText("common.retry", "Повторить");
  const emptyTitle = useContentText(
    "partners.empty.title",
    "Мы скоро добавим новых партнёров",
  );
  const emptyDescription = useContentText(
    "partners.empty.description",
    "А пока сохраняйте настроение Bloom Club — каталог уже наполняется красивыми местами.",
  );
  const eyebrow = useContentText("partners.eyebrow", "Каталог");
  const title = useContentText("partners.title", "Партнёры клуба");
  const description = useContentText(
    "partners.description",
    "Ищите любимые места, фильтруйте по категориям и открывайте клубные предложения рядом с вами.",
  );

  if (isLoading) {
    return <CatalogSkeleton onCancel={onCancel} />;
  }

  if (error) {
    const debugDetails = {
      ...errorDetails,
      catalogErrorCreatedAt: errorCreatedAt,
      catalogLoadStartedAt: loadStartedAt,
      catalogLoadRequestId: loadRequestId,
    };

    return (
      <EmptyState
        title={errorTitle}
        description={error}
        eyebrow={isRecovery ? "Восстановление" : "Ошибка загрузки"}
        icon="!"
        details={debugDetails}
        actionLabel={retryLabel}
        onAction={onRetry}
      />
    );
  }

  return (
    <section className="page catalog-page">
      <div className="page-header catalog-hero">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>

      <label className="catalog-search" aria-label="Поиск партнёров">
        <span className="catalog-search__icon" aria-hidden="true">⌕</span>
        <input
          type="search"
          value={searchQuery}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(event.target.value)}
          placeholder="Найти салон, кафе или услугу"
        />
        {searchQuery ? (
          <button className="catalog-search__clear" type="button" onClick={() => setSearchQuery("")} aria-label="Очистить поиск">
            ×
          </button>
        ) : null}
      </label>

      <div className="chips catalog-chips" aria-label="Категории партнёров">
        {categories.map((category) => (
          <button
            className={category === selectedCategory ? "chip catalog-chip chip--active" : "chip catalog-chip"}
            type="button"
            key={category}
            onClick={() => setSelectedCategory(category)}
          >
            {category}
          </button>
        ))}
      </div>

      {!safePartners.length || !visiblePartners.length ? (
        <div className="catalog-empty-state" role="status">
          <span aria-hidden="true">✦</span>
          <h2>{emptyTitle}</h2>
          <p>{emptyDescription}</p>
        </div>
      ) : (
        <div className="cards-grid catalog-grid">
          {visiblePartners.map((partner) => {
            const image = getPartnerImage(partner);
            const name = getPartnerName(partner);
            const categoriesText = getPartnerCategories(partner).join(" • ");
            const city = getPartnerCity(partner);
            const address = getPartnerAddress(partner);
            const distance = getPartnerDistance(partner);
            const offerText = getOfferAvailabilityText(partner);
            const preview = getPartnerDescription(partner);

            return (
              <article className="partner-card" key={String(partner.id ?? name)}>
                <button className="partner-card__open" type="button" onClick={() => onOpenPartner(partner)} aria-label={`Открыть ${name}`}>
                  <span className="partner-card__media">
                    <PartnerCardImage src={image} name={name} />
                    {categoriesText ? <span className="partner-card__category">{categoriesText}</span> : null}
                  </span>
                  <span className="partner-card__body">
                    <strong>{name}</strong>
                    <small>{[city, distance].filter(Boolean).join(" • ") || "Партнёр Bloom Club"}</small>
                    {address ? <span className="partner-card__address">{address}</span> : null}
                    <span className="partner-card__preview">{preview}</span>
                    {offerText ? <em>{offerText}</em> : null}
                  </span>
                </button>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
