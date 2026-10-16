import { useEffect, useMemo, useState } from 'react';
import { Banner, Chip, EmptyState, LineChart, Panel, Skeleton, Stack, Text } from '@aunoo/ui';
import { errorText } from '../../../../shell';
import { getCampaigns, getDailyCounts, getTimeline, type Campaign, type DailyCount, type TimelinePoint } from '../api';
import type { ThreatCtx } from '../context';
import { fmtDate, fmtDay } from '../labels';
import { LinkButton } from '../parts';
import { CampaignDialog } from './CampaignDialog';

/*
 * Activity over time, as the old ThreatTimelineTab: campaigns on a shared date range, articles per day
 * with a seven-day average, average severity, and how many threats were active each day.
 */

/** A rounded top for a count axis, with four or five ticks */
function axis(max: number): { domain: [number, number]; ticks: number[] } {
  const top = max <= 5 ? 5 : Math.ceil(max / 5) * 5;
  const step = top / 5;
  return { domain: [0, top], ticks: Array.from({ length: 6 }, (_, i) => Math.round(i * step)) };
}

export function Timeline(ctx: ThreatCtx) {
  const [timeline, setTimeline] = useState<TimelinePoint[] | null>(null);
  const [daily, setDaily] = useState<DailyCount[] | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Campaign | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    Promise.all([getTimeline(ctx.daysBack), getDailyCounts(ctx.daysBack), getCampaigns()]).then(
      ([t, d, c]) => {
        if (!live) return;
        setTimeline(t);
        setDaily(d);
        setCampaigns(c.data);
      },
      (e) => live && setError(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, [ctx.daysBack]);

  const range = useMemo(() => {
    const dates = (campaigns ?? []).flatMap((c) => [c.start_date, c.end_date]).filter((d): d is string => !!d).map((d) => new Date(d).getTime());
    const min = dates.length ? Math.min(...dates) : Date.now() - 90 * 86400000;
    const max = Math.max(Date.now(), ...dates);
    return { min, span: max - min || 1 };
  }, [campaigns]);

  if (error) return <Banner tone="error" title="The timeline didn’t load" description={error} />;
  if (!timeline || !daily || !campaigns) return <Skeleton variant="block" size="card" />;

  const articleAxis = axis(Math.max(0, ...daily.map((d) => Math.max(d.article_count, d.rolling_avg))));
  const threatAxis = axis(Math.max(0, ...timeline.map((d) => d.threat_count)));
  const sorted = [...campaigns].sort((a, b) => (a.start_date ? new Date(a.start_date).getTime() : 0) - (b.start_date ? new Date(b.start_date).getTime() : 0));

  return (
    <>
      <Panel title="Campaigns" description="Coordinated runs of activity the AI grouped together, on one shared date range. A campaign with no end date is still running.">
        {!sorted.length ? <Text>No campaigns tracked yet. They appear when the AI links several threats to one operation.</Text> : (
          <ul className="threat-plainlist">
            {sorted.map((c) => {
              const start = c.start_date ? new Date(c.start_date).getTime() : range.min;
              const end = c.end_date ? new Date(c.end_date).getTime() : Date.now();
              const left = ((start - range.min) / range.span) * 100;
              const width = Math.max(((end - start) / range.span) * 100, 2);
              return (
                <li key={c.id}>
                  <Stack gap="sm">
                    <Stack direction="row" gap="sm">
                      <LinkButton onClick={() => setOpen(c)}>{c.name}</LinkButton>
                      {c.is_active && <Chip tone="error" size="sm">Active</Chip>}
                      <Text as="span" variant="caption">{`${fmtDate(c.start_date)} to ${c.end_date ? fmtDate(c.end_date) : 'now'} · ${c.threat_count} threats · ${c.article_count} articles`}</Text>
                    </Stack>
                    <div className="threat-span" aria-hidden="true">
                      <div className={`threat-span__bar${c.is_active ? ' threat-span__bar--active' : ''}`} style={{ left: `${left}%`, width: `${width}%` }} />
                    </div>
                  </Stack>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      {!daily.length && !timeline.length ? (
        <Panel title="Activity"><EmptyState icon="ChartLineUp" title="No activity in this period">No articles linked to threats were published in this period.</EmptyState></Panel>
      ) : (
        <>
          <Panel title="Articles about threats, by day" description="How many collected articles mentioned a tracked threat each day, with the seven-day average to smooth out busy days.">
            <LineChart
              title="Articles about threats per day"
              categories={daily.map((d) => d.date)}
              categoryLabels={daily.map((d) => fmtDay(d.date))}
              series={[
                { id: 'a', label: 'Articles', color: 1, values: daily.map((d) => d.article_count), fill: true },
                { id: 'r', label: 'Seven-day average', color: 2, dashed: true, values: daily.map((d) => Math.round(d.rolling_avg * 10) / 10) },
              ]}
              yDomain={articleAxis.domain}
              yTicks={articleAxis.ticks}
            />
          </Panel>
          <Panel title="Average severity, by day" description="The average severity score (0 to 100) of the threats mentioned each day. 80 and over counts as critical, 60 as high.">
            <LineChart
              title="Average severity per day"
              categories={timeline.map((d) => d.date)}
              categoryLabels={timeline.map((d) => fmtDay(d.date))}
              series={[{ id: 's', label: 'Average severity', color: 'negative', markers: true, values: timeline.map((d) => Math.round(d.avg_severity * 10) / 10) }]}
              yDomain={[0, 100]}
              yTicks={[0, 20, 40, 60, 80, 100]}
            />
          </Panel>
          <Panel title="Active threats, by day" description="How many distinct threats had coverage each day.">
            <LineChart
              title="Active threats per day"
              categories={timeline.map((d) => d.date)}
              categoryLabels={timeline.map((d) => fmtDay(d.date))}
              series={[{ id: 't', label: 'Threats', color: 3, fill: true, values: timeline.map((d) => d.threat_count) }]}
              yDomain={threatAxis.domain}
              yTicks={threatAxis.ticks}
            />
          </Panel>
        </>
      )}

      <CampaignDialog
        campaign={open}
        onClose={() => setOpen(null)}
        onArticles={(c) => {
          setOpen(null);
          ctx.showArticles({ campaign: { id: c.id, name: c.name } });
        }}
      />
    </>
  );
}
