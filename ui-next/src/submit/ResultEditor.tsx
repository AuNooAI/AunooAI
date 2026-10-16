import { Chip, Grid, Select, Stack, TagInput, TextArea, TextField, TextLink } from '@aunoo/ui';
import { tagList, type Analysis, type Labels } from './api';

/** A label select that keeps a value the topic's list doesn't have (older articles, renamed labels). */
function LabelSelect({ label, value, options, onChange }: { label: string; value?: string; options: string[]; onChange: (v: string) => void }) {
  const all = value && !options.includes(value) ? [value, ...options] : options;
  return <Select label={label} fullWidth placeholder="Not set" options={all.map((o) => ({ value: o, label: o }))} value={value || undefined} onValueChange={onChange} />;
}

/** Review and correct what the analysis found before saving. */
export function ResultEditor({ a, labels, onChange }: { a: Analysis; labels: Labels; onChange: (patch: Partial<Analysis>) => void }) {
  const bias = [a.bias, a.factual_reporting && `Factual reporting: ${a.factual_reporting}`, a.mbfc_credibility_rating && `Credibility: ${a.mbfc_credibility_rating}`].filter(Boolean) as string[];
  return (
    <Stack gap="md">
      <Grid columns={2} stackAt="small" gap="md">
        <TextField label="Title" value={a.title ?? ''} onChange={(title) => onChange({ title })} />
        <TextField label="Source" value={a.news_source ?? ''} onChange={(news_source) => onChange({ news_source })} />
      </Grid>
      <Stack direction="row" gap="sm" wrap>
        <TextLink href={a.uri} external>{a.uri}</TextLink>
        {bias.map((b) => <Chip key={b} size="sm" tone="muted">{b}</Chip>)}
      </Stack>
      <TextArea label="Summary" rows={4} value={a.summary ?? ''} onChange={(summary) => onChange({ summary })} />
      <Grid columns={2} stackAt="small" gap="md">
        <LabelSelect label="Category" value={a.category} options={labels.categories} onChange={(category) => onChange({ category })} />
        <LabelSelect label="Sentiment" value={a.sentiment} options={labels.sentiments} onChange={(sentiment) => onChange({ sentiment })} />
      </Grid>
      <TextArea label="Why this sentiment" rows={2} value={a.sentiment_explanation ?? ''} onChange={(sentiment_explanation) => onChange({ sentiment_explanation })} />
      <Grid columns={2} stackAt="small" gap="md">
        <LabelSelect label="Future signal" value={a.future_signal} options={labels.futureSignals} onChange={(future_signal) => onChange({ future_signal })} />
        <LabelSelect label="Time to impact" value={a.time_to_impact} options={labels.timeToImpacts} onChange={(time_to_impact) => onChange({ time_to_impact })} />
        <TextArea label="Why this signal" rows={2} value={a.future_signal_explanation ?? ''} onChange={(future_signal_explanation) => onChange({ future_signal_explanation })} />
        <TextArea label="Why this time to impact" rows={2} value={a.time_to_impact_explanation ?? ''} onChange={(time_to_impact_explanation) => onChange({ time_to_impact_explanation })} />
      </Grid>
      <Grid columns={2} stackAt="small" gap="md">
        <LabelSelect label="Driver type" value={a.driver_type} options={labels.driverTypes} onChange={(driver_type) => onChange({ driver_type })} />
        <TextArea label="Why this driver type" rows={2} value={a.driver_type_explanation ?? ''} onChange={(driver_type_explanation) => onChange({ driver_type_explanation })} />
      </Grid>
      <TagInput label="Tags" tags={tagList(a.tags)} onChange={(tags) => onChange({ tags })} />
    </Stack>
  );
}
