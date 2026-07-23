import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { isApiError, isTimeoutError } from '../api/client';
import { AppImage } from '../components/AppImage';
import { ContentText } from '../components/ContentText';
import { useContentText } from '../content/ContentContext';
import type { City, ClientProfile, ClientProfilePatch, ReferralSummary, Subscription } from '../api/types';
import { formatDate } from '../utils/format';
import { getSubscriptionEnd, isSubscriptionActive, isTrialEligible } from '../utils/subscription';
import { pickText, toText } from '../utils/text';
import { getReferralLink, shareOrCopyReferralLink } from '../utils/referral';
// shareOrCopyReferralLink uses navigator.share with navigator.clipboard fallback.

type TextChangeEvent = { target?: { value?: string } | null; currentTarget?: { value?: string } | null } | null | undefined;

function readChangeValue(event: TextChangeEvent): string {
  return event?.currentTarget?.value ?? event?.target?.value ?? "";
}

interface ProfilePageProps {
  profile: ClientProfile | null;
  subscription: Subscription | null;
  cities?: City[] | null;
  onOpenSubscription: () => void;
  onActivateTrial: () => Promise<Subscription>;
  onSaveProfile: (payload: ClientProfilePatch) => Promise<ClientProfile>;
  referralSummary?: ReferralSummary | null;
}

function isValidPhone(value: string): boolean {
  if (!value.trim()) {
    return true;
  }

  return /^\+?[\d\s()\-]{10,20}$/.test(value.trim());
}

function isValidEmail(value: string): boolean {
  if (!value.trim()) {
    return true;
  }

  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function getCityName(city: unknown): string {
  return toText(city);
}

function getProfileDisplayName(profile: ClientProfile | null | undefined): string {
  return pickText(
    profile?.full_name,
    profile?.name,
    profile?.user?.full_name,
    profile?.user?.name,
    [profile?.telegram_first_name, profile?.telegram_last_name],
    [profile?.first_name, profile?.last_name],
    [profile?.user?.first_name, profile?.user?.last_name],
  ) || '';
}

export function ProfilePage({ profile, subscription, cities, onOpenSubscription, onActivateTrial, onSaveProfile, referralSummary }: ProfilePageProps) {
  const safeCities = useMemo(() => (Array.isArray(cities) ? cities : []), [cities]);
  const initialName = getProfileDisplayName(profile);
  const initialCity = getCityName(profile?.city);
  const [name, setName] = useState(initialName);
  const [phone, setPhone] = useState(toText(profile?.phone));
  const [email, setEmail] = useState(toText(profile?.email));
  const [city, setCity] = useState(initialCity);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const avatarUrl = toText(profile?.avatar_url);
  const defaultProfileName = useContentText('profile.default_name', 'Участница Bloom Club');
  const defaultProfileCity = useContentText('profile.default_city', 'Город можно указать ниже.');
  const manageSubscriptionCta = useContentText('profile.subscription.cta', 'Управлять подпиской');
  const trialCta = useContentText('profile.trial.cta', 'Подключить пробный период 15 дней');
  const trialAvailable = isTrialEligible(profile, subscription);
  const [isActivatingTrial, setIsActivatingTrial] = useState(false);
  const referralLink = getReferralLink(referralSummary, profile);
  const invitedCount = referralSummary?.pending_referrals_count ?? referralSummary?.invited_count ?? referralSummary?.referrals_count ?? profile?.referrals_count ?? 0;
  const activatedCount = referralSummary?.activated_referrals_count ?? 0;
  const entriesCount = referralSummary?.earned_entries_count ?? referralSummary?.earned_giveaway_entries_count ?? profile?.earned_giveaway_entries_count ?? profile?.referral_entries_count ?? 0;

  useEffect(() => {
    setName(initialName);
    setPhone(toText(profile?.phone));
    setEmail(toText(profile?.email));
    setCity(initialCity);
  }, [initialName, initialCity, profile?.phone, profile?.email]);

  async function handleActivateTrial() {
    setError('');
    setMessage('');
    setIsActivatingTrial(true);

    try {
      const updated = await onActivateTrial();
      const end = getSubscriptionEnd(updated);
      setMessage(end ? `Тестовый период активирован. Доступ к клубу до ${formatDate(end)}.` : 'Тестовый период активирован.');
    } catch (caughtError) {
      if (isTimeoutError(caughtError)) {
        setError('Загрузка заняла слишком много времени. Попробуйте ещё раз.');
      } else if (isApiError(caughtError) && [400, 403, 409, 422].includes(caughtError.status || 0)) {
        setError('Пробный период уже использован');
      } else {
        setError('Не удалось активировать тестовый период. Попробуйте ещё раз.');
      }
    } finally {
      setIsActivatingTrial(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setMessage('');

    if (!isValidPhone(phone)) {
      setError('Введите корректный номер телефона');
      return;
    }

    if (!isValidEmail(email)) {
      setError('Введите корректный email');
      return;
    }

    setIsSaving(true);

    try {
      await onSaveProfile({
        full_name: name.trim(),
        name: name.trim(),
        phone: phone.trim(),
        email: email.trim(),
        contact_email: email.trim(),
        custom_city: city.trim(),
        city: city.trim(),
      });
      setMessage('Данные сохранены');
    } catch (caughtError) {
      setError(isTimeoutError(caughtError) ? 'Загрузка заняла слишком много времени. Данные не сохранены, попробуйте ещё раз.' : 'Не удалось сохранить данные. Попробуйте ещё раз.');
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="page">
      <div className="profile-card">
        <div className="profile-card__avatar"><AppImage src={avatarUrl} alt="" placeholder="♡" placeholderClassName="profile-card__avatar-placeholder image-placeholder" /></div>
        <h1>{name || defaultProfileName}</h1>
        <p>{city || defaultProfileCity}</p>
      </div>

      <form className="profile-form" onSubmit={(event: FormEvent<HTMLFormElement>) => void handleSubmit(event)}>
        <div>
          <ContentText as="h2" textKey="profile.title" fallback="Профиль" />
          <ContentText as="p" textKey="profile.description" fallback="Пожалуйста, заполните данные ниже. Они могут понадобиться для связи с вами в случае вашей победы в ежемесячном розыгрыше." multiline />
        </div>
        <label>
          Имя
          <input value={name} onChange={(event: { target: { value: string } }) => setName(readChangeValue(event))} placeholder="Ваше имя" />
        </label>
        <label>
          Телефон
          <input value={phone} onChange={(event: { target: { value: string } }) => setPhone(readChangeValue(event))} placeholder="+7 999 000-00-00" inputMode="tel" />
        </label>
        <label>
          Email
          <input value={email} onChange={(event: { target: { value: string } }) => setEmail(readChangeValue(event))} placeholder="name@example.com" inputMode="email" />
        </label>
        <label>
          Город
          <input value={city} onChange={(event: { target: { value: string } }) => setCity(readChangeValue(event))} list="club-cities" placeholder="Новосибирск" />
          <datalist id="club-cities">
            {safeCities.map((item) => {
              const cityName = getCityName(item);
              return cityName ? <option value={cityName} key={item.id ?? cityName} /> : null;
            })}
          </datalist>
        </label>
        {error ? <p className="error-text">{error}</p> : null}
        {message ? <p className="success-text">{message}</p> : null}
        <button className="button button--primary" type="submit" disabled={isSaving}>
          {isSaving ? 'Сохраняем…' : 'Сохранить данные'}
        </button>
      </form>


      <div className="info-panel info-panel--soft referral-profile-card">
        <ContentText as="strong" textKey="profile.referral.title" fallback="Моя реферальная ссылка" />
        <p>Приглашено: {invitedCount}. Активировали trial: {activatedCount}. Получено номеров: {entriesCount}.</p>
        {referralLink ? <code className="referral-link">{referralLink}</code> : <p>Ссылка появится после обновления профиля backend.</p>}
        <div className="referral-profile-card__actions">
          <button className="button button--ghost" type="button" disabled={!referralLink} onClick={() => referralLink && navigator.clipboard?.writeText(referralLink)}>
            Скопировать ссылку
          </button>
          <button className="button button--primary" type="button" disabled={!referralLink} onClick={() => shareOrCopyReferralLink(referralLink)}>
            Поделиться
          </button>
        </div>
      </div>

      <div className="info-panel">
        <ContentText as="strong" textKey="profile.subscription.title" fallback="Подписка" />
        <p>{isSubscriptionActive(subscription) ? `Доступ активен до ${formatDate(getSubscriptionEnd(subscription))}` : 'Доступ не активен'}</p>
        {trialAvailable ? (
          <button className="button button--primary" type="button" onClick={() => void handleActivateTrial()} disabled={isActivatingTrial}>
            {isActivatingTrial ? 'Активируем…' : trialCta}
          </button>
        ) : (
          <button className="button button--primary" type="button" onClick={onOpenSubscription}>
            {manageSubscriptionCta}
          </button>
        )}
      </div>
    </section>
  );
}
