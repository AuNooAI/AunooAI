import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Grid, Icon, Select, Slider, Stack, Switch, TextField } from '@aunoo/ui';
import { createRSSFeed, testRSSFeedUrl, updateRSSFeed, type RSSFeedCreate, type RSSFeedTestResult } from '@monolith/gatherApi';
import { errorText } from '../../shell';
import { FACTUAL_OPTIONS, UNIT_OPTIONS, type FactualReporting, type Feed, type IntervalUnit } from '../model';
import { rangeError } from '../lib';

export type FeedDraft = Pick<Feed, 'url' | 'name' | 'topic' | 'description' | 'interval' | 'unit' | 'active' | 'threshold' | 'factual'>;

const EMPTY: FeedDraft = { url: '', name: '', topic: '', description: '', interval: '60', unit: 'minutes', active: true, threshold: 0, factual: 'none' };

interface Props {
  /** `null` = closed · `'new'` = Add Feed · a feed = Edit */
  feed: Feed | 'new' | null;
  onClose: () => void;
  /** Topic names from /api/topics */
  topics: string[];
  /** After a successful create / update. */
  onSaved: (name: string, created: boolean) => void;
}

const toRequest = (d: FeedDraft): RSSFeedCreate => ({
  name: d.name.trim(),
  url: d.url.trim(),
  topic: d.topic,
  description: d.description.trim() || undefined,
  is_active: d.active,
  check_interval: Number(d.interval),
  interval_unit: d.unit,
  relevance_threshold: d.threshold,
  default_factual_reporting: d.factual === 'none' ? undefined : d.factual,
});

const isUrl = (v: string) => /^https?:\/\/\S+\.\S+/.test(v.trim());

export function FeedDialog({ feed, onClose, topics, onSaved }: Props) {
  const editing = feed !== null && feed !== 'new' ? feed : null;
  const [draft, setDraft] = useState<FeedDraft>(EMPTY);
  const [test, setTest] = useState<'idle' | 'testing' | RSSFeedTestResult>('idle');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (feed !== null) {
      setDraft(editing ? { ...editing } : { ...EMPTY, topic: topics[0] ?? '' });
      setTest('idle');
      setSaveError(null);
    }
  }, [feed]);

  const runTest = async () => {
    setTest('testing');
    try {
      const r = await testRSSFeedUrl(draft.url.trim());
      setTest(r);
      // Name the feed after its title when the name is still empty
      if (r.valid && r.title && !draft.name.trim()) set('name', r.title);
    } catch (e) {
      setTest({ valid: false, error: errorText(e) });
    }
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      if (editing) await updateRSSFeed(Number(editing.id), toRequest(draft));
      else await createRSSFeed(toRequest(draft));
      onSaved(draft.name.trim(), !editing);
      onClose();
    } catch (e) {
      setSaveError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const set = <K extends keyof FeedDraft>(key: K, value: FeedDraft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const intervalError = rangeError(draft.interval, 1, 9999);
  const valid = isUrl(draft.url) && draft.name.trim() && draft.topic && !intervalError;

  return (
    <Dialog
      open={feed !== null}
      onOpenChange={(open) => !open && onClose()}
      title={<><Icon name="Rss" size="sm" /> {editing ? 'Edit RSS Feed' : 'Add RSS Feed'}</>}
      footer={
        <>
          <DialogClose>
            <Button variant="secondary" size="lg">Cancel</Button>
          </DialogClose>
          {/* Bug 2: a real primary button (was transparent with white text) */}
          <Button size="lg" disabled={!valid} busy={saving} onClick={save}>
            {editing ? 'Update Feed' : 'Add Feed'}
          </Button>
        </>
      }
    >
      <Stack gap="lg">
        <TextField
          label="Feed URL"
          type="url"
          placeholder="https://example.com/feed.xml"
          value={draft.url}
          onChange={(v) => {
            set('url', v);
            setTest('idle');
          }}
          action={
            <Button
              size="lg"
              variant="secondary"
              disabled={!isUrl(draft.url)}
              busy={test === 'testing'}
              onClick={runTest}
            >
              {test === 'testing' ? 'Testing…' : 'Test'}
            </Button>
          }
        />
        {saveError && <Banner tone="error" icon="WarningCircle" title="Not saved" description={saveError} />}
        {typeof test === 'object' &&
          (test.valid ? (
            <Banner
              tone="success"
              icon="CheckCircle"
              title={`Valid ${test.feed_type ?? 'feed'}${test.title ? `: “${test.title}”` : ''}`}
              description={`${test.entry_count ?? 0} entries`}
            />
          ) : (
            <Banner tone="error" icon="WarningCircle" title="Feed not readable" description={test.error ?? 'Unknown error'} />
          ))}
        <TextField label="Name" placeholder="My RSS Feed" value={draft.name} onChange={(v) => set('name', v)} />
        <Select label="Topic" fullWidth placeholder="Select topic..." options={topics.map((t) => ({ value: t, label: t }))} value={draft.topic} onValueChange={(v) => set('topic', v)} />
        <TextField label="Description (optional)" placeholder="A brief description of this feed" value={draft.description} onChange={(v) => set('description', v)} />
        <Grid columns={2} stackAt="small" gap="md">
          <TextField label="Check Interval" type="number" min={1} max={9999} value={draft.interval} onChange={(v) => set('interval', v)} error={intervalError} />
          <Select label="Unit" fullWidth options={UNIT_OPTIONS} value={draft.unit} onValueChange={(v) => set('unit', v as IntervalUnit)} />
        </Grid>
        <Switch label="Active" description="Enable automatic fetching" checked={draft.active} onCheckedChange={(c) => set('active', c)} />
        {/* Bug 3: visible slider */}
        <Slider
          label="Relevance Threshold"
          value={draft.threshold}
          onValueChange={(v) => set('threshold', v)}
          step={5}
          valueText={draft.threshold === 0 ? 'Off' : `${draft.threshold}%`}
          hint={draft.threshold === 0 ? 'All articles will be enriched without relevance filtering' : `Only articles scoring ${draft.threshold}% or more are enriched`}
        />
        <Select
          label="Default Factual Reporting"
          fullWidth
          options={FACTUAL_OPTIONS}
          value={draft.factual}
          onValueChange={(v) => set('factual', v as FactualReporting)}
        />
        <Banner tone="info" icon="Info" title="Credibility" description="Credibility will be determined by AI analysis or media bias database unless you set a default." />
      </Stack>
    </Dialog>
  );
}
