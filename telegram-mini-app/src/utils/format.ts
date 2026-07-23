import { toText } from './text';

export function parseMoney(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();

  if (!trimmed) {
    return null;
  }

  const compact = trimmed.replace(/\s+/g, '');
  const prepared = compact
    .replace(/[^\d,.-]/g, '')
    .replace(/,(?=\d{1,2}$)/, '.')
    .replace(/,/g, '');

  if (!prepared || prepared === '-' || prepared === '.' || prepared === '-.') {
    return null;
  }

  const amount = Number(prepared);
  return Number.isFinite(amount) ? amount : null;
}

export function roundMoney(value: number): number {
  return Math.round(value);
}

export function formatMoney(value?: unknown, currency: unknown = '₽'): string {
  const parsed = parseMoney(value);
  const safeCurrency = toText(currency, '₽');

  if (parsed === null) {
    return '';
  }

  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(roundMoney(parsed))} ${safeCurrency}`;
}

export function formatDate(value?: unknown): string {
  const text = toText(value);

  if (!text) {
    return 'не указано';
  }

  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text;
  }

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}

export function buildYandexMapsUrl(options: {
  latitude?: string | number;
  longitude?: string | number;
  address?: unknown;
}): string | null {
  const latitude = Number(options.latitude);
  const longitude = Number(options.longitude);
  const address = toText(options.address);

  if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
    return `https://yandex.ru/maps/?ll=${longitude},${latitude}&z=16&pt=${longitude},${latitude},pm2rdm`;
  }

  if (address) {
    return `https://yandex.ru/maps/?text=${encodeURIComponent(address)}`;
  }

  return null;
}
