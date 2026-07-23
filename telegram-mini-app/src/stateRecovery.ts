const PROJECT_STORAGE_PREFIXES = [
  "bloom_club_tma_",
  "bloomClubTma",
  "bloom_tma_",
];

const STALE_STATE_KEY_PATTERNS = [
  /activeScreen/i,
  /selectedPartner/i,
  /selectedOffer/i,
  /verification/i,
  /partnerOffers/i,
  /offersStatus/i,
];

function shouldClearProjectKey(key: string): boolean {
  return (
    PROJECT_STORAGE_PREFIXES.some((prefix) => key.startsWith(prefix)) &&
    STALE_STATE_KEY_PATTERNS.some((pattern) => pattern.test(key))
  );
}

function clearMatchingKeys(storage: Storage): string[] {
  const removed: string[] = [];

  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index);

    if (key && shouldClearProjectKey(key)) {
      storage.removeItem(key);
      removed.push(key);
    }
  }

  return removed;
}

export function clearStaleAppState(): { localStorage: string[]; sessionStorage: string[] } {
  if (typeof window === "undefined") {
    return { localStorage: [], sessionStorage: [] };
  }

  return {
    localStorage: clearMatchingKeys(window.localStorage),
    sessionStorage: clearMatchingKeys(window.sessionStorage),
  };
}
