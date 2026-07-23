import type { Partner } from '../api/types';
import { getPartnerCategories, sortPartnersForCatalog } from './partnerDisplay';

export function buildCatalogCategories(partners: Partner[] | null | undefined): string[] {
  const safePartners = sortPartnersForCatalog(partners);
  const categories = safePartners.flatMap(getPartnerCategories);
  return ['Все', ...Array.from(new Set(categories)).sort((a, b) => a.localeCompare(b, 'ru'))];
}

export function filterPartnersByCategory(partners: Partner[] | null | undefined, category: string): Partner[] {
  const safePartners = sortPartnersForCatalog(partners);
  if (category === 'Все') {
    return safePartners;
  }

  return safePartners.filter((partner) => getPartnerCategories(partner).includes(category));
}
