import type { HomeBlock } from "../content/clientContentApi";

const TRIAL_CTA_TEXT_PATTERN = /подключить\s+(?:тестовый|пробный)\s+период/i;

export function resolveHomeCtaAction(block: Pick<HomeBlock, "cta_action" | "cta_text">): string {
  const explicitAction = String(block.cta_action || "").trim();

  if (explicitAction) {
    return explicitAction;
  }

  const ctaText = String(block.cta_text || "").trim();

  if (TRIAL_CTA_TEXT_PATTERN.test(ctaText)) {
    return "trial";
  }

  return "";
}
