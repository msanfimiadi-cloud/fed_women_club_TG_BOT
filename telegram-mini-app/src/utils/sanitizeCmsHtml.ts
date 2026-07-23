const TAG_PATTERN = /<[^>]*>/g;
const SCRIPT_OR_STYLE_PATTERN = /<\s*(script|style)\b[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi;

const HTML_ENTITIES: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
};

function decodeHtmlEntity(entity: string): string {
  if (entity.startsWith("#x") || entity.startsWith("#X")) {
    const codePoint = Number.parseInt(entity.slice(2), 16);
    return Number.isFinite(codePoint) ? String.fromCodePoint(codePoint) : `&${entity};`;
  }

  if (entity.startsWith("#")) {
    const codePoint = Number.parseInt(entity.slice(1), 10);
    return Number.isFinite(codePoint) ? String.fromCodePoint(codePoint) : `&${entity};`;
  }

  return HTML_ENTITIES[entity] ?? `&${entity};`;
}

function decodeHtmlEntities(value: string): string {
  return value.replace(/&([a-zA-Z][a-zA-Z0-9]+|#[0-9]+|#x[0-9a-fA-F]+);/g, (_match, entity: string) =>
    decodeHtmlEntity(entity),
  );
}

/**
 * Converts CMS-provided rich text into inert display text.
 *
 * Home CMS blocks are authored outside of this bundle, so they must never be
 * mounted as HTML. Returning plain text preserves visible copy while ensuring
 * scripts, event handlers, dangerous URLs, and arbitrary markup cannot execute
 * in the Telegram WebView origin.
 */
export function sanitizeCmsHtml(value: string | null | undefined): string {
  if (!value) return "";

  return decodeHtmlEntities(
    value
      .replace(SCRIPT_OR_STYLE_PATTERN, " ")
      .replace(/<\s*br\s*\/?>/gi, "\n")
      .replace(/<\s*\/\s*(p|div|section|article|h[1-6]|li|ul|ol|blockquote)\s*>/gi, "\n")
      .replace(TAG_PATTERN, " "),
  )
    .replace(/[\t\f\v ]+/g, " ")
    .replace(/\s*\n\s*/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
