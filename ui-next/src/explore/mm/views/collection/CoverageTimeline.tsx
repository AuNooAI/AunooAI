import { useMemo, useState } from 'react';
import { Button, Stack, Text } from '@aunoo/ui';
import type { CorpusArticle } from '@monolith/marketMonitorApi';
import { Swimlane } from '../../../shared/Swimlane';
import type { VendorColours } from '../../shared/colours';
import { CLASS_LABEL } from './labels';

/*
 * Coverage on a timeline: one lane per vendor (an article counts under its first matched vendor),
 * the busiest twelve by default, as the old CoverageTimeline. Dots are sized by how many sources
 * carried the story; a dot opens the article. Undated articles can't be placed and are counted.
 */

const DEFAULT_LANES = 12;
const NO_VENDOR = 'No vendor matched';

export function CoverageTimeline({ articles, colours }: { articles: CorpusArticle[]; colours: VendorColours }) {
  const [showAll, setShowAll] = useState(false);
  const view = useMemo(() => {
    const counts = new Map<string, { n: number; id?: number }>();
    for (const a of articles) {
      const v = a.vendors[0];
      const key = v ? v.vendor : NO_VENDOR;
      const c = counts.get(key) ?? { n: 0, id: v?.brand_id };
      c.n += 1;
      counts.set(key, c);
    }
    const ranked = [...counts.entries()].sort((x, y) => y[1].n - x[1].n);
    const cap = showAll ? ranked.length : DEFAULT_LANES;
    const shown = ranked.slice(0, cap);
    const laneSet = new Set(shown.map(([name]) => name));
    const lanes = shown.map(([name, c]) => ({ id: name, label: `${name} (${c.n})`, color: colours.byId(c.id) }));
    let undated = 0;
    const items = [];
    for (const a of articles) {
      if (!a.published || Number.isNaN(new Date(a.published).getTime())) {
        undated += 1;
        continue;
      }
      const lane = a.vendors[0]?.vendor ?? NO_VENDOR;
      if (!laneSet.has(lane)) continue;
      items.push({
        id: a.uri,
        lane,
        date: a.published,
        label: `${a.title} (${CLASS_LABEL[a.article_class] ?? a.article_class}${a.news_source ? `, ${a.news_source}` : ''}${a.cluster ? `, ${a.cluster.size} sources` : ''})`,
        weight: a.cluster?.size ?? 1,
        onSelect: () => window.open(a.uri, '_blank', 'noopener,noreferrer'),
      });
    }
    const hiddenVendors = ranked.length - shown.length;
    const hiddenArticles = ranked.slice(cap).reduce((s, [, c]) => s + c.n, 0);
    return { lanes, items, undated, hiddenVendors, hiddenArticles, total: ranked.length };
  }, [articles, colours, showAll]);

  return (
    <Stack gap="sm">
      <Swimlane
        title="Matched coverage by vendor over time"
        lanes={view.lanes}
        items={view.items}
        emptyText="Nothing with a publication date to place on a timeline."
        caption="Each dot is one article, placed on its publication day in the lane of the first vendor it names. Bigger dots are stories more sources carried. Select a dot to open the article."
      />
      {(view.hiddenVendors > 0 || view.undated > 0) && (
        <Text variant="caption">
          {view.hiddenVendors > 0 ? `${view.hiddenArticles} articles from ${view.hiddenVendors} quieter vendors aren't shown. ` : ''}
          {view.undated > 0 ? `${view.undated} without a usable date are left out.` : ''}
        </Text>
      )}
      {view.total > DEFAULT_LANES && (
        <div>
          <Button variant="ghost" size="sm" onClick={() => setShowAll((s) => !s)}>{showAll ? 'Show the busiest twelve' : `Show all ${view.total} vendors`}</Button>
        </div>
      )}
    </Stack>
  );
}
