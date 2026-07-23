import { useState } from 'react';
import { isApiError, isTimeoutError } from '../api/client';
import { ContentText } from '../components/ContentText';
import { useContentText } from '../content/ContentContext';
import type { ClientProfile, PaymentRequest, Subscription } from '../api/types';
import { formatDate } from '../utils/format';
import { getSubscriptionEnd, isSubscriptionActive, isTrialEligible } from '../utils/subscription';

interface SubscriptionPageProps {
  profile: ClientProfile | null;
  subscription: Subscription | null;
  paymentRequest: PaymentRequest | null;
  isCreatingPayment: boolean;
  trialMessage: string | null;
  onCreatePayment: () => void;
  onActivateTrial: () => Promise<Subscription>;
  onBack: () => void;
}

function getTrialErrorMessage(error: unknown): string {
  if (isTimeoutError(error)) {
    return 'Загрузка заняла слишком много времени. Попробуйте ещё раз.';
  }

  if (isApiError(error) && error.status === 409) {
    return 'У вас уже есть активный доступ';
  }

  if (isApiError(error) && [400, 403, 422].includes(error.status || 0)) {
    return 'Пробный период уже использован';
  }

  return 'Не удалось активировать тестовый период. Попробуйте ещё раз.';
}

export function SubscriptionPage({
  profile,
  subscription,
  isCreatingPayment,
  trialMessage,
  onActivateTrial,
  onBack,
}: SubscriptionPageProps) {
  const [isActivatingTrial, setIsActivatingTrial] = useState(false);
  const [localMessage, setLocalMessage] = useState('');
  const [localError, setLocalError] = useState('');
  const accessEnd = getSubscriptionEnd(subscription);
  const hasAccess = isSubscriptionActive(subscription);
  const trialAvailable = isTrialEligible(profile, subscription);
  const backLabel = useContentText('subscription.back', '← Назад');
  const trialCta = useContentText('subscription.trial.cta', 'Подключить пробный период 15 дней');

  async function handleTrial() {
    setIsActivatingTrial(true);
    setLocalMessage('');
    setLocalError('');

    try {
      const updated = await onActivateTrial();
      const end = getSubscriptionEnd(updated);
      setLocalMessage(end ? `Тестовый период активирован. Доступ к клубу до ${formatDate(end)}.` : 'Тестовый период активирован.');
    } catch (caughtError) {
      setLocalError(getTrialErrorMessage(caughtError));
    } finally {
      setIsActivatingTrial(false);
    }
  }

  return (
    <section className="page">
      <button className="link-button" type="button" onClick={onBack}>{backLabel}</button>
      <div className="subscription-card">
        <ContentText as="p" className="eyebrow" textKey="subscription.eyebrow" fallback="Подписка Bloom Club" />
        <ContentText as="h1" textKey="subscription.title" fallback="349 ₽ / месяц" />
        <ContentText as="p" textKey="subscription.description" fallback="Доступ на 1 месяц к клубным привилегиям у партнёров Bloom Club. Автопродление не подключено, продление выполняется вручную." multiline />
        {trialAvailable ? (
          <button className="button button--primary" type="button" onClick={() => void handleTrial()} disabled={isActivatingTrial}>
            {isActivatingTrial ? 'Активируем…' : trialCta}
          </button>
        ) : null}
        <div className="info-panel info-panel--soft">
          <ContentText as="strong" textKey="subscription.payment_soon.title" fallback="Оплата скоро появится" />
          <ContentText as="p" textKey="subscription.payment_soon.description" fallback="Сейчас можно активировать тестовый период, если он доступен." multiline />
        </div>
        {isCreatingPayment ? <small>Проверяем возможность продления…</small> : null}
        {localError ? <p className="error-text">{localError}</p> : null}
        {localMessage || (!localError && trialMessage) ? <p className="success-text">{localMessage || trialMessage}</p> : null}
      </div>

      <div className="info-panel">
        <ContentText as="strong" textKey="subscription.current_access.title" fallback="Текущий доступ" />
        <p>{hasAccess ? `Доступ активен до ${formatDate(accessEnd)}` : 'Доступ не активен'}</p>
      </div>

      <div className="terms-list">
        <ContentText as="h2" textKey="subscription.terms.title" fallback="Условия подписки" />
        <ul>
          <li>Стоимость — 349 ₽ / месяц.</li>
          <li>Доступ открывается на 1 месяц.</li>
          <li>Автопродление не подключено.</li>
          <li>Продление выполняется вручную.</li>
          <li>Привилегии зависят от условий конкретного партнёра.</li>
        </ul>
      </div>
    </section>
  );
}
