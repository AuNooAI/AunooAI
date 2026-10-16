import { useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Dialog, DialogClose, LineItems, Stack, Text, TextField } from '@aunoo/ui';
import { saveDashboard, type OrganizationalProfile } from '@monolith/api';
import { errorText } from '../../shell';
import { BACKEND_TAB, type Payload } from '../lib/model';
import { fetchTabData } from '../lib/useAnalysis';
import type { AnalysisConfig } from '../lib/useWorkspace';

const ALL_TABS = Object.values(BACKEND_TAB);

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: AnalysisConfig;
  backendTab: string;
  data: Payload | null;
  profile: OrganizationalProfile | undefined;
  onSaved: (name: string) => void;
}

/** Saves the analysis on screen as a named dashboard (POST /api/saved-dashboards/save). */
export function SaveDialog({ open, onOpenChange, config, backendTab, data, profile, onSaved }: Props) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
      setError(null);
    }
  }, [open]);

  const articles = Number(data?.articles_analyzed ?? 0);
  // The other tabs' analyses for these settings, fetched when the dialog opens
  const [others, setOthers] = useState<Record<string, Payload> | null>(null);
  const [allTabs, setAllTabs] = useState(true);
  useEffect(() => {
    if (!open) return;
    let alive = true;
    setOthers(null);
    const rest = ALL_TABS.filter((t) => t !== backendTab);
    Promise.all(rest.map((t) => fetchTabData(config, t))).then((rs) => {
      if (alive) setOthers(Object.fromEntries(rest.flatMap((t, i) => (rs[i] ? [[t, rs[i] as Payload]] : []))));
    });
    return () => {
      alive = false;
    };
  }, [open, backendTab, config]);
  const tabData: Record<string, Payload> = { ...(allTabs && others ? others : {}), ...(data ? { [backendTab]: data } : {}) };
  const tabCount = Object.keys(tabData).length;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await saveDashboard({
        topic: config.topic,
        name: name.trim(),
        description: description.trim() || undefined,
        // The old page's config shape, so either page can load it. article_count: the server
        // counts articles from it (the old page never sent one, so saves recorded 0)
        config: {
          topic: config.topic, model: config.model, timeframe_days: config.timeframeDays, source_quality: config.sourceQuality,
          sample_size_mode: config.articleLimit === 'auto' ? 'auto' : 'custom', custom_limit: config.articleLimit === 'auto' ? undefined : Number(config.articleLimit),
          profile_id: config.profileId ?? undefined, consistency_mode: 'balanced', tab: backendTab, article_count: articles,
        },
        article_uris: [],
        tab_data: tabData,
        profile_snapshot: profile,
      });
      onSaved(name.trim());
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e).includes('409') || /exist/i.test(errorText(e)) ? 'A saved analysis with this name already exists for this topic.' : errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Save analysis"
      description="Saves the analyses so you can reopen them from Saved analyses."
      footer={
        <>
          <DialogClose>
            <Button variant="secondary" size="lg">Cancel</Button>
          </DialogClose>
          <Button size="lg" busy={busy} disabled={!name.trim() || (allTabs && !others)} onClick={save}>Save</Button>
        </>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" icon="WarningCircle" title="Not saved" description={error} />}
        <TextField label="Name" placeholder="e.g. Q4 2026 review" value={name} onChange={setName} />
        <TextField label="Description (optional)" value={description} onChange={setDescription} />
        <Stack gap="sm">
          <Checkbox label="Save all five analysis tabs" checked={allTabs} onCheckedChange={setAllTabs} />
          <Text variant="hint">
            {!allTabs ? 'Only this tab is saved.' : others ? `${tabCount} of 5 tabs have an analysis for these settings. Tabs without one are left out.` : 'Checking the other tabs…'}
          </Text>
        </Stack>
        <LineItems
          label="What’s saved"
          items={[
            { id: 'topic', label: 'Topic', amount: config.topic },
            { id: 'articles', label: 'Articles', amount: String(articles) },
            { id: 'model', label: 'Model', amount: String(data?.model_used ?? config.model) },
            { id: 'range', label: 'Timeframe', amount: config.timeframeDays ? `${config.timeframeDays} days` : 'All time' },
          ]}
        />
      </Stack>
    </Dialog>
  );
}
