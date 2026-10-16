import { useEffect, useState } from 'react';
import { Banner, Chip, Grid, Panel, Skeleton, Stack, Stat, Table, Text } from '@aunoo/ui';
import {
  getCanonicalProfile, getVendorEvents, getVendorMentions,
  type CanonicalProfile, type CanonicalProfileField, type EntityEvent, type MentionSummaryRow, type VendorBaseline,
} from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import { baselineDiffers, corroborationNote, eventDateLabel, provenanceLabel, splitMentions, statusNote, type FieldStatus } from './provenance';

/*
 * Canonical values, where each came from, and what we don't know, as the old MarketVendorProvenance.
 * The per-source panels further down show readings; this shows the answer: which reading wins for
 * each field, from which source, when, and whether anything disagrees. Where the imported workbook
 * still says something different, both are shown: a newer source displacing the import is the
 * system working, not a dispute. Events say how much they should be believed.
 */

const FIELD_ORDER = ['employee_count', 'funding_total_musd', 'funding_status', 'last_funding_type', 'hq_country', 'founded_year', 'operating_status', 'industry', 'followers_linkedin'];
const FIELD_LABELS: Record<string, string> = {
  employee_count: 'Headcount', funding_total_musd: 'Total funding', funding_status: 'Funding status', last_funding_type: 'Latest round',
  hq_country: 'Headquarters', founded_year: 'Founded', operating_status: 'Operating status', industry: 'Industry', followers_linkedin: 'LinkedIn followers',
};

function baselineValue(b: VendorBaseline | null | undefined, key: string): unknown {
  if (!b) return null;
  switch (key) {
    case 'employee_count': return b.metrics?.employee_count ?? null;
    case 'funding_total_musd': return b.funding_baseline?.total_musd ?? null;
    case 'funding_status': return b.funding_baseline?.status ?? null;
    case 'hq_country': return b.hq_country ?? null;
    case 'founded_year': return b.founded_year ?? null;
    default: return null;
  }
}

/** Crunchbase's slugs for "the round type wasn't disclosed": capitalised they read as a stage called "Series Unknown" */
const UNDISCLOSED_STAGES = new Set(['series_unknown', 'undisclosed', 'unknown', 'not_stated', 'funding_round']);
function stageLabel(raw: string) {
  if (!raw || raw === 'not stated') return 'not stated';
  if (UNDISCLOSED_STAGES.has(raw.trim().toLowerCase().replace(/ /g, '_'))) return 'Undisclosed round';
  return raw.replace(/_/g, ' ').split(' ').map((w) => (w.length === 1 ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1))).join(' ');
}

function displayValue(f: CanonicalProfileField) {
  if (f.value_number != null) {
    const n = Number(f.value_number);
    // A year isn't a quantity: "2,019" is wrong
    if (f.field_key === 'founded_year') return String(Math.trunc(n));
    const s = Number.isInteger(n) ? n.toLocaleString() : String(n);
    return f.unit === 'musd' ? `$${s}m` : s;
  }
  if (f.value_text && f.field_key === 'last_funding_type') return stageLabel(f.value_text);
  return f.value_text ?? '—';
}

const NOTE_TONE = { neutral: 'muted', warn: 'warning', alert: 'error', good: 'success' } as const;

export function Provenance({ marketId, brandId, baseline }: { marketId: number; brandId: number; baseline: VendorBaseline | null | undefined }) {
  const [profile, setProfile] = useState<CanonicalProfile | null | undefined>(undefined);
  const [events, setEvents] = useState<EntityEvent[]>([]);
  const [mentions, setMentions] = useState<MentionSummaryRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setProfile(undefined);
    setError(null);
    getCanonicalProfile(marketId, brandId)
      .then((p) => {
        if (!live) return;
        setProfile(p);
        if (p === null) return;
        return Promise.all([getVendorEvents(marketId, brandId, 25), getVendorMentions(marketId, brandId, { limit: 1 })]).then(([ev, mn]) => {
          if (!live) return;
          setEvents(ev.events);
          setMentions(mn.summary);
        });
      })
      .catch((e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [marketId, brandId]);

  // The entity layer is switched off: show nothing, as the old page did
  if (profile === null) return null;
  if (error) return <Banner tone="warning" title="Where the figures come from didn’t load" description={error} />;
  if (profile === undefined) return <Skeleton variant="block" size="card" />;

  const byField = new Map(profile.fields.map((f) => [f.field_key, f]));
  const ordered = FIELD_ORDER.filter((f) => byField.has(f));
  const missing = FIELD_ORDER.filter((f) => !byField.has(f));
  const split = splitMentions(mentions.map((m) => ({ channel: m.channel, total: m.total, unevaluated: m.unevaluated, positive: m.positive, negative: m.negative, owned_claims: m.owned_claims })));
  const confirmed = events.filter((e) => corroborationNote(e.corroboration, e.sources).tone === 'good').length;

  return (
    <>
      <Panel title="Current profile" description="What we currently believe, and which reading says so.">
        <Stack gap="sm">
          {ordered.length === 0 ? <Text>No resolved fields yet for this vendor.</Text> : (
            <Table<string>
              caption="Current profile"
              hideCaption
              rows={ordered}
              rowKey={(k) => k}
              columns={[
                { key: 'field', header: 'Field', rowHeader: true, render: (k) => FIELD_LABELS[k] ?? k },
                { key: 'value', header: 'Value', render: (k) => displayValue(byField.get(k)!) },
                {
                  key: 'source', header: 'Source', wrap: true,
                  render: (k) => {
                    const o = byField.get(k)!;
                    const prev = baselineValue(baseline, k);
                    const note = o.status !== 'current' ? statusNote(o.status as FieldStatus, o.stale_after) : null;
                    return (
                      <Stack direction="row" gap="sm">
                        <Text as="span" variant="caption">{provenanceLabel(o.source, o.observed_at)}</Text>
                        {note && <Chip size="sm" tone={NOTE_TONE[note.tone]}>{note.text}</Chip>}
                        {/* History, not a dispute: a newer, better source has moved on from the import */}
                        {baselineDiffers(prev, o.value_number ?? o.value_text) && <Text as="span" variant="hint">{`${String(prev)} at import`}</Text>}
                      </Stack>
                    );
                  },
                },
              ]}
            />
          )}
          {missing.length > 0 && (
            <Text variant="caption">
              No source has answered: {missing.map((f) => FIELD_LABELS[f] ?? f).join(', ')}. That is a gap in what we have collected, not a statement about the company.
            </Text>
          )}
        </Stack>
      </Panel>

      <Panel title="Events" description="What happened, and how much of it anyone other than the vendor has confirmed.">
        {events.length === 0 ? <Text>No events extracted yet.</Text> : (
          <Stack gap="sm">
            <Text variant="caption">{confirmed} of {events.length} confirmed by someone other than the vendor.</Text>
            <Stack as="ul" gap="sm" label="Events">
              {events.slice(0, 12).map((e) => {
                const note = corroborationNote(e.corroboration, e.sources);
                return (
                  <li key={e.id}>
                    <Stack gap="sm">
                      <Text as="span">{e.title}</Text>
                      <Stack direction="row" gap="sm">
                        <Text as="span" variant="caption">{e.event_type.replace(/_/g, ' ')}</Text>
                        <Chip size="sm" tone={NOTE_TONE[note.tone]}>{note.text}</Chip>
                        <Text as="span" variant="caption">{eventDateLabel(e.occurred_at, e.date_precision)}</Text>
                      </Stack>
                    </Stack>
                  </li>
                );
              })}
            </Stack>
          </Stack>
        )}
      </Panel>

      <Panel title="Mentions" description="All time, not the period picked on the market page. The vendor’s own posts and website are counted apart from what other people said.">
        <Stack gap="sm">
          <Grid columns={4}>
            <Stat size="compact" label="Own posts" value={split.owned.toLocaleString()} />
            <Stat size="compact" label="External mentions" value={split.external.toLocaleString()} />
            <Stat size="compact" label="Evaluated" value={split.evaluated.toLocaleString()} />
            <Stat size="compact" label="Net sentiment" value={split.netSentiment == null ? '—' : `${Math.round(split.netSentiment * 100)}%`} />
          </Grid>
          <Text variant="caption">
            {split.netSentiment == null
              ? split.external === 0
                ? 'No external mentions have been collected. That is a gap in coverage, not evidence that nobody discussed this company.'
                : `None of the ${split.external} external mentions have been evaluated yet, so there is no sentiment figure to show.`
              : `Out of ${split.denominator} evaluated mentions.${split.unevaluated > 0 ? ` ${split.unevaluated} more are found but not yet judged, and are left out.` : ''}`}
          </Text>
        </Stack>
      </Panel>
    </>
  );
}
