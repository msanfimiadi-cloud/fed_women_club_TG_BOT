import type { SavingsSummary } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { ContentText } from '../components/ContentText';
import { useContentText } from '../content/ContentContext';
import { formatDate, formatMoney } from '../utils/format';
import { getPartnerName } from '../utils/partnerDisplay';
import { toText } from '../utils/text';

interface SavingsPageProps {
  savings: SavingsSummary | null;
  emptyTitle?: string;
  emptyDescription?: string;
}

export function SavingsPage({ savings, emptyTitle, emptyDescription }: SavingsPageProps) {
  const total = savings?.total ?? savings?.amount ?? 0;
  const items = Array.isArray(savings?.items) ? savings.items : [];
  const defaultEmptyTitle = useContentText('savings.empty.title', 'Ваша экономия появится после первого использования привилегии.');
  const defaultEmptyDescription = useContentText('savings.empty.description', 'Используйте коды привилегий у партнёров — мы аккуратно соберём историю здесь.');

  return (
    <section className="page">
      <div className="savings-hero">
        <ContentText as="p" className="eyebrow" textKey="savings.eyebrow" fallback="Экономия" />
        <h1>{formatMoney(total, toText(savings?.currency, '₽'))}</h1>
        <ContentText as="p" textKey="savings.description" fallback="Здесь появится сумма вашей выгоды после использования привилегий." multiline />
      </div>

      {items.length ? (
        <div className="timeline">
          {items.map((item, index) => (
            <article className="timeline-item" key={item.id ?? index}>
              <strong>{item.partner ? getPartnerName(item.partner) : toText(item.partner_name, 'Партнёр клуба')}</strong>
              <span>{formatMoney(item.amount ?? item.value)}</span>
              <small>{formatDate(item.created_at)}</small>
              {toText(item.description) ? <p>{toText(item.description)}</p> : null}
            </article>
          ))}
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
