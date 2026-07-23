import type React from 'react';
import { useMemo, useState } from 'react';
import {
  confirmAccountLinking,
  isApiError,
  startAccountLinking,
  storeAuthTokenFromResponse,
} from '../api/client';
import type { ApiId, LinkingConfirmResponse, LinkingStartResponse } from '../api/types';
import { toText } from '../utils/text';

type LinkingStep = 'question' | 'identifier' | 'code' | 'success';
type TextChangeEvent = { target?: { value?: string } | null; currentTarget?: { value?: string } | null } | null | undefined;

function readChangeValue(event: TextChangeEvent): string {
  return event?.currentTarget?.value ?? event?.target?.value ?? '';
}

interface AccountLinkingOnboardingProps {
  onDismiss: () => void;
  onLinked: () => Promise<void> | void;
}

function readChallengeId(response: LinkingStartResponse): ApiId | null {
  return response.challenge_id ?? response.challenge?.challenge_id ?? response.challenge?.id ?? null;
}

function readResponseCode(response: LinkingStartResponse): string {
  return toText(response.code) || toText(response.reason) || toText(response.status) || toText(response.result);
}

function getStartErrorMessage(response: LinkingStartResponse): string {
  const code = readResponseCode(response);

  if (code === 'not_found') {
    return 'Профиль с такими данными не найден. Проверьте телефон или e-mail.';
  }

  if (code === 'multiple_matches') {
    return 'Найдено несколько профилей. Напишите администратору.';
  }

  return 'Не удалось начать привязку. Проверьте телефон или e-mail и попробуйте ещё раз.';
}

function getSafeDetailText(detail: unknown): string {
  if (detail === undefined || detail === null) {
    return '';
  }

  return (toText(detail) || JSON.stringify(detail)).toLowerCase();
}

function getConfirmErrorMessage(error: unknown): string {
  const detail = isApiError(error) ? error.detail : undefined;
  const detailText = getSafeDetailText(detail);

  if (detailText.includes('temporary_profile_has_activity')) {
    return 'Этот Telegram-профиль уже использовался. Напишите администратору для объединения.';
  }

  if (detailText.includes('expired')) {
    return 'Срок действия кода истёк. Запросите новый код и попробуйте ещё раз.';
  }

  if (detailText.includes('invalid') || detailText.includes('code')) {
    return 'Неверный код. Проверьте код и попробуйте ещё раз.';
  }

  return 'Не удалось подтвердить привязку. Проверьте код и попробуйте ещё раз.';
}

function hasDevCode(response: LinkingStartResponse): boolean {
  return Boolean(import.meta.env.DEV && toText(response.dev_code));
}

export function AccountLinkingOnboarding({ onDismiss, onLinked }: AccountLinkingOnboardingProps) {
  const [step, setStep] = useState<LinkingStep>('question');
  const [identifier, setIdentifier] = useState('');
  const [code, setCode] = useState('');
  const [challengeId, setChallengeId] = useState<ApiId | null>(null);
  const [devCode, setDevCode] = useState('');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canSubmitIdentifier = useMemo(() => identifier.trim().length >= 3, [identifier]);
  const canSubmitCode = useMemo(() => code.trim().length > 0 && challengeId !== null, [code, challengeId]);

  async function submitIdentifier() {
    if (!canSubmitIdentifier || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setMessage('');

    try {
      const response = await startAccountLinking(identifier.trim());
      const nextChallengeId = readChallengeId(response);
      const responseCode = readResponseCode(response);

      if (!nextChallengeId || responseCode === 'not_found' || responseCode === 'multiple_matches') {
        setMessage(getStartErrorMessage(response));
        return;
      }

      setChallengeId(nextChallengeId);
      setDevCode(hasDevCode(response) ? toText(response.dev_code) : '');
      setStep('code');
    } catch (error) {
      if (isApiError(error)) {
        const detailText = getSafeDetailText(error.detail);
        if (detailText.includes('not_found')) {
          setMessage('Профиль с такими данными не найден. Проверьте телефон или e-mail.');
          return;
        }
        if (detailText.includes('multiple_matches')) {
          setMessage('Найдено несколько профилей. Напишите администратору.');
          return;
        }
      }
      setMessage('Не удалось начать привязку. Проверьте телефон или e-mail и попробуйте ещё раз.');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitCode() {
    if (!canSubmitCode || isSubmitting || challengeId === null) {
      return;
    }

    setIsSubmitting(true);
    setMessage('');

    try {
      const response: LinkingConfirmResponse = await confirmAccountLinking(challengeId, code.trim());
      storeAuthTokenFromResponse(response);
      await onLinked();
      setStep('success');
      setMessage('Профиль привязан');
    } catch (error) {
      setMessage(getConfirmErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="linking-modal" role="dialog" aria-modal="true" aria-labelledby="linking-title">
      <div className="linking-modal__card">
        {step === 'question' ? (
          <>
            <p className="eyebrow">Профиль</p>
            <h2 id="linking-title">Вы уже пользовались Bloom Club во ВКонтакте?</h2>
            <p>Мы можем привязать ваш Telegram к существующему профилю, чтобы сохранить доступ, тестовый период и привилегии.</p>
            <div className="linking-modal__actions">
              <button className="button button--primary" type="button" onClick={() => setStep('identifier')}>
                Да, привязать профиль
              </button>
              <button className="button button--ghost" type="button" onClick={onDismiss}>
                Нет, продолжить
              </button>
            </div>
          </>
        ) : null}

        {step === 'identifier' ? (
          <form
            className="linking-modal__form"
            onSubmit={(event: React.FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              void submitIdentifier();
            }}
          >
            <p className="eyebrow">Привязка</p>
            <h2 id="linking-title">Введите телефон или e-mail, который указывали в VK-приложении</h2>
            <input
              value={identifier}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) => setIdentifier(readChangeValue(event))}
              placeholder="Телефон или e-mail"
              autoComplete="email"
            />
            {message ? <p className="error-text">{message}</p> : null}
            <div className="linking-modal__actions">
              <button className="button button--primary" type="submit" disabled={!canSubmitIdentifier || isSubmitting}>
                Продолжить
              </button>
              <button className="button button--ghost" type="button" onClick={onDismiss}>
                Не сейчас
              </button>
            </div>
          </form>
        ) : null}

        {step === 'code' ? (
          <form
            className="linking-modal__form"
            onSubmit={(event: React.FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              void submitCode();
            }}
          >
            <p className="eyebrow">Подтверждение</p>
            <h2 id="linking-title">Введите код подтверждения</h2>
            <input value={code} onChange={(event: React.ChangeEvent<HTMLInputElement>) => setCode(readChangeValue(event))} placeholder="Код" inputMode="numeric" />
            {devCode ? <p className="success-text">Dev-код: {devCode}</p> : null}
            {message ? <p className="error-text">{message}</p> : null}
            <div className="linking-modal__actions">
              <button className="button button--primary" type="submit" disabled={!canSubmitCode || isSubmitting}>
                Подтвердить
              </button>
              <button className="button button--ghost" type="button" onClick={() => setStep('identifier')}>
                Назад
              </button>
            </div>
          </form>
        ) : null}

        {step === 'success' ? (
          <>
            <p className="eyebrow">Готово</p>
            <h2 id="linking-title">Профиль привязан</h2>
            <p className="success-text">{message || 'Профиль привязан'}</p>
            <button className="button button--primary" type="button" onClick={onDismiss}>
              Продолжить
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}
