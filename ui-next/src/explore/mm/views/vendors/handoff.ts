/*
 * A filter another view hands to the vendor list, such as the Analysis formation chart's "vendors
 * founded in 2021". Call setFoundedFilter(year) before ctx.goTo('vendors'); the list picks it up once
 * and shows it as a removable chip, so a filtered table never looks wrong for no visible reason.
 */
const KEY = 'aunoo.mm.foundedFilter';

export function setFoundedFilter(year: string | number) {
  try {
    sessionStorage.setItem(KEY, String(year));
  } catch {
    // no storage: the list opens unfiltered
  }
}

export function takeFoundedFilter(): string {
  try {
    const v = sessionStorage.getItem(KEY) ?? '';
    sessionStorage.removeItem(KEY);
    return v;
  } catch {
    return '';
  }
}
