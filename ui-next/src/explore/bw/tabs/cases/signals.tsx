// Five Signals screening: labels, the compact chip strip on article rows, and one shared poller.
// A screen runs on the analysis platform (claim validation + Bluesky reach, 2–4 minutes). Runs start
// only from a button; while one is running this module polls its status every 5 s and tells every
// view through the `bw:signals` window event, so chips update wherever the article is shown.
import { useEffect, useState } from 'react';
import { Button, Chip, Icon } from '@aunoo/ui';
import { getSignalsDetail, runSignals, type BWArticleSignals, type BWSignalsMode } from '@monolith/brandWatcherApi';

export type SignalsSummary = {
  status: string;
  verdict?: string | null;
  composite?: number | null;
  signals: { key: string; band?: string | null; score?: number | null }[];
};

export const SIG_ORDER = ['veracity', 'source_credibility', 'corroboration', 'propagation', 'amplification_integrity'] as const;
export const SIG_SHORT: Record<string, string> = { veracity: 'V', source_credibility: 'S', corroboration: 'C', propagation: 'P', amplification_integrity: 'A' };
export const SIG_TITLE: Record<string, string> = {
  veracity: 'Claim veracity', source_credibility: 'Source credibility', corroboration: 'Corroboration',
  propagation: 'Spread on social', amplification_integrity: 'Amplification integrity',
};
export const SIG_DESC: Record<string, string> = {
  veracity: 'Are the article’s claims true? Each claim is pulled out and checked against other coverage and the open web.',
  source_credibility: 'How reliable is the outlet, from its Media Bias / Fact Check record. Satire scores near zero.',
  corroboration: 'Is anyone else reporting this independently? Same-owner outlets and wire copies don’t count.',
  propagation: 'How far it has spread on social networks. Wide spread of a damaging story is the risky case, so high spread is marked as a problem.',
  amplification_integrity: 'Does the spread look natural? Low scores mean the pickup looks manufactured.',
};
export const BAND_WORD: Record<string, string> = { good: 'healthy', warn: 'caution', bad: 'problem', nodata: 'no data' };
export const BAND_TONE: Record<string, 'success' | 'warning' | 'error' | 'muted'> = { good: 'success', warn: 'warning', bad: 'error', nodata: 'muted' };
export const VERDICT_DESC: Record<string, string> = {
  corroborated: 'Several independent outlets carry the story and its claims check out.',
  partial: 'Some claims are supported; others couldn’t be checked.',
  single_source: 'Only one source reports this. Unconfirmed, not necessarily false.',
  contested: 'Evidence disputes one or more of the claims.',
  non_independent: 'The apparent confirmation comes from same-owner outlets or wire copy.',
  unverifiable_input: 'The article couldn’t be fetched or its claims couldn’t be pulled out.',
  satire: 'The outlet is satire, not factual reporting.',
  likely_coordinated: 'Coverage patterns suggest placed rather than natural reporting.',
};

export const sigKey = (uri: string, brandId: number | null | undefined) => `${uri}|${brandId ?? ''}`;

export const summaryOf = (d: BWArticleSignals): SignalsSummary => ({
  status: d.status, verdict: d.verdict, composite: d.composite_score,
  signals: SIG_ORDER.map((k) => ({ key: k, band: d.signals?.[k]?.band ?? null, score: d.signals?.[k]?.score ?? null })),
});

const EVENT = 'bw:signals';
type Payload = { key: string; summary: SignalsSummary | null; detail?: BWArticleSignals };

function emit(p: Payload) {
  window.dispatchEvent(new CustomEvent<Payload>(EVENT, { detail: p }));
}

const polls = new Map<string, ReturnType<typeof setInterval>>();

/** Polls a running screen until it finishes, then tells every view. */
export function pollSignals(uri: string, brandId: number) {
  const key = sigKey(uri, brandId);
  if (polls.has(key)) return;
  polls.set(key, setInterval(async () => {
    try {
      const d = await getSignalsDetail(uri, brandId);
      if (d.status !== 'running') {
        clearInterval(polls.get(key));
        polls.delete(key);
        emit({ key, summary: summaryOf(d), detail: d });
      }
    } catch {
      // still starting; try again
    }
  }, 5000));
}

/** Starts a screen (an AI and external lookup run). Resolves once started; the poller reports the result. */
export async function startSignals(uri: string, brandId: number, force: boolean, mode: BWSignalsMode) {
  const key = sigKey(uri, brandId);
  emit({ key, summary: { status: 'running', signals: [] } });
  try {
    const r = await runSignals(uri, brandId, force, mode);
    if (r.status === 'completed') {
      const d = await getSignalsDetail(uri, brandId);
      emit({ key, summary: summaryOf(d), detail: d });
    } else {
      pollSignals(uri, brandId);
    }
  } catch (e) {
    emit({ key, summary: null });
    throw e;
  }
}

/** Latest screen summaries reported by the poller, keyed by sigKey. `null` = forget the override. */
export function useSignalsOverrides() {
  const [map, setMap] = useState<Record<string, SignalsSummary | null>>({});
  useEffect(() => {
    const on = (e: Event) => {
      const { key, summary } = (e as CustomEvent<Payload>).detail;
      setMap((m) => ({ ...m, [key]: summary }));
    };
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, []);
  return map;
}

/** Full detail updates for one article (the dialog listens to swap in finished results). */
export function useSignalsDetailEvents(key: string | null, onDetail: (d: BWArticleSignals) => void) {
  useEffect(() => {
    if (!key) return;
    const on = (e: Event) => {
      const p = (e as CustomEvent<Payload>).detail;
      if (p.key === key && p.detail) onDetail(p.detail);
    };
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, [key, onDetail]);
}

/**
 * The V/S/C/P/A strip on an article row, or a "Screen" button. Every state opens the dialog,
 * where runs are started; nothing here calls the AI.
 */
export function SignalsChips({ summary, available, uri, onOpen }: {
  summary: SignalsSummary | null | undefined;
  available: boolean;
  uri: string;
  onOpen: () => void;
}) {
  if (summary?.status === 'running') {
    return <Chip size="sm" tone="info" icon={<Icon name="ArrowsClockwise" size="sm" />}>Screening</Chip>;
  }
  if (summary?.status === 'completed') {
    const parts = (summary.signals ?? []).map((s) => `${SIG_TITLE[s.key] ?? s.key} ${s.score ?? '–'} (${BAND_WORD[s.band ?? 'nodata']})`);
    const bad = (summary.signals ?? []).filter((s) => s.band === 'bad').length;
    return (
      <Chip size="sm" tone={bad ? 'error' : 'success'} onClick={onOpen} label={`Five Signals: ${summary.verdict ?? 'no verdict'}. ${parts.join('; ')}. Open the breakdown.`}>
        Signals: {summary.verdict?.replace(/_/g, ' ') ?? 'done'}{summary.composite != null ? ` · ${summary.composite}/100` : ''}{bad ? ` · ${bad} ${bad === 1 ? 'problem' : 'problems'}` : ''}
      </Chip>
    );
  }
  if (summary?.status === 'failed') {
    return <Chip size="sm" tone="error" onClick={onOpen} label="Five Signals screen failed. Open to retry.">Signals failed</Chip>;
  }
  if (available && uri.startsWith('http')) {
    return <Button variant="ghost" size="sm" iconStart={<Icon name="ShieldCheck" size="sm" />} onClick={onOpen}>Screen</Button>;
  }
  return null;
}
