/**
 * Each vendor's brand colour (bw_brands.color), for the Market Monitor views.
 *
 * The colour says "which vendor" and nothing else: a dot beside the name, or
 * the fill of a mark in a chart where each mark is one vendor. Text keeps its
 * normal colour. A vendor with no colour set renders exactly as before, so
 * every caller keeps its old colour as the fallback.
 *
 * Many components on one page want the same map, so the vendor list is
 * fetched once per market and shared through a module-level cache.
 */

import { useEffect, useMemo, useState } from 'react';
import { getVendors, type Vendor } from '../../services/marketMonitorApi';

export interface VendorColours {
  byId: (brandId?: number | null) => string | undefined;
  byName: (name?: string | null) => string | undefined;
}

const cache = new Map<number, Promise<Vendor[]>>();

function load(marketId: number): Promise<Vendor[]> {
  let p = cache.get(marketId);
  if (!p) {
    // A failed load is dropped from the cache so a later mount can retry;
    // until then every vendor simply has no colour.
    p = getVendors(marketId).catch(() => {
      cache.delete(marketId);
      return [] as Vendor[];
    });
    cache.set(marketId, p);
  }
  return p;
}

const key = (name?: string | null) => (name || '').trim().toLowerCase();

/** Lookups over a vendor list, for a component that already holds one. */
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

export function useVendorColours(marketId?: number | null): VendorColours {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  useEffect(() => {
    if (!marketId) { setVendors([]); return; }
    let live = true;
    load(marketId).then((v) => { if (live) setVendors(v); });
    return () => { live = false; };
  }, [marketId]);
  return useMemo(() => vendorColoursFrom(vendors), [vendors]);
}

/** An 8px dot in the vendor's colour; nothing when there is none. */
export function VendorSwatch({ color, className = '' }: {
  color?: string | null; className?: string;
}) {
  if (!color) return null;
  return (
    <span
      aria-hidden="true"
      className={`inline-block w-2 h-2 rounded-full shrink-0 align-middle ${className}`}
      style={{ backgroundColor: color }}
    />
  );
}
