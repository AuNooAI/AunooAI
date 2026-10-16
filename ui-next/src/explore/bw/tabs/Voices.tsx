import { useEffect, useMemo, useState } from 'react';
import {
  ArticleCard, Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Eyebrow, FilterChipRow, Grid, Icon, Panel, PanelDivider,
  Select, Skeleton, Stack, StackedBars, Text,
} from '@aunoo/ui';
import {
  getVoices, getVoicesDigest, getVoicesProfilingStatus, startVoicesProfiling,
  type BWVoicePost, type BWVoiceRole, type BWVoicesDigest, type BWVoicesProfileStatus, type BWVoicesResponse,
} from '@monolith/brandWatcherApi';
import { downloadVoicesReport } from '@monolith/voicesReportHtml';
import { errorText } from '../../../shell';
import type { BwContext } from '../context';
import { platLabel, signed, netTone } from './social/helpers';

/*
 * Voices: who is talking about the brand and what each audience thinks, as the old Voices view
 * (ui/src/components/newsfeed/BrandWatcherVoices.tsx). The audience table is a database read.
 * The AI digest of an audience and "Profile posters" (account lookups on Xpoz) run only from
 * their buttons.
 */

const MIN_REL = 0.4;
const THEME_TONE: Record<string, 'success' | 'error' | 'warning' | 'muted'> = { positive: 'success', negative: 'error', mixed: 'warning' };

function roleSource(p: BWVoicePost) {
  if (p.author_role_source === 'account_profile') {
    const who = p.account_market_role ? ` (${p.account_market_role.replace(/_/g, ' ')}${p.account_org ? `, ${p.account_org}` : ''})` : '';
    return `Role from the account profile${who}${p.post_role && p.post_role !== p.author_role ? `; this post alone read as ${p.post_role}` : ''}`;
  }
  if (p.author_role_source === 'account_posts') {
    return `Role from this account’s other posts${p.post_role && p.post_role !== p.author_role ? `; this post alone read as ${p.post_role}` : ''}`;
  }
  return p.author_role_reason ? `Why this role: ${p.author_role_reason}` : null;
}

function Column({ role, brandId, daysBack, digest, onDigest }: {
  role: BWVoiceRole; brandId: number; daysBack: number; digest: BWVoicesDigest | null; onDigest: (d: BWVoicesDigest) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const load = async () => {
    setBusy(true);
    setErr(null);
    try {
      onDigest(await getVoicesDigest(role.role, brandId, daysBack, MIN_REL));
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel
      title={role.label}
      description={role.hint}
      headingLevel={3}
      headerAside={<Chip tone={netTone(role.net)}>Net {role.net === null ? 'n/a' : signed(role.net)}</Chip>}
    >
      <Stack gap="lg">
        <StackedBars
          title={`${role.n} ${role.n === 1 ? 'post' : 'posts'}`}
          series={[{ id: 'p', label: 'Positive', color: 'positive' }, { id: 'u', label: 'Neutral', color: 'neutral' }, { id: 'n', label: 'Negative', color: 'negative' }]}
          rows={[{ id: role.role, label: role.label, values: [role.positive, role.neutral, role.negative] }]}
        />
        <Stack as="ul" direction="row" gap="sm" label="Posts by network">
          {Object.entries(role.by_platform).sort((a, b) => b[1] - a[1]).map(([pl, n]) => <li key={pl}><Chip size="sm" tone="muted">{platLabel(pl)} {n}</Chip></li>)}
        </Stack>
        <PanelDivider />
        <Stack gap="md">
          <Stack direction="row" justify="between" gap="sm">
            <Eyebrow as="h4">What {role.label.toLowerCase()} are saying</Eyebrow>
            {role.n >= 2 && (
              <Button size="sm" variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} disabled={busy} onClick={() => void load()}>
                {busy ? `Reading ${role.n} posts…` : digest ? 'Write again' : 'Summarise with AI'}
              </Button>
            )}
          </Stack>
          {role.n < 2 && <Text variant="caption">Fewer than two posts from this audience in the window, so there’s nothing to summarise yet.</Text>}
          {err && <Text tone="error">{err}</Text>}
          {digest && (
            <Stack gap="md">
              {digest.context && <Text variant="caption">{digest.context}</Text>}
              {digest.summary && <Text>{digest.summary}</Text>}
              {digest.note && <Text variant="caption">{digest.note}</Text>}
              {digest.themes.map((t, i) => (
                <Stack key={i} gap="sm">
                  <Stack direction="row" gap="sm">
                    <Text variant="label" as="span">{t.theme}</Text>
                    <Chip size="sm" tone={THEME_TONE[t.sentiment] ?? 'muted'}>{t.sentiment}</Chip>
                    {t.post_count > 0 && <Text variant="caption" as="span">{t.post_count} {t.post_count === 1 ? 'post' : 'posts'}</Text>}
                  </Stack>
                  {t.quotes.length > 0 && (
                    <Stack as="ul" gap="sm" label={`Quotes on ${t.theme}`}>
                      {t.quotes.map((q, j) => <li key={j}><Text variant="description">“{q}”</Text></li>)}
                    </Stack>
                  )}
                </Stack>
              ))}
              {!!digest.asks?.length && (
                <Stack gap="sm">
                  <Text variant="label" as="span">What these posts ask for</Text>
                  <Stack as="ul" gap="sm" label="What these posts ask for">
                    {digest.asks.map((a, i) => <li key={i}><Text variant="description">{a}</Text></li>)}
                  </Stack>
                </Stack>
              )}
              {(digest.summary || digest.themes.length > 0) && (
                <Text variant="caption">AI digest of {digest.post_count} {digest.post_count === 1 ? 'post' : 'posts'}. The quotes are copied from the posts; check the post before citing one.</Text>
              )}
            </Stack>
          )}
        </Stack>
        <PanelDivider />
        <Stack gap="sm">
          <Eyebrow as="h4">Posts</Eyebrow>
          {role.posts.length === 0 ? <Text>No posts.</Text> : (
            <Stack as="ul" gap="sm" label={`${role.label} posts`}>
              {role.posts.map((p) => (
                <ArticleCard
                  key={p.uri}
                  as="li"
                  variant="row"
                  headingLevel={4}
                  href={p.uri}
                  meta={[platLabel(p.platform || 'social'), p.publication_date?.slice(0, 10)].filter(Boolean).join(' · ')}
                  title={p.author || 'Unknown author'}
                  summary={p.text.length > 360 ? `${p.text.slice(0, 360)}…` : p.text}
                  tags={p.sentiment ? <Chip size="sm" tone={p.sentiment === 'positive' ? 'success' : p.sentiment === 'negative' ? 'error' : 'neutral'}>{p.sentiment}</Chip> : <Chip size="sm" tone="muted">Not scored</Chip>}
                  footer={roleSource(p) ? <span>{roleSource(p)}</span> : undefined}
                />
              ))}
            </Stack>
          )}
          {role.n > role.posts.length && <Text variant="caption">The {role.posts.length} most recent of {role.n}.</Text>}
        </Stack>
      </Stack>
    </Panel>
  );
}

export function Voices(ctx: BwContext) {
  const { bw, notify } = ctx;
  const daysBack = bw.config.daysBack;
  const enabled = useMemo(() => bw.brands.filter((b) => b.enabled !== false), [bw.brands]);
  const [brandId, setBrandId] = useState<number | null>(null);
  const [data, setData] = useState<BWVoicesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // The audiences compared side by side; null = the pair the server suggests
  const [picked, setPicked] = useState<string[] | null>(null);
  const [digests, setDigests] = useState<Record<string, BWVoicesDigest>>({});
  const [profiling, setProfiling] = useState<BWVoicesProfileStatus | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const brand = brandId ?? ctx.focusBrand?.id ?? enabled.find((b) => b.is_primary)?.id ?? enabled[0]?.id ?? null;

  useEffect(() => {
    if (brand == null) {
      setLoading(false);
      return;
    }
    let stale = false;
    setLoading(true);
    setError(null);
    if (reloadKey === 0) setPicked(null);
    setDigests({});
    getVoices(brand, daysBack, MIN_REL).then(
      (d) => !stale && setData(d),
      (e: unknown) => !stale && setError(errorText(e)),
    ).finally(() => !stale && setLoading(false));
    return () => {
      stale = true;
    };
  }, [brand, daysBack, reloadKey]);

  // Pick up a profiling run already going for this brand, poll while it runs, reload when it ends
  const running = profiling?.state === 'running';
  useEffect(() => {
    if (brand == null) return;
    let stale = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const st = await getVoicesProfilingStatus(brand);
        if (stale) return;
        setProfiling((prev) => {
          if (prev?.state === 'running' && st.state === 'done') setReloadKey((k) => k + 1);
          return st;
        });
        if (st.state === 'running') timer = setTimeout(tick, 3000);
      } catch {
        // the status is a convenience; the table stands without it
      }
    };
    void tick();
    return () => {
      stale = true;
      if (timer) clearTimeout(timer);
    };
  }, [brand, running]);

  const profilePosters = async () => {
    if (brand == null) return;
    try {
      const st = await startVoicesProfiling(brand, daysBack, MIN_REL);
      setProfiling(st);
      if (st.state === 'done') setReloadKey((k) => k + 1);
    } catch (e) {
      notify(`Profiling didn’t start: ${errorText(e)}`);
    }
  };

  const roles = data?.roles ?? [];
  const shown = picked ?? data?.focus ?? [];
  const columns = shown.map((r) => roles.find((x) => x.role === r)).filter((x): x is BWVoiceRole => !!x);

  // The HTML report carries the digests already written on this page; it doesn't ask the AI again
  const exportHtml = () => {
    if (!data) return;
    downloadVoicesReport({
      voices: data,
      compared: columns.map((r) => r.role),
      digests: Object.fromEntries(columns.map((r) => [r.role, digests[r.role] ?? null])),
      daysBack,
      generatedAt: new Date().toISOString(),
    });
  };

  return (
    <>
      <Panel
        title="Voices"
        description={`Who is talking about the brand, and what each audience thinks. ${daysBack === 0 ? 'All time' : `Last ${daysBack} days`}, on-brand posts only.`}
        headingLevel={3}
        headerAside={
          <Stack direction="row" gap="sm">
            {enabled.length > 1 && (
              <Select
                label="Brand"
                hideLabel
                options={enabled.map((b) => ({ value: String(b.id), label: `${b.display_name}${b.is_primary ? ' (primary)' : ''}` }))}
                value={brand != null ? String(brand) : undefined}
                onValueChange={(v) => setBrandId(Number(v))}
              />
            )}
            <Button size="sm" variant="secondary" iconStart={<Icon name="User" size="sm" />} disabled={!data || loading || running} onClick={() => void profilePosters()}>
              {running ? `Profiling ${profiling?.done ?? 0} of ${profiling?.total ?? 0}` : 'Profile posters'}
            </Button>
            <Button size="sm" variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} disabled={!data || loading} onClick={exportHtml}>Export HTML</Button>
          </Stack>
        }
      >
        <Collapsible>
          <Stack direction="row" justify="between" gap="sm">
            <Text variant="caption">“Profile posters” looks up every poster in this window without a profile on Xpoz, which uses paid credits.</Text>
            <CollapsibleTrigger variant="ghost" size="sm">How roles are read</CollapsibleTrigger>
          </Stack>
          <CollapsibleContent>
            <Text variant="description">
              The social scoring model reads the role from the post itself: using the service in the first person reads as a patient or customer,
              prescribing or referring as a clinician, a reporter or outlet as press, the company’s own promotion as brand voice. Glassdoor reviews count as
              employees. Where the text gives no clue the poster counts as a bystander rather than a guess. An account profiled under Market Monitor Top
              voices, the Accounts tab or “Profile posters” carries its role onto all its posts, and so does an account whose other posts keep reading the same
              way. The brand’s own LinkedIn and website posts are left out.
            </Text>
          </CollapsibleContent>
        </Collapsible>
      </Panel>

      {error && <Banner tone="error" title="Voices didn’t load" description={error} />}
      {profiling?.state === 'done' && (profiling.total ?? 0) > 0 && (
        <Text variant="caption">
          Profiled {profiling.built ?? 0} of {profiling.total} {profiling.total === 1 ? 'account' : 'accounts'}{profiling.failed ? `; ${profiling.failed} couldn’t be read` : ''}.
        </Text>
      )}
      {loading ? <Skeleton variant="block" size="card" /> : data && (
        <>
          {data.coverage_notes.length > 0 && <Banner tone="warning" title="Coverage notes" description={data.coverage_notes.join(' ')} />}
          {roles.length > 0 && (
            <Panel title="Audiences" description="Pick up to two to compare." headingLevel={3}>
              <Stack gap="md">
                <StackedBars
                  title="Posts by audience and sentiment"
                  series={[{ id: 'p', label: 'Positive', color: 'positive' }, { id: 'u', label: 'Neutral', color: 'neutral' }, { id: 'n', label: 'Negative', color: 'negative' }]}
                  rows={roles.map((r) => ({ id: r.role, label: `${r.label} (${r.n}, net ${r.net === null ? 'n/a' : signed(r.net)})`, values: [r.positive, r.neutral, r.negative] }))}
                />
                <FilterChipRow
                  label="Compare"
                  allLabel="Suggested pair"
                  options={roles.map((r) => ({ value: r.role, label: r.label }))}
                  selected={picked ?? []}
                  onChange={(v) => setPicked(v.length ? v.slice(-2) : null)}
                  maxVisible={12}
                />
              </Stack>
            </Panel>
          )}
          {columns.length > 0 ? (
            <Grid columns={2} stackAt="wide" gap="md">
              {columns.map((r) => (
                <Column key={r.role} role={r} brandId={data.brand_id} daysBack={daysBack} digest={digests[r.role] ?? null} onDigest={(d) => setDigests((x) => ({ ...x, [r.role]: d }))} />
              ))}
            </Grid>
          ) : roles.length > 0 ? (
            <Text>Pick up to two audiences above to compare them.</Text>
          ) : (
            <Text>No on-brand posts with an author role in this window.</Text>
          )}
        </>
      )}
    </>
  );
}
