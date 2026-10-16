import { useCallback, useEffect, useRef, useState } from 'react';
import { Banner, Button, Chip, Dialog, EmptyState, Grid, Icon, Meter, Select, Skeleton, Stack, Stat, Text } from '@aunoo/ui';
import { getTriageArticles, type TriageArticle } from '@monolith/trainingApi';
import { api, errorText } from '../../shell';
import { fmt } from '../lib';
import { FEEDBACK_GOAL } from '../useTraining';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Feedback recorded so far (all sessions), for the progress bar. */
  startTotal: number;
  /** Shown when the goal is reached. */
  onTrain: () => void;
  /** Reload the tab's stats when the dialog closes. */
  onClosed: () => void;
}

const BATCH = 50;
/** Load the next batch when this few cards are left. */
const PREFETCH_AT = 10;
const ALL = '__all__';

type Verdict = 'more' | 'less' | 'skip';

const tagsOf = (raw: string | null) => {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    if (Array.isArray(v)) return v.map(String);
  } catch {
    // comma-separated
  }
  return raw.split(',').map((s) => s.trim()).filter(Boolean);
};

/**
 * Relevance Triage: label scored articles "Relevant" / "Not relevant" for the relevance model
 * (POST /api/article-preference). Keys: → relevant, ← not relevant, S skip.
 */
export function RelevanceTriageDialog({ open, onOpenChange, startTotal, onTrain, onClosed }: Props) {
  const [topic, setTopic] = useState(ALL);
  const [topics, setTopics] = useState<string[]>([]);
  const [queue, setQueue] = useState<TriageArticle[]>([]);
  const [index, setIndex] = useState(0);
  const [available, setAvailable] = useState(0);
  const [exhausted, setExhausted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState({ more: 0, less: 0, skip: 0 });
  const offset = useRef(0);
  const sending = useRef(false);

  const loadBatch = useCallback(async (t: string, reset: boolean) => {
    setLoading(true);
    setError(null);
    try {
      if (reset) offset.current = 0;
      const r = await getTriageArticles({ topic: t === ALL ? undefined : t, limit: BATCH, offset: offset.current });
      offset.current += r.articles.length;
      setTopics(r.available_topics ?? []);
      setAvailable(r.total_available ?? 0);
      setExhausted(r.articles.length < BATCH);
      setQueue((q) => (reset ? r.articles : [...q, ...r.articles]));
      if (reset) setIndex(0);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      setSession({ more: 0, less: 0, skip: 0 });
      void loadBatch(topic, true);
    }
  }, [open, topic, loadBatch]);

  const current = queue[index];
  const total = startTotal + session.more + session.less;
  const reached = total >= FEEDBACK_GOAL;

  const decide = useCallback(
    async (v: Verdict) => {
      if (!current || sending.current) return;
      if (v !== 'skip') {
        sending.current = true;
        try {
          await api('/api/article-preference', { method: 'POST', json: { uri: current.uri, preference: v } });
        } catch (e) {
          setError(`Not saved: ${errorText(e)}`);
          sending.current = false;
          return;
        }
        sending.current = false;
      }
      setSession((s) => ({ ...s, [v]: s[v] + 1 }));
      setIndex((i) => i + 1);
      if (!exhausted && !loading && queue.length - (index + 1) <= PREFETCH_AT) void loadBatch(topic, false);
    },
    [current, exhausted, loading, queue.length, index, topic, loadBatch],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.closest('input, textarea, select, [role="combobox"], [role="listbox"]'))) return;
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        void decide('more');
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        void decide('less');
      } else if (e.key === 's' || e.key === 'S') {
        e.preventDefault();
        void decide('skip');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, decide]);

  const change = (o: boolean) => {
    onOpenChange(o);
    if (!o) onClosed();
  };

  const tags = current ? tagsOf(current.tags).slice(0, 5) : [];

  return (
    <Dialog
      open={open}
      onOpenChange={change}
      title="Relevance Triage"
      description="Tell the relevance model which articles belong in their topic. → relevant · ← not relevant · S skip"
      size="xl"
      footer={
        current && (
          <>
            <Button variant="secondary" size="lg" iconStart={<Icon name="X" size="sm" />} onClick={() => void decide('less')}>Not Relevant</Button>
            <Button variant="ghost" size="lg" onClick={() => void decide('skip')}>Skip</Button>
            <Button size="lg" iconStart={<Icon name="Check" size="sm" />} onClick={() => void decide('more')}>Relevant</Button>
          </>
        )
      }
    >
      <Stack gap="lg">
        <Grid columns={2} stackAt="small" gap="md">
          <Select
            label="Topic"
            fullWidth
            options={[{ value: ALL, label: 'All Topics' }, ...topics.map((t) => ({ value: t, label: t }))]}
            value={topic}
            onValueChange={setTopic}
          />
          <Stack gap="sm">
            <Meter
              label="Feedback toward training"
              progress
              value={Math.min(total, FEEDBACK_GOAL)}
              max={FEEDBACK_GOAL}
              valueText={`${fmt(total)} of ${fmt(FEEDBACK_GOAL)}`}
              tone={reached ? 'success' : 'neutral'}
            />
            <Text variant="hint">{fmt(available)} unreviewed</Text>
          </Stack>
        </Grid>
        <Grid columns={3} stackAt="never" gap="sm">
          <Stat size="compact" label="Relevant" value={fmt(session.more)} tone="success" />
          <Stat size="compact" label="Not relevant" value={fmt(session.less)} tone="error" />
          <Stat size="compact" label="Skipped" value={fmt(session.skip)} />
        </Grid>
        {error && (
          <Banner tone="error" icon="WarningCircle" title="Something went wrong" description={error} action={<Button variant="secondary" onClick={() => void loadBatch(topic, true)}>Retry</Button>} />
        )}
        {loading && !current ? (
          <Skeleton variant="block" />
        ) : current ? (
          <Stack gap="md">
            <Stack direction="row" gap="sm">
              {current.news_source && <Chip size="sm" tone="neutral">{current.news_source}</Chip>}
              {current.category && <Chip size="sm" tone="neutral">{current.category}</Chip>}
              {current.topic && <Chip size="sm" tone="accent">{current.topic}</Chip>}
              {current.publication_date && <Chip size="sm" tone="neutral">{current.publication_date.slice(0, 10)}</Chip>}
              {current.sentiment && <Chip size="sm" tone="neutral">{current.sentiment}</Chip>}
              {current.keyword_relevance_score != null && (
                <Chip size="sm" tone="info">Score {Math.round(current.keyword_relevance_score * 100)}%</Chip>
              )}
            </Stack>
            <Text variant="label">{current.title}</Text>
            <Text>{current.summary || 'No summary available.'}</Text>
            {tags.length > 0 && (
              <Stack direction="row" gap="sm">
                {tags.map((t) => <Chip key={t} size="sm" tone="muted">{t}</Chip>)}
              </Stack>
            )}
          </Stack>
        ) : reached ? (
          <EmptyState
            icon="CheckCircle"
            title="Goal reached"
            action={<Button iconStart={<Icon name="Brain" size="sm" />} onClick={() => { onTrain(); change(false); }}>Train Relevance Model</Button>}
          >
            There’s enough feedback to train the relevance model.
          </EmptyState>
        ) : (
          <EmptyState icon="Tray" title="No more articles to review">Try another topic, or come back after the next collection.</EmptyState>
        )}
      </Stack>
    </Dialog>
  );
}
