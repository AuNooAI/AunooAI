import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, Grid, Icon, Select, type SelectOption } from '@aunoo/ui';
import type { AIModel, OrganizationalProfile } from '@monolith/api';
import { contextEstimate, type AnalysisConfig } from '../lib/useWorkspace';

const DATA_RANGES: SelectOption[] = [
  { value: '1', label: 'Last 24 hours' },
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 6 months' },
  { value: '365', label: 'Last year' },
  { value: '0', label: 'All time' },
];
const SOURCE_QUALITY: SelectOption[] = [
  { value: 'all', label: 'All sources' },
  { value: 'high_quality', label: 'High quality only (high factuality and credibility)' },
];
const ARTICLE_LIMITS: SelectOption[] = [
  { value: 'auto', label: 'Auto (fits the model)' },
  { value: '50', label: '50 articles' },
  { value: '100', label: '100 articles' },
  { value: '200', label: '200 articles' },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: AnalysisConfig;
  topics: string[];
  models: AIModel[];
  profiles: OrganizationalProfile[];
  onManageProfiles: () => void;
  onSave: (config: AnalysisConfig) => void;
  onGenerate: (config: AnalysisConfig) => void;
}

/** Analysis settings for every analysis tab: topic, window, sources, profile, model, sample size. */
export function ConfigureDialog({ open, onOpenChange, config, topics, models, profiles, onManageProfiles, onSave, onGenerate }: Props) {
  const [draft, setDraft] = useState(config);
  useEffect(() => {
    if (open) setDraft(config);
  }, [open, config]);
  const set = (patch: Partial<AnalysisConfig>) => setDraft((d) => ({ ...d, ...patch }));
  const est = contextEstimate(draft, models);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Configure analysis"
      description="These settings apply to every analysis tab."
      footer={
        <>
          <Button variant="secondary" size="lg" onClick={() => { onSave(draft); onOpenChange(false); }}>Save</Button>
          <Button size="lg" iconEnd={<Icon name="Play" size="sm" />} disabled={!draft.topic || !draft.model} onClick={() => { onGenerate(draft); onOpenChange(false); }}>
            Generate analysis
          </Button>
        </>
      }
    >
      <Grid columns={2} stackAt="small" gap="md">
        <Select label="Topic" fullWidth options={topics.map((t) => ({ value: t, label: t }))} value={draft.topic} onValueChange={(topic) => set({ topic })} />
        <Select label="Source quality" fullWidth options={SOURCE_QUALITY} value={draft.sourceQuality} onValueChange={(v) => set({ sourceQuality: v as AnalysisConfig['sourceQuality'] })} />
        <Select label="Data range" fullWidth options={DATA_RANGES} value={String(draft.timeframeDays)} onValueChange={(v) => set({ timeframeDays: Number(v) })} />
        <Select
          label="Organizational profile"
          fullWidth
          placeholder="Server default"
          options={profiles.filter((p) => p.id != null).map((p) => ({ value: String(p.id), label: p.name }))}
          value={draft.profileId != null ? String(draft.profileId) : ''}
          onValueChange={(v) => set({ profileId: Number(v) })}
          footerAction={{ label: 'Manage profiles', icon: 'PencilSimple', onSelect: () => { onSave(draft); onOpenChange(false); onManageProfiles(); } }}
        />
        <Select label="AI model" fullWidth options={models.map((m) => ({ value: m.id, label: m.name }))} value={draft.model} onValueChange={(model) => set({ model })} />
        <Select label="Article limit" fullWidth options={ARTICLE_LIMITS} value={draft.articleLimit} onValueChange={(articleLimit) => set({ articleLimit })} />
      </Grid>
      <Banner
        tone={est.percent > 90 ? 'warning' : 'info'}
        icon="Lightning"
        title={`About ${est.articles} articles, ~${Math.round(est.tokens / 1000)}K tokens (${est.percent}% of the model’s context)`}
        description="An estimate; the server picks the final sample."
      />
    </Dialog>
  );
}
