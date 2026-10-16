import { useCallback, useEffect, useState } from 'react';
import {
  ActivityRow, Banner, Button, Chip, Dialog, DialogClose, Eyebrow, Grid, Icon, Meter, Skeleton, Stack, Text, TextLink,
} from '@aunoo/ui';
import { getSignalsDetail, type BWArticleSignals, type BWSignalsMode } from '@monolith/brandWatcherApi';
import { downloadPropagationReport } from './cases/propagationReport';
import { errorText } from '../../../shell';
import {
  BAND_TONE, BAND_WORD, SIG_DESC, SIG_ORDER, SIG_TITLE, VERDICT_DESC, pollSignals, sigKey, startSignals, useSignalsDetailEvents,
} from './cases/signals';

/*
 * Five Signals screen for one article (the old modal in BrandWatcherTab.tsx). Opening it only reads
 * the stored screen. Every run button calls the analysis platform (claim validation and/or the
 * Bluesky reach lookup, plus the X/Reddit/TikTok/Instagram query where set up), so runs are explicit.
 */

type Target = { uri: string; title?: string; brand_id?: number | null };

const NETWORK: Record<string, string> = { twitter: 'X / Twitter', reddit: 'Reddit', tiktok: 'TikTok', instagram: 'Instagram' };
const RISKY = ['contested', 'non_independent', 'satire', 'likely_coordinated'];

// The platform wraps sub-results as {status, output:{...}}; older rows are flat
const sub = (val: Record<string, unknown>, key: string): Record<string, unknown> => {
  const block = (val[key] ?? {}) as Record<string, unknown>;
  return ('output' in block || 'status' in block ? (block.output ?? {}) : block) as Record<string, unknown>;
};
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const day = (s: unknown) => String(s ?? '').slice(0, 10);

function Completed({ d, run }: { d: BWArticleSignals; run: (mode: BWSignalsMode, force: boolean) => void }) {
  const sigs = d.signals ?? {};
  const val = (d.validation ?? {}) as Record<string, unknown>;
  const claims = arr<{ status?: string; claim_text?: string; claim?: string }>(val.claim_verifications);
  const web = arr<{ verdict?: string; claim_text?: string }>(sub(val, 'web_evidence').verdicts);
  const corroborators = arr<{ source?: string; domain?: string; title?: string }>(sub(val, 'corroboration').corroborators);
  const factChecks = arr<{ rating?: string; publisher_name?: string; provider?: string; review_url?: string }>(sub(val, 'external_fact_check').matched_reviews);
  const reach = d.reach as { posts?: Record<string, unknown>[]; totals?: { posts?: number; unique_accounts?: number }; first_seen?: string; search_available?: boolean; window_days?: number } | null;
  const reachPosts = arr<Record<string, unknown>>(reach?.posts);
  const xnet = (d as { xnet?: { live_available?: boolean; platforms?: Record<string, { posts: number; engagement: number; first_seen?: string; sample?: Record<string, unknown>[] }> } }).xnet ?? null;
  const platforms = Object.entries(xnet?.platforms ?? {}).sort((a, b) => b[1].posts - a[1].posts);

  return (
    <Stack gap="lg">
      <Stack direction="row" gap="sm">
        <Chip tone={RISKY.includes(d.verdict ?? '') ? 'error' : d.verdict === 'corroborated' ? 'success' : 'warning'}>Verdict: {(d.verdict ?? 'none').replace(/_/g, ' ')}</Chip>
        {d.composite_score != null && <Chip tone="muted">Overall {d.composite_score} / 100</Chip>}
        {d.error && <Chip tone="warning">One of the two checks failed</Chip>}
        <Chip tone="muted">Screened {String(d.updated_at ?? '').slice(0, 16).replace('T', ' ')}{d.requested_by === 'auto' ? ', automatically' : ''}</Chip>
      </Stack>
      {VERDICT_DESC[d.verdict ?? ''] && <Text variant="description">{VERDICT_DESC[d.verdict ?? '']}</Text>}
      <Text variant="caption">The overall score is the mean of the signals that have data, with spread counted against (wide spread lowers it). Higher is healthier.</Text>

      <Grid as="ul" columns={2} stackAt="small" gap="sm" label="Signals">
        {SIG_ORDER.map((k) => {
          const s = sigs[k];
          if (!s) return null;
          const band = s.band ?? 'nodata';
          return (
            <li key={k}>
              <Stack gap="sm">
                <Stack direction="row" justify="between" gap="sm">
                  <Text variant="label" as="span">{SIG_TITLE[k]}</Text>
                  <Chip size="sm" tone={BAND_TONE[band]}>{s.score != null ? `${s.score} · ${BAND_WORD[band]}` : 'no data'}</Chip>
                </Stack>
                {s.score != null && <Meter label={`${SIG_TITLE[k]} score`} value={Math.max(0, Math.min(100, s.score))} max={100} hideValue tone={band === 'good' ? 'success' : band === 'warn' ? 'warning' : band === 'bad' ? 'error' : 'neutral'} />}
                <Text variant="caption">{s.summary || SIG_DESC[k]}</Text>
              </Stack>
            </li>
          );
        })}
      </Grid>

      {!d.validation && (
        <Banner tone="info" title="Claims not checked yet" description="Claim validation fills claim veracity, source credibility and corroboration (about 1–3 minutes)." action={<Button size="sm" variant="secondary" onClick={() => run('validation', false)}>Check claims</Button>} />
      )}
      {claims.length > 0 && (
        <Stack gap="sm">
          <Eyebrow as="h4">Claims checked</Eyebrow>
          <Text variant="caption">“Unsupported” means nothing was found either way, not that the claim is false.</Text>
          <Stack as="ul" gap="sm" label="Claims">
            {claims.map((c, i) => (
              <li key={i}>
                <Stack direction="row" gap="sm" wrap={false}>
                  <Chip size="sm" tone={c.status === 'supported' ? 'success' : c.status === 'contested' || c.status === 'unsupported' ? 'error' : 'muted'}>{c.status || 'uncertain'}</Chip>
                  <Text variant="description" as="span">{c.claim_text || c.claim}</Text>
                </Stack>
              </li>
            ))}
          </Stack>
        </Stack>
      )}
      {(corroborators.length > 0 || web.length > 0 || factChecks.length > 0) && (
        <Grid columns={2} stackAt="small" gap="md">
          {corroborators.length > 0 && (
            <Stack gap="sm">
              <Eyebrow as="h4">Other outlets carrying it</Eyebrow>
              {corroborators.slice(0, 6).map((c, i) => <Text key={i} variant="caption">{[c.source || c.domain, c.title].filter(Boolean).join(': ')}</Text>)}
            </Stack>
          )}
          {(web.length > 0 || factChecks.length > 0) && (
            <Stack gap="sm">
              <Eyebrow as="h4">Outside evidence</Eyebrow>
              {web.slice(0, 4).map((v, i) => <Text key={`w${i}`} variant="caption"><strong>{v.verdict}</strong>: {(v.claim_text ?? '').slice(0, 90)}</Text>)}
              {factChecks.slice(0, 3).map((m, i) => (
                <Text key={`f${i}`} variant="caption">
                  Fact-check {m.rating ? `(${m.rating}) ` : ''}by {m.publisher_name || m.provider}
                  {m.review_url && <> · <TextLink href={m.review_url} external>review</TextLink></>}
                </Text>
              ))}
            </Stack>
          )}
        </Grid>
      )}

      <Stack gap="sm">
        <Eyebrow as="h4">Social pickup</Eyebrow>
        <Text variant="label" as="div">
          Bluesky (live trace){reach && (reach.totals?.posts ?? 0) > 0 ? `: ${reach.totals?.posts} posts by ${reach.totals?.unique_accounts} accounts${reach.first_seen ? `, first seen ${day(reach.first_seen)}` : ''}` : ''}
        </Text>
        {!reach && (
          <Banner tone="info" title="Spread not checked yet" description="The Bluesky lookup fills spread and amplification integrity (about 1–2 minutes)." action={<Button size="sm" variant="secondary" onClick={() => run('reach', false)}>Check Bluesky spread</Button>} />
        )}
        {reach && reach.search_available === false && <Text variant="caption">Bluesky search isn’t set up on the analysis platform, so there’s no spread data.</Text>}
        {reach && reach.search_available !== false && reachPosts.length === 0 && <Text variant="caption">No Bluesky posts shared this article in the {reach.window_days || 90}-day window.</Text>}
        {reachPosts.length > 0 && (
          <Stack as="ul" gap="sm" label="Bluesky posts">
            {reachPosts.slice(0, 20).map((p, i) => (
              <ActivityRow key={i} as="li" primary={`@${String(p.handle)}${p.text ? `: ${String(p.text).slice(0, 140)}` : ''}`} secondary={`${Number(p.total_engagement ?? 0)} engagement${p.post_url ? '' : ''}`} timestamp={day(p.created_at)} dateTime={day(p.created_at)} />
            ))}
          </Stack>
        )}
        {!xnet ? (
          <Text variant="caption">X, Reddit, TikTok and Instagram: not checked yet. The next spread run includes them.</Text>
        ) : (
          <Stack gap="sm">
            <Text variant="label" as="div">Other networks ({xnet.live_available ? 'collected posts plus a live search' : 'collected posts only'})</Text>
            {platforms.length === 0 && <Text variant="caption">No shares found on X, Reddit, TikTok or Instagram.</Text>}
            {platforms.map(([k, p]) => (
              <Stack key={k} gap="sm">
                <Text variant="caption"><strong>{NETWORK[k] ?? k}</strong>: {p.posts} posts · {p.engagement} engagement{p.first_seen ? ` · first seen ${day(p.first_seen)}` : ''}</Text>
                <Stack as="ul" gap="sm" label={`${NETWORK[k] ?? k} posts`}>
                  {(p.sample ?? []).slice(0, 5).map((s, i) => (
                    <ActivityRow key={i} as="li" primary={`@${String(s.author ?? 'unknown')}${s.text ? `: ${String(s.text).slice(0, 140)}` : ''}`} secondary={`${Number(s.engagement ?? 0)} engagement · ${s.origin === 'live' ? 'live search' : 'collected'}`} timestamp={day(s.date)} />
                  ))}
                </Stack>
              </Stack>
            ))}
          </Stack>
        )}
      </Stack>
    </Stack>
  );
}

export function SignalsDialog({ target, onClose, notify }: { target: Target | null; onClose: () => void; notify: (m: string) => void }) {
  const [detail, setDetail] = useState<BWArticleSignals | null>(null);
  const [error, setError] = useState<string | null>(null);
  const brandId = target?.brand_id ?? null;
  const key = target && brandId ? sigKey(target.uri, brandId) : null;

  useEffect(() => {
    setDetail(null);
    setError(null);
    if (!target || !brandId) return;
    let stale = false;
    getSignalsDetail(target.uri, brandId).then(
      (d) => {
        if (stale) return;
        setDetail(d);
        if (d.status === 'running') pollSignals(target.uri, brandId);
      },
      (e: unknown) => !stale && setError(errorText(e)),
    );
    return () => {
      stale = true;
    };
  }, [target, brandId]);

  useSignalsDetailEvents(key, useCallback((d: BWArticleSignals) => setDetail(d), []));

  const run = (mode: BWSignalsMode, force: boolean) => {
    if (!target || !brandId) return;
    setDetail((d) => ({
      status: 'running', signals: d?.signals ?? null, verdict: d?.verdict ?? null, composite_score: d?.composite_score ?? null,
      validation: d?.validation ?? null, reach: d?.reach ?? null, error: null, requested_by: 'user',
    }));
    startSignals(target.uri, brandId, force, mode).catch((e: unknown) => {
      notify(`The screen didn’t start: ${errorText(e)}. Is the analysis platform connected?`);
      void getSignalsDetail(target.uri, brandId).then(setDetail, () => setDetail(null));
    });
  };

  const done = detail?.status === 'completed';
  return (
    <Dialog
      open={!!target}
      onOpenChange={(o) => !o && onClose()}
      title="Five Signals screen"
      size="lg"
      description={target?.title ?? target?.uri}
      footer={
        <>
          {done && (
            <>
              <Button
                variant="ghost"
                size="lg"
                iconStart={<Icon name="DownloadSimple" size="sm" />}
                onClick={() => target && downloadPropagationReport({ articleTitle: target.title ?? target.uri, articleUri: target.uri, brandName: null, signals: detail!, generatedAt: new Date().toISOString() })}
              >
                Spread report
              </Button>
              <Button variant="secondary" size="lg" onClick={() => run('validation', true)}>Re-check claims</Button>
              <Button variant="secondary" size="lg" onClick={() => run('reach', true)}>Re-check spread</Button>
              <Button variant="secondary" size="lg" iconStart={<Icon name="ArrowsClockwise" size="sm" />} onClick={() => run('full', true)}>Run all again</Button>
            </>
          )}
          <DialogClose><Button size="lg">Close</Button></DialogClose>
        </>
      }
    >
      <Stack gap="md">
        <Text variant="caption">
          Two checks run on the analysis platform: claim validation, and who shared the story on social networks. Together they give five scores. Results are kept, so looking again is free; a run takes 2–4 minutes.
        </Text>
        {!brandId && <Banner tone="warning" title="No brand on this article" description="Screening needs to know which brand the article is about." />}
        {error && <Banner tone="error" title="The screen didn’t load" description={error} />}
        {brandId && !detail && !error && <Skeleton variant="text" lines={5} />}
        {detail?.status === 'running' && <Text><span role="status">Screening now. This usually takes 2–4 minutes and updates here by itself.</span></Text>}
        {detail?.status === 'failed' && (
          <Banner tone="error" title="The screen failed" description={detail.error ?? undefined} action={<Button size="sm" variant="secondary" onClick={() => run('full', true)}>Try again</Button>} />
        )}
        {detail?.status === 'none' && (
          <Stack gap="md">
            <Text>Not screened yet.</Text>
            <div><Button iconStart={<Icon name="ShieldCheck" size="sm" />} onClick={() => run('full', false)}>Run Five Signals</Button></div>
            <Text variant="caption">Or run one check at a time; the scores it feeds fill in and the rest stay “no data”.</Text>
            <Stack direction="row" gap="sm">
              <Button size="sm" variant="secondary" onClick={() => run('validation', false)}>Claim validation only</Button>
              <Button size="sm" variant="secondary" onClick={() => run('reach', false)}>Bluesky spread only</Button>
            </Stack>
          </Stack>
        )}
        {done && <Completed d={detail} run={run} />}
      </Stack>
    </Dialog>
  );
}
