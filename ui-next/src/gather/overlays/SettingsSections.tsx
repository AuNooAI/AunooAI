import { Checkbox, Chip, Eyebrow, Grid, Icon, Select, type SelectOption, Slider, Stack, Switch, Text, TextField } from '@aunoo/ui';
import type { AvailableProvider } from '@monolith/gatherApi';
import { UNIT_OPTIONS, type CollectSettings, type IntervalUnit } from '../model';
import { rangeError } from '../lib';

/** Saved by the backend but not read by collection yet (the old page said "(not used)"). */
const NOT_USED = 'Saved, but collection doesn’t use this yet.';

type Section = 'schedule' | 'providers' | 'processing' | 'ai';

const SECTION_KEYS: Record<Section, (keyof CollectSettings)[]> = {
  schedule: ['interval', 'unit', 'dateRange', 'dailyLimit'],
  providers: ['providers', 'socialPlatforms'],
  processing: ['autoProcessing', 'qualityControl', 'approvedOnly', 'minRelevance'],
  ai: ['model', 'temperature', 'maxTokens', 'autoRegenerate'],
};

/** Field errors for the number inputs; empty = valid. */
export function settingsErrors(s: CollectSettings, group = false) {
  const errors: Partial<Record<keyof CollectSettings, string>> = {
    interval: rangeError(s.interval, 1, 9999),
    dateRange: rangeError(s.dateRange, 1, 30),
    maxTokens: rangeError(s.maxTokens, 100, 4000),
    ...(group ? {} : { dailyLimit: rangeError(s.dailyLimit, 10, 1000) }),
  };
  if (s.providers.length === 0) errors.providers = 'Choose at least one provider.';
  return Object.fromEntries(Object.entries(errors).filter(([, v]) => v)) as typeof errors;
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

interface Props {
  value: CollectSettings;
  onChange: (next: CollectSettings) => void;
  /** Group settings: hides Daily Request Limit and Auto-Regenerate, and tags sections that differ from `global`. */
  global?: CollectSettings;
  /** Show field errors (after a save attempt or once a field is edited). */
  errors: Partial<Record<keyof CollectSettings, string>>;
  /** From /api/keyword-monitor/available-providers */
  providers: AvailableProvider[];
  /** From /api/trend-convergence/models */
  models: SelectOption[];
}

/** Schedule · News Providers · Processing · AI — shared by Auto-Collect Settings and Group Settings. */
export function SettingsSections({ value, onChange, global, errors, providers, models }: Props) {
  const set = <K extends keyof CollectSettings>(key: K, v: CollectSettings[K]) => onChange({ ...value, [key]: v });
  const isGroup = Boolean(global);
  const custom = (section: Section) => global && SECTION_KEYS[section].some((k) => !same(value[k], global[k]));

  const heading = (section: Section, text: string) => (
    <Stack direction="row" gap="sm">
      <Eyebrow as="h3">{text}</Eyebrow>
      {custom(section) && <Chip size="sm" tone="info" variant="outline" icon={<Icon name="SlidersHorizontal" size="sm" />}>Custom</Chip>}
    </Stack>
  );

  const unitLabel = UNIT_OPTIONS.find((u) => u.value === value.unit)?.label.toLowerCase() ?? value.unit;

  return (
    <Stack gap="lg">
      <Stack gap="md">
        {heading('schedule', 'Collection Schedule')}
        <Grid columns={2} stackAt="small" gap="md">
          <TextField
            label="Check Interval"
            type="number"
            min={1}
            max={9999}
            value={value.interval}
            onChange={(v) => set('interval', v)}
            error={errors.interval}
            hint={errors.interval ? undefined : `Check every ${value.interval} ${unitLabel}`}
          />
          <Select label="Unit" fullWidth options={UNIT_OPTIONS} value={value.unit} onValueChange={(v) => set('unit', v as IntervalUnit)} />
          <TextField
            label="Search Date Range (days)"
            type="number"
            min={1}
            max={30}
            value={value.dateRange}
            onChange={(v) => set('dateRange', v)}
            error={errors.dateRange}
            hint={errors.dateRange ? undefined : '1–30 days back'}
          />
          {!isGroup && (
            <TextField
              label="Daily Request Limit"
              type="number"
              min={10}
              max={1000}
              value={value.dailyLimit}
              onChange={(v) => set('dailyLimit', v)}
              error={errors.dailyLimit}
              hint={errors.dailyLimit ? undefined : '10–1,000 requests a day. Not enforced yet.'}
            />
          )}
        </Grid>
      </Stack>

      <Stack gap="sm">
        {heading('providers', 'News Providers')}
        {providers.map((p) => (
          <Checkbox
            key={p.id}
            label={<>{p.name} <Text as="span" variant="hint">· {p.configured ? p.description : 'Not configured'}</Text></>}
            disabled={!p.configured}
            checked={value.providers.includes(p.id)}
            onCheckedChange={(c) => set('providers', c ? [...value.providers, p.id] : value.providers.filter((id) => id !== p.id))}
          />
        ))}
        {errors.providers && <Text tone="error">{errors.providers}</Text>}
        {isGroup && value.providers.includes('xpoz') && (() => {
          const options = providers.find((p) => p.id === 'xpoz')?.platform_options ?? [];
          if (options.length === 0) return null;
          const chosen = value.socialPlatforms ?? [];
          return (
            <Stack gap="sm">
              <Eyebrow as="h4">Social platforms</Eyebrow>
              <Text variant="hint">Leave all unticked to use the site default.</Text>
              {options.map((o) => (
                <Checkbox
                  key={o}
                  label={o}
                  checked={chosen.includes(o)}
                  onCheckedChange={(c) => {
                    const next = c ? [...chosen, o] : chosen.filter((x) => x !== o);
                    set('socialPlatforms', next.length ? next : null);
                  }}
                />
              ))}
            </Stack>
          );
        })()}
      </Stack>

      <Stack gap="md">
        {heading('processing', 'Processing Settings')}
        <Switch label="Auto-Processing" description="Score and enrich new articles as they arrive" checked={value.autoProcessing} onCheckedChange={(c) => set('autoProcessing', c)} />
        <Switch label="Quality Control" description={NOT_USED} checked={value.qualityControl} onCheckedChange={(c) => set('qualityControl', c)} />
        <Switch label="Auto-Save Approved Only" description={NOT_USED} checked={value.approvedOnly} onCheckedChange={(c) => set('approvedOnly', c)} />
        <Slider
          label="Minimum Relevance Threshold"
          value={value.minRelevance}
          onValueChange={(v) => set('minRelevance', v)}
          step={5}
          valueText={`${value.minRelevance}%`}
        />
      </Stack>

      <Stack gap="md">
        {heading('ai', 'AI Settings')}
        <Select label="Default LLM Model" fullWidth placeholder="Select model..." options={models} value={value.model} onValueChange={(v) => set('model', v)} />
        {/* 0–2 in steps of 0.1, as the old page stored it */}
        <Slider
          label="LLM Temperature"
          value={value.temperature}
          onValueChange={(v) => set('temperature', Math.round(v * 10) / 10)}
          min={0}
          max={2}
          step={0.1}
          valueText={value.temperature.toFixed(1)}
          hint={NOT_USED}
        />
        <TextField
          label="Max Tokens"
          type="number"
          min={100}
          max={4000}
          value={value.maxTokens}
          onChange={(v) => set('maxTokens', v)}
          error={errors.maxTokens}
          hint={errors.maxTokens ? undefined : `100–4,000. ${NOT_USED}`}
        />
        {!isGroup && (
          <Switch label="Auto-Regenerate Reports" description="Rebuild reports after each collection run" checked={value.autoRegenerate} onCheckedChange={(c) => set('autoRegenerate', c)} />
        )}
      </Stack>
    </Stack>
  );
}
