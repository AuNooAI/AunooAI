import { useEffect, useMemo, useState } from 'react';
import { getVendors, type Vendor } from '@monolith/marketMonitorApi';

/*
 * Each vendor's brand colour (bw_brands.color), as the old vendorColours.tsx. The colour only says
 * "which vendor": a dot beside the name, or a mark's fill where each mark is one vendor. A vendor with
 * no colour set gets none.
 */

export interface VendorColours {
  byId: (brandId?: number | null) => string | undefined;
  byName: (name?: string | null) => string | undefined;
}

const cache = new Map<number, Promise<Vendor[]>>();
const key = (name?: string | null) => (name || '').trim().toLowerCase();

export function vendorColoursFrom(vendors: Vendor[] | null | undefined): VendorColours {
  const ids = new Map<number, string>();
  const names = new Map<string, string>();
  for (const v of vendors || []) {
    if (!v.color) continue;
    ids.set(v.brand_id, v.color);
    names.set(key(v.display_name), v.color);
  }
  return {
    byId: (id) => (id == null ? undefined : ids.get(id)),
    byName: (name) => (name ? names.get(key(name)) : undefined),
  };
}

/** For a component outside the frame (the vendor list is fetched once per market) */
export function useVendorColours(marketId?: number | null): VendorColours {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  useEffect(() => {
    if (!marketId) return;
    let live = true;
    let p = cache.get(marketId);
    if (!p) {
      p = getVendors(marketId).catch(() => {
        cache.delete(marketId);
        return [] as Vendor[];
      });
      cache.set(marketId, p);
    }
    p.then((v) => live && setVendors(v));
    return () => {
      live = false;
    };
  }, [marketId]);
  return useMemo(() => vendorColoursFrom(vendors), [vendors]);
}

/** An 8px dot in the vendor's colour; nothing when there is none. */
export function VendorSwatch({ color }: { color?: string | null }) {
  if (!color) return null;
  return (
    <span
      aria-hidden="true"
      style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: color, marginInlineEnd: 6, verticalAlign: 'middle', flexShrink: 0 }}
    />
  );
}
