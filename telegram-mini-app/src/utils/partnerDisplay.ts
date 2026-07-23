import type { Offer, Partner, Verification } from '../api/types';
import { parseMoney, roundMoney } from './format';
import { pickText, toText } from './text';

const DEFAULT_PRIVILEGE = 'Клубное предложение по условиям партнёра';
const DEFAULT_PARTNER_DESCRIPTION = 'Описание партнёра скоро появится.';
const SITE_ORIGIN = 'https://bloomclub.ru';

export interface OfferPrices {
  basePrice?: number;
  memberPrice?: number;
  saving?: number;
  hasValidMemberPrice: boolean;
  hasValidSaving: boolean;
}

export interface NumericPartnerIdResolution {
  numericPartnerId: number;
  source: 'partner.id';
}

export function pickReadableValue(...values: Array<unknown>): string | undefined {
  return pickText(...values);
}

function field<T extends object>(source: T | null | undefined, key: string): unknown {
  return source ? (source as T & Record<string, unknown>)[key] : undefined;
}

function normalizeMediaUrl(value: unknown): string | undefined {
  const text = toText(value);

  if (!text) {
    return undefined;
  }

  if (/^https?:\/\//i.test(text)) {
    return text;
  }

  if (text.startsWith('//')) {
    return `https:${text}`;
  }

  if (text.startsWith('/')) {
    return `${SITE_ORIGIN}${text}`;
  }

  return `${SITE_ORIGIN}/${text}`;
}

function collectMediaValues(value: unknown): unknown[] {
  if (!value) {
    return [];
  }

  if (Array.isArray(value)) {
    return value.flatMap(collectMediaValues);
  }

  if (typeof value === 'object') {
    if (field(value, 'is_active') === false) {
      return [];
    }

    return [
      field(value, 'image'),
      field(value, 'image_url'),
      field(value, 'photo'),
      field(value, 'photo_url'),
      field(value, 'cover'),
      field(value, 'cover_url'),
      field(value, 'avatar_url'),
      field(value, 'url'),
      field(value, 'src'),
      field(value, 'path'),
      field(value, 'file_path'),
    ];
  }

  return [value];
}

export function getPartnerName(partner: Partner | null | undefined): string {
  return pickReadableValue(
    field(partner, 'display_name'),
    partner?.title,
    partner?.name,
    field(partner, 'legal_name'),
  ) || 'Партнёр клуба';
}

export function getPartnerImages(partner: Partner | null | undefined): string[] {
  if (!partner) {
    return [];
  }

  const candidates = [
    field(partner, 'image'),
    partner.image_url,
    field(partner, 'photo'),
    partner.photo_url,
    field(partner, 'cover'),
    partner.cover_url,
    partner.logo_url,
    partner.photos,
    partner.avatar_url,
    partner.images,
    partner.gallery,
    partner.media,
  ];

  return Array.from(
    new Set(candidates.flatMap(collectMediaValues).map(normalizeMediaUrl).filter((url): url is string => Boolean(url))),
  );
}

export function getOfferImages(offer: Offer | null | undefined): string[] {
  if (!offer) {
    return [];
  }

  return Array.from(
    new Set([offer.image_url, offer.photo_url, offer.photos].flatMap(collectMediaValues).map(normalizeMediaUrl).filter((url): url is string => Boolean(url))),
  );
}

export function getPartnerImage(partner: Partner | null | undefined): string | undefined {
  return getPartnerImages(partner)[0];
}

function toNumericId(value: unknown): number | null {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) {
    return value;
  }

  if (typeof value === 'string' && /^\d+$/.test(value.trim())) {
    const numeric = Number(value.trim());
    return Number.isSafeInteger(numeric) && numeric > 0 ? numeric : null;
  }

  return null;
}

export function resolveNumericPartnerId(partner: Partner | null | undefined): NumericPartnerIdResolution | null {
  const numericPartnerId = toNumericId(partner?.id);
  return numericPartnerId === null ? null : { numericPartnerId, source: 'partner.id' };
}

export function isNumericApiId(value: unknown): value is string | number {
  return toNumericId(value) !== null;
}


function readBooleanFlag(value: unknown): boolean | null {
  if (value === true || value === 'true' || value === 1 || value === '1') {
    return true;
  }

  if (value === false || value === 'false' || value === 0 || value === '0') {
    return false;
  }

  return null;
}

function readSortOrder(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function isProductionSeedPartner(partner: Partner): boolean {
  const identityText = [
    getPartnerName(partner),
    partner.slug,
    field(partner, 'external_slug'),
    field(partner, 'code'),
  ]
    .map((value) => toText(value).trim().toLowerCase())
    .filter(Boolean)
    .join(' ');

  return /(^|\b)(demo spa|demo fitness|route-test|route test)(\b|$)/i.test(identityText);
}

export function isVisiblePartner(partner: Partner | null | undefined): partner is Partner {
  if (!partner || typeof partner !== 'object') {
    return false;
  }

  const record = partner as Partner & Record<string, unknown>;
  const activeFlags = [record.is_active, record.active, record.is_visible, record.visible, record.published];
  if (activeFlags.some((value) => readBooleanFlag(value) === false)) {
    return false;
  }

  const hiddenFlags = [record.is_hidden, record.hidden, record.deleted, record.is_deleted, record.archived, record.is_archived];
  if (hiddenFlags.some((value) => readBooleanFlag(value) === true)) {
    return false;
  }

  return !isProductionSeedPartner(partner);
}

export function sortPartnersForCatalog(partners: Partner[] | null | undefined): Partner[] {
  const safePartners = Array.isArray(partners) ? partners : [];
  return safePartners
    .filter(isVisiblePartner)
    .map((partner, index) => ({ partner, index }))
    .sort((left, right) => {
      const orderDiff = readSortOrder(left.partner.sort_order, (left.index + 1) * 100) - readSortOrder(right.partner.sort_order, (right.index + 1) * 100);
      return orderDiff || getPartnerName(left.partner).localeCompare(getPartnerName(right.partner), 'ru');
    })
    .map(({ partner }) => partner);
}

export function isVisibleOffer(offer: Offer | null | undefined): offer is Offer {
  if (!offer || typeof offer !== 'object') {
    return false;
  }

  const record = offer as Offer & Record<string, unknown>;
  const activeFlags = [record.is_active, record.active, record.is_visible, record.visible, record.available, record.is_available];
  if (activeFlags.some((value) => readBooleanFlag(value) === false)) {
    return false;
  }

  const hiddenFlags = [record.is_hidden, record.hidden, record.deleted, record.is_deleted, record.archived, record.is_archived];
  return !hiddenFlags.some((value) => readBooleanFlag(value) === true);
}

export function sortOffersForPartner(offers: Offer[] | null | undefined): Offer[] {
  const safeOffers = Array.isArray(offers) ? offers : [];
  return safeOffers
    .filter(isVisibleOffer)
    .map((offer, index) => ({ offer, index }))
    .sort((left, right) => readSortOrder(left.offer.sort_order, (left.index + 1) * 100) - readSortOrder(right.offer.sort_order, (right.index + 1) * 100))
    .map(({ offer }) => offer);
}

export function getPartnerCity(partner: Partner | null | undefined): string | undefined {
  return pickReadableValue(partner?.city);
}

function normalizeCategory(category: unknown): string {
  const categoryMap: Record<string, string> = {
    beauty: 'Красота',
    health: 'Здоровье',
    style: 'Стиль',
    fashion: 'Стиль',
    rest: 'Отдых',
    leisure: 'Отдых',
    wellness: 'Забота о себе',
    fitness: 'Фитнес',
    food: 'Еда и напитки',
    restaurant: 'Еда и напитки',
    restaurants: 'Еда и напитки',
  };

  const prepared = toText(category);

  if (!prepared) {
    return '';
  }

  return categoryMap[prepared.toLowerCase()] || prepared;
}

export function getPartnerCategories(partner: Partner | null | undefined): string[] {
  const sourceCategories = partner?.categories;
  const categories: unknown[] = Array.isArray(sourceCategories) ? [...sourceCategories] : [sourceCategories];

  categories.push(partner?.category);

  return Array.from(new Set(categories.map(normalizeCategory).filter(Boolean)));
}

export function getPartnerDescription(partner: Partner | null | undefined): string {
  return pickReadableValue(partner?.description, field(partner, 'offer_description')) || DEFAULT_PARTNER_DESCRIPTION;
}

export function getPartnerAddress(partner: Partner | null | undefined): string | undefined {
  return pickReadableValue(partner?.address);
}

export function getPartnerPhone(partner: Partner | null | undefined): string | undefined {
  const contact = field(partner, 'contact');

  return pickReadableValue(partner?.phone, partner?.phone_number, field(partner, 'contact_phone'), field(partner, 'tel'), field(contact as object | null | undefined, 'phone'));
}

export function normalizeTelHref(phone: unknown): string | undefined {
  const text = toText(phone);

  if (!text) {
    return undefined;
  }

  const normalized = `${text.trim().startsWith('+') ? '+' : ''}${text.replace(/\D/g, '')}`;
  const digits = normalized.replace(/\D/g, '');

  return digits.length >= 7 ? normalized : undefined;
}

export function getPartnerPrivilege(partner: Partner | null | undefined): string {
  return pickReadableValue(
    partner?.privilege,
    partner?.offer_preview,
    partner?.discount,
    field(partner, 'benefit'),
    field(partner, 'offer'),
    field(partner, 'offer_title'),
  ) || DEFAULT_PRIVILEGE;
}

export function getOfferTitle(offer: Offer | null | undefined): string {
  return pickReadableValue(offer?.title) || 'Услуга партнёра';
}

export function getOfferDescription(offer: Offer | null | undefined): string {
  return pickReadableValue(offer?.description, offer?.benefit_text, offer?.conditions) || 'Подробности подскажет партнёр.';
}

export function getOfferConditions(offer: Offer | null | undefined): string | undefined {
  return pickReadableValue(offer?.conditions);
}

export function getOfferBenefit(offer: Offer | null | undefined): string | undefined {
  return pickReadableValue(offer?.benefit_text);
}

function pickRoundedMoney(...values: unknown[]): number | undefined {
  for (const value of values) {
    const parsed = parseMoney(value);

    if (parsed !== null) {
      return roundMoney(parsed);
    }
  }

  return undefined;
}

export { parseMoney, roundMoney };

export function getOfferPricePreview(source: Offer | Verification | null | undefined): OfferPrices {
  const basePrice = pickRoundedMoney(
    field(source, 'base_price'),
    field(source, 'original_price'),
    field(source, 'price'),
    field(source, 'old_price'),
    field(source, 'regular_price'),
  );
  const explicitMemberPrice = pickRoundedMoney(
    field(source, 'member_price'),
    field(source, 'club_price'),
    field(source, 'final_price'),
    field(source, 'discounted_price'),
    field(source, 'price_with_discount'),
  );
  const discountPercent = parseMoney(field(source, 'discount_percent'));
  const calculatedMemberPrice =
    basePrice !== undefined && explicitMemberPrice === undefined && discountPercent !== null && discountPercent > 0 && discountPercent < 100
      ? roundMoney(basePrice * (1 - discountPercent / 100))
      : undefined;
  const memberPrice = explicitMemberPrice ?? calculatedMemberPrice;
  const explicitSaving = pickRoundedMoney(
    field(source, 'saving'),
    field(source, 'saving_amount'),
    field(source, 'discount_amount'),
  );
  const calculatedSaving = basePrice !== undefined && memberPrice !== undefined && memberPrice > 0
    ? roundMoney(basePrice - memberPrice)
    : undefined;
  const saving = explicitSaving !== undefined ? explicitSaving : calculatedSaving;

  return {
    basePrice,
    memberPrice,
    saving,
    hasValidMemberPrice: memberPrice !== undefined && memberPrice > 0,
    hasValidSaving: saving !== undefined && saving > 0,
  };
}

export function getOfferPrices(source: Offer | Verification | null | undefined): OfferPrices {
  return getOfferPricePreview(source);
}

export function hasEmbeddedOffers(partner: Partner | null | undefined): boolean | undefined {
  if (!partner || !('offers' in partner)) {
    return undefined;
  }

  return Array.isArray(partner.offers) ? partner.offers.length > 0 : false;
}

export function getVerificationCode(verification: Verification | null | undefined): string | undefined {
  return pickReadableValue(verification?.display_code, verification?.code);
}
