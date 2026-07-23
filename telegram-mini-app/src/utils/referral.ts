import type { BackendText, ClientProfile, ReferralSummary } from '../api/types';
import { toText } from './text';

type RuntimeTelegramConfig = {
  telegramBotUsername?: string;
};

declare global {
  interface Window {
    __BLOOM_TG_CONFIG__?: RuntimeTelegramConfig;
  }
}

function getBotUsername(): string {
  return (
    window.__BLOOM_TG_CONFIG__?.telegramBotUsername ||
    import.meta.env.VITE_TELEGRAM_BOT_USERNAME ||
    import.meta.env.VITE_BOT_USERNAME ||
    ''
  )
    .replace(/^@/, '')
    .trim();
}

function normalizeTelegramMainAppLink(value: string): string {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.hostname !== 't.me') {
      return '';
    }
    const pathParts = url.pathname.split('/').filter(Boolean);
    if (pathParts.length !== 1 || !pathParts[0]) {
      return '';
    }
    url.search = '';
    url.hash = '';
    return url.toString().replace(/\/$/, '');
  } catch {
    return '';
  }
}

export function buildTelegramReferralLink(referralCode?: BackendText | null): string {
  const code = toText(referralCode);
  if (!code) {
    return '';
  }

  const botUsername = getBotUsername();
  const mainAppLink = botUsername ? `https://t.me/${encodeURIComponent(botUsername)}` : '';
  if (!mainAppLink) {
    return '';
  }

  const url = new URL(mainAppLink);
  url.searchParams.set('startapp', code);
  return url.toString();
}

export function getReferralLink(referralSummary?: ReferralSummary | null, profile?: ClientProfile | null): string {
  const backendLink = normalizeTelegramMainAppLink(toText(referralSummary?.referral_link || profile?.referral_link));
  if (backendLink) {
    const code = toText(referralSummary?.referral_code || profile?.referral_code);
    if (!code) {
      return '';
    }
    const url = new URL(backendLink);
    url.searchParams.set('startapp', code);
    return url.toString();
  }
  return buildTelegramReferralLink(referralSummary?.referral_code || profile?.referral_code);
}

export async function shareOrCopyReferralLink(link: string, text = 'Присоединяйся к Bloom Club'): Promise<'shared' | 'copied' | 'unavailable'> {
  if (!link) {
    return 'unavailable';
  }
  if (navigator.share) {
    try {
      await navigator.share({ title: 'Bloom Club', text, url: link });
      return 'shared';
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return 'unavailable';
      }
    }
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(link);
    return 'copied';
  }
  return 'unavailable';
}
