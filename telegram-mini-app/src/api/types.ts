export type ApiId = string | number;
export type BackendText = string | number | null | Record<string, unknown> | unknown[];

export interface AuthResponse {
  token?: string;
  [key: string]: unknown;
  token_type?: string;
  expires_in?: number;
}

export interface ClientProfile {
  id?: ApiId;
  name?: BackendText;
  full_name?: BackendText;
  first_name?: BackendText;
  last_name?: BackendText;
  phone?: BackendText;
  email?: BackendText;
  city?: BackendText | City;
  city_id?: ApiId;
  avatar_url?: BackendText;
  telegram_user_id?: ApiId;
  telegram_first_name?: BackendText;
  telegram_last_name?: BackendText;
  user?: { full_name?: BackendText; name?: BackendText; first_name?: BackendText; last_name?: BackendText } | null;
  trial_available?: boolean;
  trial_used?: boolean;
  referral_code?: BackendText;
  referral_link?: BackendText;
  referrals_count?: number;
  referral_entries_count?: number;
  earned_giveaway_entries_count?: number;
}

export interface ClientProfilePatch {
  name?: string;
  full_name?: string;
  phone?: string;
  email?: string;
  contact_email?: string;
  city?: string;
  city_slug?: string;
  custom_city?: string;
  city_id?: ApiId;
}

export interface Subscription {
  id?: ApiId;
  status?: BackendText;
  active?: boolean;
  is_active?: boolean;
  starts_at?: BackendText;
  ends_at?: BackendText;
  end_date?: BackendText;
  paid_until?: BackendText;
  expires_at?: BackendText;
  active_until?: BackendText;
  subscription_until?: BackendText;
  trial_available?: boolean;
  trial_used?: boolean;
  price?: number;
}

export interface City {
  id?: ApiId;
  name?: BackendText;
  title?: BackendText;
  label?: BackendText;
  display_name?: BackendText;
  slug?: BackendText;
}

export interface PartnerPhoto {
  id?: ApiId;
  partner_id?: ApiId;
  image_url?: BackendText;
  photo_url?: BackendText;
  url?: BackendText;
  alt_text?: BackendText;
  sort_order?: string | number;
  is_active?: boolean;
  is_cover?: boolean;
}

export interface OfferPhoto {
  id?: ApiId;
  offer_id?: ApiId;
  image_url?: BackendText;
  photo_url?: BackendText;
  url?: BackendText;
  alt_text?: BackendText;
  sort_order?: string | number;
  is_active?: boolean;
}

export interface Partner {
  id: ApiId;
  partner_id?: ApiId;
  slug?: BackendText;
  display_name?: BackendText;
  title?: BackendText;
  name?: BackendText;
  legal_name?: BackendText;
  description?: BackendText;
  category?: BackendText;
  categories?: BackendText | BackendText[];
  city?: BackendText | City;
  address?: BackendText;
  phone?: BackendText;
  website?: BackendText;
  website_url?: BackendText;
  site?: BackendText;
  url?: BackendText;
  vk_url?: BackendText;
  telegram_url?: BackendText;
  whatsapp?: BackendText;
  working_hours?: BackendText;
  hours?: BackendText;
  coordinates?: BackendText;
  map_url?: BackendText;
  is_active?: boolean;
  verified?: boolean;
  sort_order?: string | number;
  phone_number?: BackendText;
  contact_phone?: BackendText;
  tel?: BackendText;
  contact?: { phone?: BackendText } | null;
  latitude?: number | string;
  longitude?: number | string;
  lat?: number | string;
  lon?: number | string;
  logo_url?: BackendText;
  image?: BackendText;
  photo?: BackendText;
  cover?: BackendText;
  photo_url?: BackendText;
  image_url?: BackendText;
  cover_url?: BackendText;
  avatar_url?: BackendText;
  photos?: Array<BackendText | PartnerPhoto | Record<string, unknown>> | null;
  images?: Array<BackendText | Record<string, unknown>> | null;
  gallery?: Array<BackendText | Record<string, unknown>> | null;
  media?: BackendText[] | Record<string, unknown> | null;
  offers?: Offer[] | null;
  discount?: BackendText;
  privilege?: BackendText;
  offer_preview?: BackendText;
  benefit?: BackendText;
  offer?: BackendText;
  offer_title?: BackendText;
  offer_description?: BackendText;
}

export interface Offer {
  id?: ApiId;
  partner_id?: ApiId;
  title?: BackendText;
  description?: BackendText;
  benefit_text?: BackendText;
  conditions?: BackendText;
  image_url?: BackendText;
  photo_url?: BackendText;
  photos?: Array<BackendText | OfferPhoto | Record<string, unknown>> | null;
  sort_order?: string | number;
  name?: BackendText;
  terms?: BackendText;
  value?: BackendText;
  discount?: BackendText;
  gift?: BackendText;
  benefit?: BackendText;
  base_price?: string | number;
  original_price?: string | number;
  regular_price?: string | number;
  price?: string | number;
  old_price?: string | number;
  club_price?: string | number;
  final_price?: string | number;
  discounted_price?: string | number;
  member_price?: string | number;
  price_with_discount?: string | number;
  discount_percent?: string | number;
  is_active?: boolean;
  saving?: string | number;
  saving_amount?: string | number;
  discount_amount?: string | number;
}

export interface Verification {
  id?: ApiId;
  partner_id?: ApiId;
  partner?: Partner | null;
  offer_id?: ApiId;
  offer?: Offer | null;
  code?: BackendText;
  display_code?: BackendText;
  token?: BackendText;
  status?: BackendText;
  expires_at?: BackendText;
  valid_until?: BackendText;
  created_at?: BackendText;
  base_price?: string | number;
  original_price?: string | number;
  price?: string | number;
  club_price?: string | number;
  final_price?: string | number;
  discounted_price?: string | number;
  member_price?: string | number;
  price_with_discount?: string | number;
  saving?: string | number;
  saving_amount?: string | number;
  discount_amount?: string | number;
}

export interface SavingsSummary {
  total?: number;
  amount?: number;
  currency?: BackendText;
  items?: SavingItem[] | null;
}

export interface SavingItem {
  id?: ApiId;
  partner?: Partner | null;
  partner_name?: BackendText;
  amount?: number;
  value?: number;
  created_at?: BackendText;
  description?: BackendText;
}

export interface PaymentRequest {
  id: ApiId;
  status?: BackendText;
  amount?: number;
  payment_url?: BackendText;
  created_at?: BackendText;
}

export interface LinkingStatus {
  linked?: boolean;
  is_linked?: boolean;
  has_linked_account?: boolean;
  needs_linking?: boolean;
  status?: BackendText;
  provider?: BackendText;
  linked_profile_id?: ApiId | null;
}

export interface TrialEligibility {
  canUseTrial: boolean;
  trialUsed: boolean;
  hasActiveSubscription: boolean;
  trialAvailable: boolean;
}

export interface ReferralSummary {
  referral_code?: BackendText;
  referral_link?: BackendText;
  invited_count?: number;
  referrals_count?: number;
  pending_referrals_count?: number;
  activated_referrals_count?: number;
  earned_entries_count?: number;
  earned_giveaway_entries_count?: number;
  reward_entries_count?: number;
  reward_entries_per_referral?: number;
}

export interface GiveawayEntry {
  id?: ApiId;
  user_id?: ApiId;
  client_id?: ApiId;
  giveaway_id?: ApiId;
  source?: BackendText;
  entries_count?: number;
  created_at?: BackendText;
  related_referral_id?: ApiId | null;
}

export interface LinkingStartResponse {
  status?: BackendText;
  result?: BackendText;
  detail?: unknown;
  error?: unknown;
  code?: BackendText;
  reason?: BackendText;
  challenge_id?: ApiId;
  challenge?: { id?: ApiId; challenge_id?: ApiId } | null;
  dev_code?: BackendText;
  message?: BackendText;
}

export interface LinkingConfirmResponse extends AuthResponse {
  status?: BackendText;
  profile?: ClientProfile | null;
  client?: ClientProfile | null;
  subscription?: Subscription | null;
  detail?: unknown;
}
