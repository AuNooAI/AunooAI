import { useCallback, useEffect, useMemo, useState } from 'react';
import { generateNarrative, getLatestNarrative, type BWSavedNarrative } from '@monolith/brandWatcherApi';
import { errorText } from '../../../../shell';
import { splitSections } from './shared';

/**
 * The brand's saved intelligence report (GET /narrative/latest). Writing a new one
 * (POST /generate-narrative) calls the AI, so it only runs from a button. The old page wrote one
 * by itself whenever a brand had none, on opening Brand analysis or Insights.
 */
export function useNarrative(brandId: number | null, brandName: string | undefined, daysBack: number, notify: (m: string) => void) {
  const [narrative, setNarrative] = useState<BWSavedNarrative | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (!brandId) {
      setNarrative(null);
      return;
    }
    let stale = false;
    setLoading(true);
    getLatestNarrative(brandId)
      .then((n) => !stale && setNarrative(n), () => !stale && setNarrative(null))
      .finally(() => !stale && setLoading(false));
    return () => {
      stale = true;
    };
  }, [brandId]);

  const generate = useCallback(async () => {
    if (!brandId) return;
    setGenerating(true);
    try {
      const res = await generateNarrative({ brand_id: brandId, days_back: daysBack });
      setNarrative({
        id: 0, brand_id: brandId, brand_name: brandName ?? null, narrative: res.narrative, data_summary: res.data_summary,
        days_back: daysBack, date_range_start: res.data_summary.date_range?.start ?? null, date_range_end: res.data_summary.date_range?.end ?? null,
        generated_at: res.generated_at,
      });
      notify('Brand report written');
    } catch (e) {
      notify(`The report wasn’t written: ${errorText(e)}`);
    } finally {
      setGenerating(false);
    }
  }, [brandId, brandName, daysBack, notify]);

  const sections = useMemo(() => splitSections(narrative?.narrative ?? ''), [narrative]);
  return { narrative, sections, loading, generating, generate };
}
