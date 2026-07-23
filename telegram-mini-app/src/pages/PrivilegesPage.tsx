import type { Offer, Verification } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { ContentText } from '../components/ContentText';
import { useContentText } from '../content/ContentContext';
import { formatDate, formatMoney } from '../utils/format';
import { getOfferPrices, getOfferTitle, getPartnerName, getVerificationCode } from '../utils/partnerDisplay';
import { toText } from '../utils/text';

interface PrivilegesPageProps {
  verifications?: Verification[] | null;
  emptyTitle?: string;
  emptyDescription?: string;
}


function mergeDefinedPriceSource(verification: Verification): Offer | Verification {
  const merged: Record<string, unknown> = { ...(verification.offer || {}) };

  Object.entries(verification).forEach(([key, value]) => {
    if (value !== undefined && key !== 'offer') {
      merged[key] = value;
    }
  });

  return merged as Offer | Verification;
}

function statusLabel(status: unknown): string {
  const normalized = toText(status).toLowerCase();

  if (normalized === 'confirmed') {
    return 'Подтверждена';
  }

  if (normalized === 'expired') {
    return 'Истекла';
  }

  return 'Активна';
}

export function PrivilegesPage({ verifications, emptyTitle, emptyDescription }: PrivilegesPageProps) {
  const safeVerifications = Array.isArray(verifications) ? verifications : [];
  const defaultEmptyTitle = useContentText('privileges.empty.title', 'Здесь появятся ваши коды привилегий');
  const defaultEmptyDescription = useContentText('privileges.empty.description', 'Выберите партнёра и получите код на нужную услугу.');

  return (
    <section className="page">
      <div className="page-header">
        <ContentText as="p" className="eyebrow" textKey="privileges.eyebrow" fallback="Мои привилегии" />
        <ContentText as="h1" textKey="privileges.title" fallback="Коды привилегий" />
        <ContentText as="p" textKey="privileges.description" fallback="Здесь сохраняются коды, которые вы получили у партнёров клуба." multiline />
      </div>

      {safeVerifications.length ? (
        <div className="verification-list">
          {safeVerifications.map((verification, index) => {
            const prices = getOfferPrices(mergeDefinedPriceSource(verification));
            const code = getVerificationCode(verification) || 'Код формируется';

            return (
              <article className="verification-card" key={verification.id ?? index}>
                <div className="verification-card__code">
                  <span>Код привилегии</span>
                  <strong>{code}</strong>
                </div>
                <div>
                  <strong>{verification.partner ? getPartnerName(verification.partner) : 'Партнёр Bloom Club'}</strong>
                  <p>{verification.offer ? getOfferTitle(verification.offer) : 'Услуга партнёра'}</p>
                  <p>Статус: {statusLabel(verification.status)}</p>
                  <small>Действует до: {formatDate(verification.expires_at || verification.valid_until)}</small>
                  <div className="price-grid price-grid--compact">
                    {prices.basePrice !== undefined ? <span><small>Обычная цена</small>{formatMoney(prices.basePrice)}</span> : null}
                    {prices.hasValidMemberPrice ? <span><small>Цена для участницы</small>{formatMoney(prices.memberPrice)}</span> : null}
                    {prices.hasValidSaving ? <span><small>Экономия</small>{formatMoney(prices.saving)}</span> : null}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title={emptyTitle || defaultEmptyTitle}
          description={emptyDescription || defaultEmptyDescription}
        />
      )}
    </section>
  );
}
