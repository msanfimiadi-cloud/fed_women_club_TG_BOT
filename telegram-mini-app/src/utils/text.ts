const READABLE_OBJECT_KEYS = ['name', 'title', 'label', 'display_name', 'slug', 'legal_name', 'value'] as const;
const UNREADABLE_TEXT_VALUES = new Set(['undefined', 'null', 'unknown']);

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function maybeTrim(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function toText(value: unknown, fallback = ''): string {
  const directText = maybeTrim(value);

  if (directText && !UNREADABLE_TEXT_VALUES.has(directText.toLowerCase())) {
    return directText;
  }

  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }

  if (Array.isArray(value)) {
    const arrayText = value.map((item) => toText(item)).filter(Boolean).join(', ');
    return arrayText || fallback;
  }

  if (isPlainRecord(value)) {
    for (const key of READABLE_OBJECT_KEYS) {
      const fieldText = toText(value[key]);

      if (fieldText) {
        return fieldText;
      }
    }
  }

  return fallback;
}

export function hasText(value: unknown): boolean {
  return toText(value).length > 0;
}

export function pickText(...values: Array<unknown>): string | undefined {
  for (const value of values) {
    const text = toText(value);

    if (text) {
      return text;
    }
  }

  return undefined;
}
