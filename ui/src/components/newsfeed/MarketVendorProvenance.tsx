/**
 * Canonical values, where each came from, and what we do not know.
 *
 * The existing panels on this page show readings. This one shows the answer —
 * which reading currently wins for each field, which source it came from, when
 * it was taken, and whether anything disagrees. Every row carries that, because
 * a vendor page showing "310 people" with no attribution is exactly what this
 * layer was built to stop.
 *
 * Where the imported workbook still says something different, both are shown.
 * The difference is not an error: it means a newer credible source displaced
 * the import, which is the whole point. Hiding the old value would lose the
 * audit trail; hiding the new one would keep the page permanently wrong.
 *
 * Events carry how much they should be believed. A company's own announcement
 * is labelled as its claim until something unconnected says the same thing,
 * and an event whose date nobody stated says so rather than showing the day we
 * happened to extract it.
 */

import { useEffect, useState } from 'react';
import { AlertTriangle, ShieldCheck } from 'lucide-react';

import {
  getCanonicalProfile, getVendorEvents, getVendorMentions,
  type CanonicalProfile, type CanonicalProfileField, type EntityEvent,
  type MentionSummaryRow,
} from '../../services/marketMonitorApi';
import {
  baselineDiffers, corroborationNote, eventDateLabel, provenanceLabel,
  splitMentions, statusNote, type FieldStatus,
} from './entityProvenance';

function Panel({ title, hint, children }: {
  title: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
      <div className="text-sm font-medium text-slate-800 dark:text-gray-100">{title}</div>
      {hint && <p className="text-xs text-slate-500 mt-0.5 dark:text-gray-400">{hint}</p>}
      <div className="mt-3">{children}</div>
    </div>
  );
}

const TONE_CLASS: Record<string, string> = {
  neutral: 'text-slate-500 dark:text-gray-400',
  warn: 'text-amber-600 dark:text-amber-400',
  alert: 'text-red-600 dark:text-red-400',
  good: 'text-emerald-600 dark:text-emerald-400',
};

/** The fields worth showing on the overview, in the order a reader wants. */
const FIELD_ORDER = [
  'employee_count', 'funding_total_musd', 'funding_status', 'last_funding_type',
  'hq_country', 'founded_year', 'operating_status', 'industry',
  'followers_linkedin',
];

const FIELD_LABELS: Record<string, string> = {
  employee_count: 'Headcount',
  funding_total_musd: 'Total funding',
  funding_status: 'Funding status',
  last_funding_type: 'Latest round',
  hq_country: 'Headquarters',
  founded_year: 'Founded',
  operating_status: 'Operating status',
  industry: 'Industry',
  followers_linkedin: 'LinkedIn followers',
};

/** Where the imported workbook keeps each value, for the comparison. */
function baselineValue(baseline: Record<string, any> | null | undefined,
                       fieldKey: string): unknown {
  if (!baseline) return null;
  switch (fieldKey) {
    case 'employee_count': return baseline.metrics?.employee_count ?? null;
    case 'funding_total_musd': return baseline.funding_baseline?.total_musd ?? null;
    case 'funding_status': return baseline.funding_baseline?.status ?? null;
    case 'hq_country': return baseline.hq_country ?? null;
    case 'founded_year': return baseline.founded_year ?? null;
    default: return null;
  }
}

function displayValue(field: CanonicalProfileField): string {
  if (field.value_number != null) {
    const n = Number(field.value_number);
    const formatted = Number.isInteger(n) ? n.toLocaleString() : String(n);
    return field.unit === 'musd' ? `$${formatted}m` : formatted;
  }
  return field.value_text ?? '—';
}

export function MarketVendorProvenance({ marketId, brandId, baseline }: {
  marketId: number; brandId: number;
  baseline?: Record<string, any> | null;
}) {
  const [profile, setProfile] = useState<CanonicalProfile | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [events, setEvents] = useState<EntityEvent[]>([]);
  const [mentions, setMentions] = useState<MentionSummaryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // The canonical rows are read directly. Filtering a page of observations
    // for the winning one meant a settled or locked value dropped off the
    // page as soon as newer readings pushed it out of the window.
    getCanonicalProfile(marketId, brandId).then((p) => {
      if (cancelled) return null;
      if (p === null) {           // entity layer switched off
        setDisabled(true);
        return null;
      }
      setProfile(p);
      return Promise.all([
        getVendorEvents(marketId, brandId, 25),
        getVendorMentions(marketId, brandId, { limit: 1 }),
      ]).then(([ev, mn]) => {
        if (cancelled) return;
        setEvents(ev.events);
        setMentions(mn.summary);
      });
    }).catch((e: unknown) => {
      if (!cancelled) setError(e instanceof Error ? e.message : String(e));
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [marketId, brandId]);

  if (loading) {
    return (
      <Panel title="Current profile">
        <p className="text-sm text-slate-500 py-4 dark:text-gray-400">Loading…</p>
      </Panel>
    );
  }

  // Switched off: render nothing at all, so turning the flag off restores the
  // page as it was rather than leaving an error panel behind.
  if (disabled) return null;

  if (error) {
    return (
      <Panel title="Current profile">
        <p className="text-sm text-amber-600 py-4 dark:text-amber-400">
          Could not load provenance: {error}
        </p>
      </Panel>
    );
  }

  const byField = new Map(
    (profile?.fields ?? []).map(f => [f.field_key, f]));
  const ordered = FIELD_ORDER.filter(f => byField.has(f));
  const missing = FIELD_ORDER.filter(f => !byField.has(f));
  const split = splitMentions(mentions.map(m => ({
    channel: m.channel, total: m.total, unevaluated: m.unevaluated,
    positive: m.positive, negative: m.negative, owned_claims: m.owned_claims,
  })));

  return (
    <div className="grid gap-4">
      <Panel
        title="Current profile"
        hint="What we currently believe, and which reading says so."
      >
        {ordered.length === 0 ? (
          <p className="text-sm text-slate-500 py-4 dark:text-gray-400">
            No resolved fields yet for this vendor.
          </p>
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {ordered.map(fieldKey => {
                const observation = byField.get(fieldKey)!;
                const previous = baselineValue(baseline, fieldKey);
                const differs = baselineDiffers(
                  previous,
                  observation.value_number ?? observation.value_text);
                return (
                  <tr key={fieldKey}
                      className="border-t first:border-t-0 dark:border-gray-700">
                    <td className="py-2 pr-3 text-slate-500 w-40 dark:text-gray-400">
                      {FIELD_LABELS[fieldKey] ?? fieldKey}
                    </td>
                    <td className="py-2 pr-3 font-medium text-slate-800 dark:text-gray-100">
                      {displayValue(observation)}
                    </td>
                    <td className="py-2 text-xs text-slate-500 dark:text-gray-400">
                      {provenanceLabel(observation.source, observation.observed_at)}
                      {observation.status !== 'current' && (
                        <span className={`ml-2 ${TONE_CLASS[
                          statusNote(observation.status as FieldStatus,
                                     observation.stale_after).tone]}`}>
                          {statusNote(observation.status as FieldStatus,
                                      observation.stale_after).text}
                        </span>
                      )}
                      {differs && (
                        <span className="ml-2 text-amber-600 dark:text-amber-400">
                          import said {String(previous)}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {missing.length > 0 && (
          <p className="text-xs text-slate-500 mt-3 dark:text-gray-400">
            No source has answered: {missing.map(f => FIELD_LABELS[f] ?? f).join(', ')}.
            That is a gap in what we have collected, not a statement about the company.
          </p>
        )}
      </Panel>

      <Panel
        title="Events"
        hint="What happened, and how much of it anyone other than the vendor has confirmed."
      >
        {events.length === 0 ? (
          <p className="text-sm text-slate-500 py-4 dark:text-gray-400">
            No events extracted yet.
          </p>
        ) : (
          <>
          <p className="text-xs text-slate-500 mb-2 dark:text-gray-400">
            {events.filter(e => corroborationNote(e.corroboration, e.sources).tone === 'good').length}
            {' '}of {events.length} confirmed by someone other than the vendor.
          </p>
          <ul className="space-y-3">
            {/* The icon follows the note's tone. A vendor announcing its own
                news is the normal way to learn of it and the note calls that
                neutral, so it gets no icon; an amber triangle on every row was
                a warning that warned of nothing. The shield marks an outside
                account, the triangle a record with no source at all. */}
            {events.slice(0, 12).map(event => {
              const note = corroborationNote(event.corroboration, event.sources);
              return (
                <li key={event.id} className="text-sm">
                  <div className="flex items-start gap-2">
                    {note.tone === 'good'
                      ? <ShieldCheck className="w-4 h-4 mt-0.5 text-emerald-600 shrink-0" />
                      : note.tone === 'warn'
                        ? <AlertTriangle className="w-4 h-4 mt-0.5 text-amber-500 shrink-0" />
                        : <span className="w-4 h-4 mt-0.5 shrink-0 flex items-center justify-center">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-gray-600" />
                          </span>}
                    <div className="min-w-0">
                      <div className="text-slate-800 truncate dark:text-gray-100">
                        {event.title}
                      </div>
                      <div className="text-xs text-slate-500 dark:text-gray-400">
                        {event.event_type.replace(/_/g, ' ')} ·{' '}
                        <span className={TONE_CLASS[note.tone]}>{note.text}</span> ·{' '}
                        {eventDateLabel(event.occurred_at, event.date_precision)}
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
          </>
        )}
      </Panel>

      <Panel
        title="Coverage"
        hint="All time, not the period selected on the market page. The vendor's own posts and its own website are counted apart from what other people said."
      >
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 text-sm">
          <Stat label="Own posts" value={split.owned} />
          <Stat label="External mentions" value={split.external} />
          <Stat label="Evaluated" value={split.evaluated} />
          <Stat
            label="Net sentiment"
            value={split.netSentiment == null
              ? '—'
              : `${Math.round(split.netSentiment * 100)}%`}
          />
        </div>
        {split.netSentiment == null ? (
          <p className="text-xs text-slate-500 mt-3 dark:text-gray-400">
            {split.external === 0
              ? 'No external mentions have been collected. That is a gap in '
                + 'coverage, not evidence that nobody discussed this company.'
              : `None of the ${split.external} external mentions have been `
                + 'evaluated yet, so there is no sentiment figure to show.'}
          </p>
        ) : (
          <p className="text-xs text-slate-500 mt-3 dark:text-gray-400">
            Out of {split.denominator} evaluated mentions.
            {split.unevaluated > 0
              && ` ${split.unevaluated} more are found but not yet judged, and are excluded.`}
          </p>
        )}
      </Panel>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <div className="text-xl font-semibold text-slate-800 dark:text-gray-100">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
      <div className="text-xs text-slate-500 dark:text-gray-400">{label}</div>
    </div>
  );
}
