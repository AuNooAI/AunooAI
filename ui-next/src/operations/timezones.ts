// IANA timezone helpers for the world clock settings.

export interface TimeZoneOption {
  timeZone: string;
  /** Last path segment, readable: "America/Argentina/Buenos_Aires" → "Buenos Aires". */
  city: string;
  /** First path segment, e.g. "America". Empty for zones like "UTC". */
  region: string;
}

export function cityFromTimeZone(timeZone: string) {
  return timeZone.split('/').pop()!.replace(/_/g, ' ');
}

export function isValidTimeZone(timeZone: unknown): timeZone is string {
  if (typeof timeZone !== 'string' || !timeZone) return false;
  try {
    new Intl.DateTimeFormat('en-US', { timeZone });
    return true;
  } catch {
    return false;
  }
}

/** Every zone the browser knows, sorted by region then city. */
export const TIME_ZONES: TimeZoneOption[] = Intl.supportedValuesOf('timeZone')
  .map((timeZone) => ({
    timeZone,
    city: cityFromTimeZone(timeZone),
    region: timeZone.includes('/') ? timeZone.split('/')[0] : '',
  }))
  .sort((a, b) => a.region.localeCompare(b.region) || a.city.localeCompare(b.city));

const byLowerCase = new Map(TIME_ZONES.map((option) => [option.timeZone.toLowerCase(), option.timeZone]));

/**
 * Turns typed text into a canonical zone id: exact ids in any case ("europe/london"), ids with
 * spaces ("America/New York"), or other names the browser accepts (aliases like "Asia/Calcutta").
 */
export function resolveTimeZone(input: string): string | null {
  const text = input.trim().replace(/ /g, '_');
  if (!text) return null;
  const known = byLowerCase.get(text.toLowerCase());
  if (known) return known;
  if (!isValidTimeZone(text)) return null;
  // Keep the name the user typed (the browser may report an older alias, e.g. Kolkata → Calcutta),
  // with each word capitalised: "asia/kolkata" → "Asia/Kolkata".
  return text.replace(/(^|[/_-])([a-z])/g, (_, sep: string, letter: string) => sep + letter.toUpperCase());
}

/** The zone the browser resolves a name to, so aliases compare equal (Asia/Kolkata = Asia/Calcutta). */
export function canonicalTimeZone(timeZone: string) {
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone }).resolvedOptions().timeZone;
  } catch {
    return timeZone;
  }
}

/** Case-insensitive match on city, region or id (spaces and underscores are interchangeable). */
export function matchesQuery(option: TimeZoneOption, query: string) {
  const q = query.trim().toLowerCase().replace(/_/g, ' ');
  if (!q) return true;
  return [option.city, option.region, option.timeZone.replace(/_/g, ' ')].some((text) => text.toLowerCase().includes(q));
}
