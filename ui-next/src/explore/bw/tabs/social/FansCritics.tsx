import { useEffect, useMemo, useState } from 'react';
import { Button, Chip, Grid, Icon, IconButton, Panel, Stack, Table, Text } from '@aunoo/ui';
import type { Brand, BWSocialPost } from '@monolith/brandWatcherApi';
import { buildAccountProfile, getAccountProfile, type BWAccountProfile } from '@monolith/socialProfileApi';
import { errorText } from '../../../../shell';
import { PROFILE_PLATFORMS, brandOf, engOf, fmtCount, handleOf, platLabel, sentOf } from './helpers';
import { SplitBar } from '../../charts';

export interface Author {
  author: string;
  platform: string;
  brand: string;
  pos: number;
  neg: number;
  neu: number;
  total: number;
  net: number;
  posEng: number;
  negEng: number;
  spanDays: number;
  trend: 'up' | 'down' | 'flat' | null;
  own: boolean;
}

/**
 * On-brand (relevance ≥ 0.4) scored posts grouped by author. Fans are net-positive authors
 * ranked by advocacy (5 per aligned post + its engagement); critics net-negative ranked by damage.
 * The brand's own accounts are left out of fans. Same rules as the old tab.
 */
export function computeFansCritics(posts: BWSocialPost[], brands: Brand[]) {
  const norm = (s: string) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const ownTokens: Record<string, string[]> = {};
  for (const b of brands) ownTokens[b.display_name] = [...new Set([b.name, ...(b.brand_keywords ?? [])].map(norm).filter((t) => t.length >= 3))];
  const isOwn = (handle: string, brand: string) => {
    const lead = norm((handle || '').split('.')[0]);
    return !!lead && (ownTokens[brand] ?? []).some((t) => lead.startsWith(t));
  };
  const dates = posts.map((p) => p.publication_date || '').filter(Boolean).sort();
  const mid = dates.length ? dates[Math.floor(dates.length / 2)] : '';
  const by: Record<string, Omit<Author, 'net' | 'spanDays' | 'trend' | 'own'> & { first: string; last: string; recent: number; prior: number }> = {};
  for (const p of posts) {
    if ((p.relevance ?? 0) < 0.4) continue;
    const s = sentOf(p.sentiment);
    if (s === 'unrated') continue;
    // Only real handles: the source fallback ("xpoz:instagram") isn't an account
    const handle = (handleOf(p) || '').trim();
    if (!handle || handle === 'unknown' || handle.includes(':')) continue;
    const key = `${p.platform}:${handle.toLowerCase()}`;
    const a = (by[key] ||= { author: handle, platform: p.platform, brand: brandOf(p), pos: 0, neg: 0, neu: 0, total: 0, posEng: 0, negEng: 0, first: '', last: '', recent: 0, prior: 0 });
    if (s === 'positive') a.pos++;
    else if (s === 'negative') a.neg++;
    else a.neu++;
    a.total++;
    if (s !== 'neutral') {
      if (s === 'positive') a.posEng += engOf(p);
      else a.negEng += engOf(p);
      const d = p.publication_date || '';
      if (d) {
        if (!a.first || d < a.first) a.first = d;
        if (!a.last || d > a.last) a.last = d;
        if (mid && d >= mid) a.recent++;
        else a.prior++;
      }
    }
  }
  const BASE = 5;
  const all = Object.values(by).map((a) => ({
    ...a,
    net: a.pos - a.neg,
    own: isOwn(a.author, a.brand),
    spanDays: a.first && a.last ? Math.max(0, Math.round((new Date(a.last).getTime() - new Date(a.first).getTime()) / 86400e3)) : 0,
    trend: a.recent + a.prior >= 2 ? (a.recent > a.prior ? 'up' : a.recent < a.prior ? 'down' : 'flat') : null,
  })) as (Author & { recent: number; prior: number })[];
  const fans = all.filter((a) => a.net > 0 && !a.own).sort((x, y) => y.pos * BASE + y.posEng - (x.pos * BASE + x.posEng) || y.pos - x.pos).slice(0, 10);
  const critics = all.filter((a) => a.net < 0).sort((x, y) => y.neg * BASE + y.negEng - (x.neg * BASE + x.negEng) || y.neg - x.neg).slice(0, 10);
  return { fans, critics, authors: all.length, ownHidden: all.filter((a) => a.net > 0 && a.own).length };
}

/** A journalist critic reads differently from an unhappy customer: a guess from the bio, as the old tab made. */
function typeOf(p: BWAccountProfile | undefined) {
  const bio = (p?.bio || '').toLowerCase();
  if (!bio) return null;
  if (/journalist|reporter|editor(?!ial board)|columnist|correspondent|newsroom|covering .* for/.test(bio)) return 'Press';
  if (/professor|researcher|ph\.?d|scientist|academic|lecturer|postdoc|faculty/.test(bio)) return 'Academic';
  if (/librar/.test(bio)) return 'Librarian';
  if (/\bauthor\b|writer|novelist/.test(bio)) return 'Author';
  return null;
}

type Profiles = Record<string, BWAccountProfile | 'missing'>;
const keyOf = (a: { platform: string; author: string }) => `${a.platform}:${a.author.toLowerCase()}`;

interface Props {
  posts: BWSocialPost[];
  brands: Brand[];
  focusBrand: string | null;
  onProfile: (platform: string, handle: string) => void;
  onSeePosts: (platform: string, author: string) => void;
  onAttachProfile: (p: BWAccountProfile) => void;
  notify: (m: string) => void;
}

export function FansCritics({ posts, brands, focusBrand, onProfile, onSeePosts, onAttachProfile, notify }: Props) {
  const fc = useMemo(() => computeFansCritics(posts, brands), [posts, brands]);
  const [profiles, setProfiles] = useState<Profiles>({});
  const [building, setBuilding] = useState(false);
  const multiBrand = new Set([...fc.fans, ...fc.critics].map((a) => a.brand)).size > 1;
  const maxVol = Math.max(1, ...fc.fans.map((a) => a.total), ...fc.critics.map((a) => a.total));
  const top = useMemo(() => [...fc.critics.slice(0, 5), ...fc.fans.slice(0, 5)].filter((a) => PROFILE_PLATFORMS.includes(a.platform)), [fc]);

  // Stored profiles only: a database read, no paid lookup
  useEffect(() => {
    let stale = false;
    for (const a of top) {
      const k = keyOf(a);
      if (profiles[k]) continue;
      getAccountProfile(a.platform, a.author).then(
        (p) => !stale && setProfiles((x) => ({ ...x, [k]: p })),
        () => !stale && setProfiles((x) => ({ ...x, [k]: 'missing' })),
      );
    }
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [top]);

  const missing = top.filter((a) => profiles[keyOf(a)] === 'missing');
  // Builds from Xpoz (a paid lookup), critics first, four at a time as the old tab did
  const buildMissing = async () => {
    setBuilding(true);
    let built = 0;
    for (const a of missing.slice(0, 4)) {
      try {
        const p = await buildAccountProfile(a.platform, a.author, focusBrand);
        setProfiles((x) => ({ ...x, [keyOf(a)]: p }));
        built++;
      } catch (e) {
        notify(`@${a.author}: ${errorText(e)}`);
      }
    }
    setBuilding(false);
    if (built) notify(`${built} ${built === 1 ? 'profile' : 'profiles'} built`);
  };

  if (!fc.fans.length && !fc.critics.length) return null;

  const table = (rows: Author[], kind: 'fan' | 'critic') => (
    <Table<Author>
      caption={kind === 'fan' ? 'Top fans' : 'Top critics'}
      rows={rows}
      rowKey={keyOf}
      emptyText={kind === 'fan' ? 'No net-positive authors in this window.' : 'No net-negative authors in this window.'}
      columns={[
        {
          key: 'author', header: 'Account', rowHeader: true, wrap: true,
          render: (a) => {
            const p = profiles[keyOf(a)];
            const prof = p && p !== 'missing' ? p : undefined;
            const t = typeOf(prof);
            return (
              <Stack gap="sm">
                <Stack direction="row" gap="sm">
                  {PROFILE_PLATFORMS.includes(a.platform)
                    ? <Button variant="ghost" size="sm" onClick={() => onProfile(a.platform, a.author)}>@{a.author}</Button>
                    : <Text as="span">@{a.author}</Text>}
                </Stack>
                <Stack direction="row" gap="sm">
                  <Chip size="sm" tone="muted">{platLabel(a.platform)}</Chip>
                  {multiBrand && <Chip size="sm" tone="neutral">{a.brand}</Chip>}
                  {prof?.verified && <Chip size="sm" tone="info">Verified</Chip>}
                  {prof?.followers_count != null && <Chip size="sm" tone="muted">{fmtCount(prof.followers_count)} followers</Chip>}
                  {t && <Chip size="sm" tone={t === 'Press' ? 'error' : 'neutral'}>{t}</Chip>}
                  {a.trend === 'up' && <Chip size="sm" tone={kind === 'critic' ? 'error' : 'success'}>Posting more lately</Chip>}
                  {a.trend === 'down' && <Chip size="sm" tone="muted">Posting less lately</Chip>}
                </Stack>
              </Stack>
            );
          },
        },
        { key: 'net', header: 'Net', align: 'end', render: (a) => `${a.net > 0 ? '+' : ''}${a.net}` },
        // As the old list: each author's split, the bar's length set by how much they post
        {
          key: 'mix', header: 'Positive / neutral / negative',
          render: (a) => (
            <Stack gap="sm">
              <SplitBar pos={a.pos} neu={a.neu} neg={a.neg} scale={a.total / maxVol} label={`@${a.author}`} />
              <Text as="span" variant="caption">{`${a.pos} / ${a.neu} / ${a.neg}`}</Text>
            </Stack>
          ),
        },
        { key: 'reach', header: kind === 'fan' ? 'Reach of positive posts' : 'Reach of negative posts', align: 'end', render: (a) => fmtCount(kind === 'fan' ? a.posEng : a.negEng) },
        {
          key: 'actions', header: <span className="visually-hidden">Actions</span>,
          render: (a) => {
            const p = profiles[keyOf(a)];
            return (
              <Stack direction="row" gap="sm" wrap={false}>
                <IconButton icon={<Icon name="Eye" size="sm" />} label={`See posts by @${a.author}`} onClick={() => onSeePosts(a.platform, a.author)} />
                {p && p !== 'missing' && <IconButton icon={<Icon name="ShieldCheck" size="sm" />} label={`Add @${a.author}’s profile to an incident`} onClick={() => onAttachProfile(p)} />}
              </Stack>
            );
          },
        },
      ]}
    />
  );

  return (
    <Panel
      title="Fans and critics"
      description={`${fc.authors} authors, ranked by posts and the engagement they earned${fc.ownHidden ? `. ${fc.ownHidden} of the brand’s own ${fc.ownHidden === 1 ? 'account is' : 'accounts are'} left out of fans` : ''}.`}
      headingLevel={3}
      headerAside={
        missing.length > 0 ? (
          <Button size="sm" variant="secondary" iconStart={<Icon name="User" size="sm" />} disabled={building} onClick={() => void buildMissing()}>
            {building ? 'Looking up…' : `Look up ${Math.min(4, missing.length)} missing ${Math.min(4, missing.length) === 1 ? 'profile' : 'profiles'}`}
          </Button>
        ) : undefined
      }
    >
      <Stack gap="md">
        {missing.length > 0 && <Text variant="caption">Looking up a profile reads the account from Xpoz, which uses paid credits. Stored profiles show without a lookup.</Text>}
        <Grid columns={2} stackAt="wide" gap="md">
          {table(fc.fans, 'fan')}
          {table(fc.critics, 'critic')}
        </Grid>
      </Stack>
    </Panel>
  );
}
