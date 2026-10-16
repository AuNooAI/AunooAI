import { useCallback, useEffect, useMemo, useState } from 'react';
import { Banner, Button, EmptyState, FilterChipRow, Grid, Icon, IconButton, Menu, Panel, SegmentedControl, Skeleton, Stack, Stat, Text } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { getAvailableModels, type AIModel } from '@monolith/api';
import { errorText } from '../../shell';
import { askAuspex, loadStarred, saveStarred } from '../feed/api';
import { ArticleSheet, type SheetTarget } from '../feed/ArticleSheet';
import { PromoteDialog, type PromoteArticle } from '../feed/PromoteDialog';
import { AddToBriefingDialog } from '../desk/AddToBriefingDialog';
import { EmergingTopicsConfigModal, loadEmergingTopicsConfig, type EmergingTopicsConfig } from './overlays/ConfigDialog';
import { EmergingTopicsScheduleModal } from './overlays/ScheduleDialog';
import { EmergingTopicsDashboard } from './signals';
import { TopicComparisonDashboard } from './visuals';
import * as et from './tab/api';
import { exportCsv, exportMarkdown, exportPdf } from './tab/exports';
import { ShareDialog } from '../shared/ShareDialog';
import { HighNovelty, HorizonsDialog, ProgressPanel, RetiredSection, TopicTable } from './tab/parts';
import { TopicCard } from './tab/TopicCard';
import { urgencyOf, type EmergingTopic, type HighNoveltyArticle, type HistoryPoint, type HorizonsResult, type TopicDetail } from './tab/types';
import { useDetection } from './tab/useDetection';

/*
 * Emerging Topics on the routes the old tab uses (/api/emerging-topics/*, see
 * ui/src/components/newsfeed/EmergingTopicsTab.tsx). Loading reads the stored themes, their score
 * history, the high-novelty articles and which themes are saved; detection and Future Horizons call
 * the AI and run only from their buttons.
 */

export interface EmergingTopicsProps {
  /** The single topic picked in the filter bar, or undefined for all topics */
  topic?: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
}

type View = 'cards' | 'table' | 'signals';
const URGENCY_OPTIONS = [{ value: 'high', label: 'High urgency' }, { value: 'medium', label: 'Medium' }, { value: 'low', label: 'Low' }];
const VELOCITY_OPTIONS = [{ value: 'accelerating', label: 'Accelerating' }, { value: 'stable', label: 'Stable' }, { value: 'decelerating', label: 'Slowing' }];

/** The old signal dashboard's own topic shape, built from a theme */
const toSignal = (t: EmergingTopic, scope?: string) => ({
  id: t.id,
  name: t.topic_label,
  description: t.topic_description,
  topic_id: t.topic_id ?? null,
  article_count: t.article_count,
  composite_score: t.trend_score?.composite ?? Math.round((t.confidence_score || 0) * 100),
  confidence_score: t.confidence_score,
  velocity: t.velocity,
  detection_type: t.detection_type,
  keywords: t.representative_keywords || [],
  // The theme's own scope, else the picked topic, so the dashboard's category filter can match
  topic_filter: t.topic_filter ?? scope ?? null,
  first_detected_at: t.first_detection_date || t.detection_date || null,
  actors: t.actors || null,
  events: t.events ? {
    trigger_event: t.events.trigger_event || '',
    timeline: (t.events.timeline || []).map((i) => (typeof i === 'string' ? i : i.event || '')),
    current_status: t.events.current_status || '',
  } : null,
  implications: t.implications || null,
  signals: t.signals || null,
  synthesis: t.synthesis || null,
  trend_score: t.trend_score ? {
    volume: t.trend_score.volume || 0, velocity: t.trend_score.velocity || 0, diversity: t.trend_score.diversity || 0,
    novelty: t.trend_score.novelty || 0, composite: t.trend_score.composite || 0,
  } : null,
  detection_count: t.detection_count ?? null,
  consecutive_detections: t.consecutive_detections ?? null,
  missed_runs: t.missed_runs ?? null,
  first_detection_date: t.first_detection_date || t.detection_date || null,
  last_detection_date: t.last_detection_date || null,
});

export function EmergingTopics({ topic, notify, askConfirm }: EmergingTopicsProps) {
  const [topics, setTopics] = useState<EmergingTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [novelty, setNovelty] = useState<HighNoveltyArticle[]>([]);
  const [tracked, setTracked] = useState<Set<number>>(new Set());
  const [histories, setHistories] = useState<Record<number, HistoryPoint[]>>({});
  const [details, setDetails] = useState<Record<number, TopicDetail>>({});
  const [openId, setOpenId] = useState<number | null>(null);
  const [view, setView] = useState<View>('cards');
  const [urgency, setUrgency] = useState<string[]>([]);
  const [velocity, setVelocity] = useState<string[]>([]);
  const [config, setConfig] = useState<EmergingTopicsConfig>(loadEmergingTopicsConfig);
  const [models, setModels] = useState<AIModel[]>([]);
  const [dialog, setDialog] = useState<null | 'config' | 'schedule'>(null);
  const [retiredOpen, setRetiredOpen] = useState(false);
  const [retired, setRetired] = useState<EmergingTopic[] | null>(null);
  const [retiredLoading, setRetiredLoading] = useState(false);
  const [horizons, setHorizons] = useState<{ topic: EmergingTopic; result: HorizonsResult | null } | null>(null);
  const [horizonsBusy, setHorizonsBusy] = useState<number | null>(null);
  const [toBriefing, setToBriefing] = useState<EmergingTopic | null>(null);
  const [savingHorizons, setSavingHorizons] = useState(false);
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [promote, setPromote] = useState<PromoteArticle | null>(null);
  const [starred, setStarred] = useState<string[]>(loadStarred);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    et.fetchTopics(topic).then(setTopics, (e) => setLoadError(errorText(e))).finally(() => setLoading(false));
    et.fetchHighNovelty(topic).then(setNovelty);
  }, [topic]);
  useEffect(() => {
    load();
    et.fetchTrackedIds().then(setTracked);
    setRetired(null);
    setDetails({});
  }, [load]);
  useEffect(() => {
    getAvailableModels().then(setModels, () => setModels([]));
  }, []);
  // The Explore filter bar's Refresh button
  useEffect(() => {
    window.addEventListener('explore:refresh', load);
    return () => window.removeEventListener('explore:refresh', load);
  }, [load]);
  // Each theme's score history, for its sparkline
  const ids = topics.map((t) => t.id).join(',');
  useEffect(() => {
    if (!ids) return;
    et.fetchHistories(ids.split(',').map(Number)).then(setHistories);
  }, [ids]);
  useEffect(() => {
    if (!retiredOpen || retired) return;
    setRetiredLoading(true);
    et.fetchRetired(topic).then(setRetired, (e) => { notify(`Retired themes didn’t load: ${errorText(e)}`); setRetired([]); }).finally(() => setRetiredLoading(false));
  }, [retiredOpen, retired, topic, notify]);

  const det = useDetection({ topic, onTopics: setTopics, onFinished: load });

  const loadDetail = (id: number) => {
    if (details[id]) return;
    et.fetchDetail(id).then((d) => setDetails((m) => ({ ...m, [id]: d })), (e) => setDetails((m) => ({ ...m, [id]: { error: errorText(e) } })));
  };
  const openCard = (t: EmergingTopic, scroll = false) => {
    setView('cards');
    setOpenId(t.id);
    loadDetail(t.id);
    if (scroll) setTimeout(() => document.getElementById(`topic-${t.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
  };

  const shown = useMemo(() => topics.filter((t) =>
    (!urgency.length || urgency.includes(urgencyOf(t))) && (!velocity.length || velocity.includes(t.velocity))), [topics, urgency, velocity]);

  // ── Actions ──
  const startDetection = () =>
    askConfirm({
      title: topic ? `Scan ${topic} for emerging themes?` : 'Scan every configured topic for emerging themes?',
      message: `The AI (${models.find((m) => m.id === config.model)?.name ?? config.model}) reads a sample of up to ${config.sampleSize} articles from the last ${config.daysBack} days${topic ? '' : ' for each topic'}, proposes themes, checks articles against them and writes a deep analysis of each. It runs on the server and can take several minutes. Change these settings under Detection settings.`,
      action: 'Start the scan',
      onConfirm: () => void det.run(config),
    });

  const retire = async (t: EmergingTopic) => {
    try {
      await et.retireTopic(t.id);
      setTopics((l) => l.filter((x) => x.id !== t.id));
      setRetired((r) => (r ? [{ ...t, status: 'retired' }, ...r] : r));
      notify(`Retired “${t.topic_label}”. It stays under Retired themes.`);
    } catch (e) {
      notify(`Not retired: ${errorText(e)}`);
    }
  };
  const restore = async (t: EmergingTopic) => {
    try {
      await et.restoreTopic(t.id);
      setRetired((r) => r && r.filter((x) => x.id !== t.id));
      setTopics((l) => [{ ...t, status: 'active' }, ...l]);
      notify(`Restored “${t.topic_label}”.`);
    } catch (e) {
      notify(`Not restored: ${errorText(e)}`);
    }
  };
  const remove = (t: EmergingTopic) =>
    askConfirm({
      title: `Delete “${t.topic_label}”?`,
      message: 'The theme is deleted for good, with its detection history. Retire it instead to keep it out of the list but be able to bring it back.',
      action: 'Delete',
      onConfirm: () => {
        et.deleteTopic(t.id).then(() => setTopics((l) => l.filter((x) => x.id !== t.id)), (e) => notify(`Not deleted: ${errorText(e)}`));
      },
    });
  const clearAll = () =>
    askConfirm({
      title: 'Clear all detected themes?',
      message: `This deletes ${topics.length} detected themes${topic ? ` for ${topic}` : ''} from the database, and resets their detection counts and tracking history. They have to be detected again.`,
      action: 'Clear all themes',
      onConfirm: () => {
        et.clearTopics(topic).then(() => {
          setTopics([]);
          setNovelty([]);
          setOpenId(null);
          setDetails({});
        }, (e) => notify(`Not cleared: ${errorText(e)}`));
      },
    });
  const toggleTrack = async (t: EmergingTopic) => {
    const on = !tracked.has(t.id);
    try {
      await et.setTracked(t.id, on);
      setTracked((s) => { const n = new Set(s); if (on) n.add(t.id); else n.delete(t.id); return n; });
      notify(on ? `Saved “${t.topic_label}”. It appears under Saved.` : `Stopped tracking “${t.topic_label}”.`);
    } catch (e) {
      notify(`Not changed: ${errorText(e)}`);
    }
  };

  // Ask Auspex with the theme's full context, its source articles included, as on the old page
  const auspex = async (t: EmergingTopic) => {
    let articles = details[t.id]?.articles ?? [];
    if (!articles.length) {
      try {
        const d = await et.fetchDetail(t.id);
        setDetails((m) => ({ ...m, [t.id]: d }));
        articles = d.articles ?? [];
      } catch {
        // asks without the articles
      }
    }
    const a = t.actors;
    const actors = [a?.companies?.length && `Companies: ${a.companies.join(', ')}`, a?.people?.length && `People: ${a.people.join(', ')}`, a?.organizations?.length && `Organizations: ${a.organizations.join(', ')}`].filter(Boolean);
    const parts = [
      `Analyze this emerging topic: "${t.topic_label}"`, '', `DESCRIPTION:\n${t.topic_description}`,
      t.why_emerging && `WHY EMERGING:\n${t.why_emerging}`,
      `METRICS:\n- Articles: ${t.article_count}\n- Velocity: ${t.velocity}\n- Detection Type: ${t.detection_type}${t.trend_score ? `\n- Trend Score: ${Math.round(t.trend_score.composite)}/100` : ''}`,
      t.representative_keywords?.length && `SEARCH KEYWORDS (use these to find related articles):\n${t.representative_keywords.slice(0, 10).join(', ')}`,
      t.key_themes?.length && `KEY THEMES:\n${t.key_themes.join(', ')}`,
      actors.length && `KEY ACTORS:\n${actors.join('\n')}`,
      t.events?.trigger_event && `TRIGGER EVENT:\n${t.events.trigger_event}`,
      t.synthesis?.key_takeaway && `KEY TAKEAWAY:\n${t.synthesis.key_takeaway}`,
      t.implications?.industry_impact && `INDUSTRY IMPACT:\n${t.implications.industry_impact}`,
      articles.length && `SOURCE ARTICLES (${articles.length} articles analyzed):\n${articles.slice(0, 10).map((x, i) =>
        `${i + 1}. "${x.title}"\n   Source: ${x.news_source || 'Unknown'}\n   Date: ${x.publication_date || 'Unknown'}\n   URI: ${x.uri}${x.summary ? `\n   Summary: ${x.summary.slice(0, 300)}...` : ''}`).join('\n')}`,
      'Please provide:\n1. Deep analysis of this emerging trend (use the source articles above for context)\n2. Potential implications for our organization\n3. Key developments to monitor\n4. Recommended actions or responses\n5. Related trends or connections to explore',
    ].filter(Boolean);
    askAuspex(parts.join('\n\n'), topic || 'All');
  };

  /** Calls the AI */
  const runHorizons = async (t: EmergingTopic) => {
    setHorizonsBusy(t.id);
    setHorizons({ topic: t, result: null });
    try {
      const result = await et.runHorizons(t.id, config.model);
      setHorizons({ topic: t, result });
    } catch (e) {
      setHorizons(null);
      notify(`Future Horizons failed: ${errorText(e)}`);
    } finally {
      setHorizonsBusy(null);
    }
  };
  const saveHorizons = async () => {
    if (!horizons?.result) return;
    setSavingHorizons(true);
    try {
      await et.saveHorizons(horizons.topic.id, horizons.result);
      const { id } = horizons.topic;
      const result = horizons.result;
      setTopics((l) => l.map((x) => (x.id === id ? { ...x, future_horizons: result } : x)));
      setHorizons(null);
      notify('Scenarios saved to the theme.');
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    } finally {
      setSavingHorizons(false);
    }
  };

  const openArticle = (uri: string, title?: string) => setSheet({ article: { uri, title } });

  // The briefing keeps the theme's source articles; the old page never loaded them, so it sent none
  // Share by email sends the theme with up to 10 of its articles, so the detail is read first
  const [toShare, setToShare] = useState<EmergingTopic | null>(null);
  const shareTheme = async (t: EmergingTopic) => {
    if (!details[t.id]) {
      try {
        const d = await et.fetchDetail(t.id);
        setDetails((m) => ({ ...m, [t.id]: d }));
      } catch {
        // shared without its articles
      }
    }
    setToShare(t);
  };
  const sharePayload = (t: EmergingTopic): Record<string, unknown> => ({
    topic_id: t.id,
    topic_label: t.topic_label,
    topic_description: t.topic_description,
    score: t.trend_score?.composite ?? (t.confidence_score != null ? Math.round(t.confidence_score * 100) : undefined),
    urgency: t.synthesis?.urgency,
    velocity: t.velocity,
    article_count: t.article_count,
    key_themes: t.key_themes,
    key_entities: t.key_entities,
    why_emerging: t.why_emerging,
    key_takeaway: t.synthesis?.key_takeaway,
    trend_score: t.trend_score,
    actors: t.actors,
    events: t.events,
    implications: t.implications,
    articles: (details[t.id]?.articles ?? []).slice(0, 10).map((a) => ({ title: a.title, news_source: a.news_source, publication_date: a.publication_date, uri: a.uri })),
  });
  const addToBriefing = async (t: EmergingTopic) => {
    if (!details[t.id]) {
      try {
        const d = await et.fetchDetail(t.id);
        setDetails((m) => ({ ...m, [t.id]: d }));
      } catch {
        // added without its source articles
      }
    }
    setToBriefing(t);
  };
  const briefingItem = (t: EmergingTopic) => ({
    name: t.topic_label,
    summary: t.why_emerging || t.topic_description,
    description: t.topic_description,
    why_emerging: t.why_emerging,
    key_takeaway: t.synthesis?.key_takeaway,
    article_count: t.article_count,
    velocity: t.velocity,
    trend_score: t.trend_score as Record<string, unknown> | undefined,
    key_entities: t.key_entities,
    representative_keywords: t.representative_keywords,
    key_themes: t.key_themes,
    topic: t.topic_filter || topic,
    implications: t.implications as Record<string, unknown> | undefined,
    organization_implications: t.organization_implications as Record<string, unknown> | undefined,
    signals: t.signals as Record<string, unknown> | undefined,
    actors: t.actors as Record<string, unknown> | undefined,
    events: t.events as Record<string, unknown> | undefined,
    source_articles: (details[t.id]?.articles ?? []).slice(0, 10).map((a) => ({
      title: a.title || a.uri, url: a.uri, source: a.news_source, date: a.publication_date, summary: a.summary,
    })),
  });
  const toggleStar = (uri: string) =>
    setStarred((s) => {
      const next = s.includes(uri) ? s.filter((u) => u !== uri) : [...s, uri];
      saveStarred(next);
      return next;
    });

  const count = (v: string) => topics.filter((t) => t.velocity === v).length;

  return (
    <>
      <Panel
        title="Emerging themes"
        description={`New and growing developments found in the article collection${topic ? ` for ${topic}` : ' across all topics'}.`}
        headerAside={
          <Stack direction="row" gap="sm">
            <IconButton icon={<Icon name="Clock" size="sm" />} label="Schedule automatic detection" disabled={det.detecting} onClick={() => setDialog('schedule')} />
            <IconButton icon={<Icon name="SlidersHorizontal" size="sm" />} label="Detection settings" disabled={det.detecting} onClick={() => setDialog('config')} />
            {topics.length > 0 && (
              <Menu
                label="Export the themes"
                align="end"
                trigger={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Export the themes" disabled={det.detecting} />}
                items={[{ id: 'md', label: 'Markdown', icon: 'FileText' }, { id: 'pdf', label: 'PDF', icon: 'FileText' }, { id: 'csv', label: 'CSV', icon: 'Table' }]}
                onSelect={(id) => {
                  if (id === 'md') exportMarkdown(topics, topic);
                  else if (id === 'csv') exportCsv(topics);
                  else exportPdf(topics, topic).catch((e) => notify(`PDF not made: ${errorText(e)}`));
                }}
              />
            )}
            {(topics.length > 0 || novelty.length > 0) && (
              <IconButton icon={<Icon name="Trash" size="sm" />} tone="danger" label="Clear all detected themes" disabled={det.detecting} onClick={clearAll} />
            )}
            <Button iconStart={<Icon name="Play" size="sm" />} disabled={det.detecting} onClick={startDetection}>
              {det.detecting ? 'Scanning…' : topic ? `Scan ${topic}` : 'Scan all topics'}
            </Button>
          </Stack>
        }
      />

      {det.detecting && det.progress && <ProgressPanel p={det.progress} />}
      {det.error && <Banner tone="error" title="Detection failed" description={det.error} action={<Button variant="secondary" size="sm" onClick={() => det.setError(null)}>Dismiss</Button>} />}
      {loadError && <Banner tone="error" title="The themes didn’t load" description={loadError} action={<Button variant="secondary" size="sm" onClick={load}>Try again</Button>} />}

      {!loading && topics.length > 0 && (
        <Grid columns={4} stackAt="small">
          <Stat label="Themes" value={topics.length} meta={`${topics.reduce((s, t) => s + t.article_count, 0)} articles behind them`} />
          <Stat label="Accelerating" value={count('accelerating')} tone="success" />
          <Stat label="Stable" value={count('stable')} />
          <Stat label="Slowing" value={count('decelerating')} tone="warning" />
        </Grid>
      )}

      {topics.length >= 2 && (
        <TopicComparisonDashboard
          topics={topics as unknown as Parameters<typeof TopicComparisonDashboard>[0]['topics']}
          onTopicClick={(c) => { const t = topics.find((x) => x.id === (c as { id: number }).id); if (t) openCard(t, true); }}
        />
      )}

      <Panel
        title="Trending themes"
        headerAside={
          <SegmentedControl
            label="Show the themes as"
            value={view}
            onValueChange={(v) => setView(v as View)}
            options={[{ value: 'cards', label: 'Cards', icon: 'SquaresFour' }, { value: 'table', label: 'Table', icon: 'Table' }, { value: 'signals', label: 'Signal dashboard', icon: 'Target' }]}
          />
        }
      >
        <Stack gap="md">
          {!loading && topics.length > 0 && (
            <Stack direction="row" gap="md">
              <FilterChipRow label="Urgency" options={URGENCY_OPTIONS.map((o) => ({ ...o, count: topics.filter((t) => urgencyOf(t) === o.value).length }))} selected={urgency} onChange={setUrgency} allLabel="Any urgency" />
              <FilterChipRow label="Velocity" options={VELOCITY_OPTIONS.map((o) => ({ ...o, count: count(o.value) }))} selected={velocity} onChange={setVelocity} allLabel="Any velocity" />
            </Stack>
          )}
          {loading ? <Skeleton variant="block" size="card" /> : topics.length === 0 ? (
            <EmptyState icon="Sparkle" title="No trending themes detected">Run a scan to find new and growing developments.</EmptyState>
          ) : shown.length === 0 ? (
            <EmptyState icon="Funnel" title="No themes match these filters" action={<Button variant="secondary" size="sm" onClick={() => { setUrgency([]); setVelocity([]); }}>Clear the filters</Button>}>
              Try fewer filters.
            </EmptyState>
          ) : view === 'signals' ? (
            // The old page passed every theme here, ignoring the filters above; it now gets the filtered list
            <EmergingTopicsDashboard topics={shown.map((t) => toSignal(t, topic)) as unknown as Parameters<typeof EmergingTopicsDashboard>[0]['topics']} />
          ) : view === 'table' ? (
            <TopicTable topics={shown} onOpen={(t) => openCard(t, true)} onAuspex={(t) => void auspex(t)} onRetire={(t) => void retire(t)} onDelete={remove} />
          ) : (
            <Grid columns={2} stackAt="wide">
              {shown.map((t) => (
                <TopicCard
                  key={t.id}
                  t={t}
                  open={openId === t.id}
                  onOpenChange={(o) => { if (o) openCard(t); else setOpenId(null); }}
                  detail={details[t.id]}
                  history={histories[t.id]}
                  tracked={tracked.has(t.id)}
                  horizonsBusy={horizonsBusy === t.id}
                  onTrack={() => void toggleTrack(t)}
                  onAuspex={() => void auspex(t)}
                  onHorizons={() => void runHorizons(t)}
                  onRetire={() => void retire(t)}
                  onDelete={() => remove(t)}
                  onAddToBriefing={() => void addToBriefing(t)}
                  onShare={() => void shareTheme(t)}
                  onArticle={openArticle}
                />
              ))}
            </Grid>
          )}
        </Stack>
      </Panel>

      <RetiredSection open={retiredOpen} onOpenChange={setRetiredOpen} topics={retired} loading={retiredLoading} onRestore={(t) => void restore(t)} />
      <HighNovelty articles={novelty} onArticle={openArticle} />
      <Text variant="caption">Detection, analysis and Future Horizons are written by AI from collected articles and may contain errors.</Text>

      <EmergingTopicsConfigModal open={dialog === 'config'} onClose={() => setDialog(null)} config={config} onSave={setConfig} availableModels={models} />
      <EmergingTopicsScheduleModal open={dialog === 'schedule'} onClose={() => setDialog(null)} />
      <HorizonsDialog
        open={!!horizons}
        onOpenChange={(o) => !o && setHorizons(null)}
        label={horizons?.topic.topic_label ?? ''}
        result={horizons?.result ?? null}
        busy={horizonsBusy !== null}
        saving={savingHorizons}
        onRegenerate={() => horizons && void runHorizons(horizons.topic)}
        onSave={() => void saveHorizons()}
      />
      <ArticleSheet target={sheet} onClose={() => setSheet(null)} onOpenRelated={(uri) => setSheet({ article: { uri } })} starred={starred} onToggleStar={toggleStar} onPromote={setPromote} notify={notify} />
      <PromoteDialog article={promote} onOpenChange={(o) => !o && setPromote(null)} onDone={() => undefined} notify={notify} />
      {toBriefing && (
        <AddToBriefingDialog open onClose={() => setToBriefing(null)} itemType="emerging_topic" emergingTopic={briefingItem(toBriefing)} notify={notify} />
      )}
      {toShare && (
        <ShareDialog open onOpenChange={(o) => !o && setToShare(null)} kind="emerging-topic" title={toShare.topic_label} payload={sharePayload(toShare)} notify={notify} />
      )}
    </>
  );
}
