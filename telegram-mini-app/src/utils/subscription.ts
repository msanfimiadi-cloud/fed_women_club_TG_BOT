import type { ClientProfile, Subscription, TrialEligibility } from '../api/types';
import { toText } from './text';

const ACTIVE_STATUSES = new Set(['active', 'trial', 'trialing', 'trial_active']);
const END_DATE_FIELDS = ['expires_at', 'end_date', 'subscription_until', 'ends_at', 'paid_until', 'active_until'] as const;

function getDateTime(value: unknown): number | null {
  const text = toText(value);

  if (!text) {
    return null;
  }

  const timestamp = new Date(text).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

export function getSubscriptionEnd(subscription: Subscription | null | undefined): unknown {
  if (!subscription || typeof subscription !== 'object') {
    return undefined;
  }

  const source = subscription as Subscription & Record<string, unknown>;
  return END_DATE_FIELDS.map((field) => source[field]).find((value) => getDateTime(value) !== null || Boolean(toText(value)));
}

export function isSubscriptionActive(subscription: Subscription | null | undefined, now = new Date()): boolean {
  if (!subscription || typeof subscription !== 'object') {
    return false;
  }

  const source = subscription as Subscription & Record<string, unknown>;
  const endTimestamp = getDateTime(getSubscriptionEnd(subscription));
  const hasFutureEnd = endTimestamp !== null && endTimestamp > now.getTime();
  const isFlagActive = source.is_active === true || source.active === true;
  const status = toText(source.status).toLowerCase();
  const isStatusActive = ACTIVE_STATUSES.has(status);

  if (isStatusActive) {
    return endTimestamp === null || hasFutureEnd;
  }

  if (isFlagActive) {
    return endTimestamp === null || hasFutureEnd;
  }

  return hasFutureEnd;
}

function hasBooleanFlag(flag: boolean, ...values: unknown[]): boolean {
  return values.some((value) => value === flag);
}

function readNestedBoolean(source: unknown, path: string): boolean | undefined {
  if (!source || typeof source !== 'object') {
    return undefined;
  }
  const value = path.split('.').reduce<unknown>((current, key) => {
    return current && typeof current === 'object' ? (current as Record<string, unknown>)[key] : undefined;
  }, source);
  return typeof value === 'boolean' ? value : undefined;
}

export function getTrialEligibility(
  profile: ClientProfile | null | undefined,
  subscription: Subscription | null | undefined,
  now = new Date(),
): TrialEligibility {
  const hasActiveSubscription = isSubscriptionActive(subscription, now);
  const profileSource = (profile || {}) as Record<string, unknown>;
  const subscriptionSource = (subscription || {}) as Record<string, unknown>;
  const trialUsed = hasBooleanFlag(
    true,
    profile?.trial_used,
    subscription?.trial_used,
    readNestedBoolean(profileSource, 'trial.used'),
    readNestedBoolean(subscriptionSource, 'trial.used'),
  );
  const explicitlyUnavailable = hasBooleanFlag(
    false,
    profile?.trial_available,
    subscription?.trial_available,
    readNestedBoolean(profileSource, 'trial.available'),
    readNestedBoolean(subscriptionSource, 'trial.available'),
  );
  const trialAvailable = hasBooleanFlag(
    true,
    profile?.trial_available,
    subscription?.trial_available,
    readNestedBoolean(profileSource, 'trial.available'),
    readNestedBoolean(subscriptionSource, 'trial.available'),
  ) && !explicitlyUnavailable;

  return {
    canUseTrial: !hasActiveSubscription && !trialUsed && trialAvailable,
    trialUsed,
    hasActiveSubscription,
    trialAvailable,
  };
}

export function isTrialEligible(
  profile: ClientProfile | null | undefined,
  subscription: Subscription | null | undefined,
  now = new Date(),
): boolean {
  return getTrialEligibility(profile, subscription, now).canUseTrial;
}
