import { useEffect, useState } from 'react';
import { ImagePanel } from '../../common/ImagePanel';
import { Banner, DonutChart, EmptyState, Grid, Panel, Skeleton, Text, type ChartColor } from '@aunoo/ui';
import { getCategoriesData, getRegionsData, type CategoryData, type RegionData } from '@monolith/geopoliticalHotspotsApi';
import { errorText } from '../../../../shell';
import { BarList } from '../BarList';
import { cap } from '../labels';

/*
 * Hotspots by region and by threat category, as the old Regions tab. These figures cover every
 * hotspot on file: the server doesn't take a period for them, so the period picker doesn't apply.
 */

const SLOTS: ChartColor[] = [1, 2, 3, 4, 5];

export function Regions() {
  const [regions, setRegions] = useState<RegionData[] | null>(null);
  const [categories, setCategories] = useState<CategoryData[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([getRegionsData(), getCategoriesData()]).then(
      ([r, c]) => {
        if (!live) return;
        setRegions(r);
        setCategories(c);
      },
      (e) => live && setError(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, []);

  if (error) return <Banner tone="error" title="Regions didn’t load" description={error} />;
  if (!regions || !categories) return <Skeleton variant="block" size="card" />;
  if (!regions.length && !categories.length) {
    return <Panel title="Regions"><EmptyState icon="Globe" title="No regional figures yet">They appear once articles have been read and linked to hotspots.</EmptyState></Panel>;
  }

  const total = regions.reduce((s, r) => s + r.hotspot_count, 0);
  const sorted = [...regions].sort((a, b) => b.hotspot_count - a.hotspot_count);
  // Five named slices plus "Other", so the donut stays readable
  const slices = sorted.slice(0, 5).map((r, i) => ({ id: r.region, label: r.region, value: r.hotspot_count, color: SLOTS[i] }));
  const rest = sorted.slice(5).reduce((s, r) => s + r.hotspot_count, 0);
  if (rest > 0) slices.push({ id: 'other', label: 'Other regions', value: rest, color: 0 });
  const cats = [...categories].sort((a, b) => b.count - a.count);

  return (
    <>
      <Text variant="caption">All hotspots on file; the period picker doesn’t apply here.</Text>
      <Grid columns={2} gap="md">
        <ImagePanel filename="geohotspots-hotspots-by-region" title="Hotspots by region">
          <BarList rows={sorted.map((r) => ({ id: r.region, label: r.region, value: r.hotspot_count, valueText: `${r.hotspot_count} hotspots (${total ? ((r.hotspot_count / total) * 100).toFixed(1) : 0}%) · ${r.article_count} articles` }))} />
        </ImagePanel>
        <ImagePanel filename="geohotspots-share-of-hotspots-by-region" title="Share of hotspots by region">
          <DonutChart title="Share of hotspots by region" segments={slices} centerLabel={`${total} hotspots`} />
        </ImagePanel>
        <ImagePanel filename="geohotspots-hotspots-by-threat-category" title="Hotspots by threat category">
          <BarList rows={cats.map((c) => ({ id: c.category, label: cap(c.category), value: c.count, valueText: `${c.count} hotspots · ${c.total_articles} articles` }))} />
        </ImagePanel>
        <ImagePanel filename="geohotspots-average-intensity-by-category" title="Average intensity by category" description="Out of 100.">
          <BarList
            max={100}
            rows={[...categories].sort((a, b) => b.avg_intensity - a.avg_intensity).map((c) => ({
              id: c.category, label: cap(c.category), value: c.avg_intensity, valueText: c.avg_intensity.toFixed(1),
              tone: c.avg_intensity >= 60 ? 'error' : c.avg_intensity >= 40 ? 'warning' : 'neutral',
            }))}
          />
        </ImagePanel>
      </Grid>
    </>
  );
}
