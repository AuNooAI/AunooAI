import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, FilterChipRow, Grid, Select, Stack, Text, TextField } from '@aunoo/ui';
import { getSocialPosts, type Brand, type BWSocialPost } from '@monolith/brandWatcherApi';
import { listAccountProfiles, type BWAccountProfile } from '@monolith/socialProfileApi';
import { stripSocialMarkdown } from '@monolith/socialText';
import { errorText } from '../../../../shell';
import { brandOf, download, sentOf } from './helpers';

const SENT_ORDER: Record<string, number> = { positive: 0, neutral: 1, negative: 2, unrated: 3 };
const iso = (d: Date) => d.toISOString().slice(0, 10);

/**
 * Posts as CSV, ordered primary brand first, then fans to critics, then newest. Authors with an
 * account profile get its followers, verified flag, tags, note and summary (as the old export).
 */
function toCsv(posts: BWSocialPost[], rank: Record<string, number>, profiles: BWAccountProfile[]) {
  const canon = (h: string) => (h || '').trim().replace(/^https?:\/\/(www\.)?[^/]+\//, '').replace(/^@/, '').replace(/\/+$/, '').replace(/^u\//i, '').split('/')[0].toLowerCase();
  const byHandle = new Map(profiles.map((p) => [`${(p.platform || '').toLowerCase()}|${p.handle_canonical || canon(p.handle)}`, p]));
  const rows = [...posts].sort((a, b) =>
    (rank[brandOf(a)] ?? 99) - (rank[brandOf(b)] ?? 99)
    || (SENT_ORDER[sentOf(a.sentiment)] ?? 9) - (SENT_ORDER[sentOf(b.sentiment)] ?? 9)
    || (b.publication_date || '').localeCompare(a.publication_date || ''));
  const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const one = (s: string) => s.replace(/\s+/g, ' ').trim();
  const header = ['brand', 'sentiment', 'keywords', 'platform', 'author', 'date', 'relevance', 'likes', 'reposts', 'comments', 'plays', 'text', 'url',
    'author_followers', 'author_verified', 'author_tags', 'author_note', 'author_profile'];
  const lines = [header.map(esc).join(',')];
  for (const p of rows) {
    const sm = p.social_meta || {};
    const prof = byHandle.get(`${(p.platform || '').toLowerCase()}|${canon(sm.author || '')}`);
    lines.push([
      brandOf(p), p.sentiment || sentOf(p.sentiment), (p.matched_keywords ?? []).join('; '), p.platform, sm.author || '', (p.publication_date || '').slice(0, 10),
      p.relevance ?? '', sm.likes ?? '', sm.reposts ?? '', sm.comments ?? '', sm.plays ?? '', stripSocialMarkdown(p.summary || p.title || ''), p.uri,
      prof?.followers_count ?? '', prof ? (prof.verified ? 'yes' : 'no') : '', (prof?.tags ?? []).join('; '), one(prof?.annotation?.text || ''), one(prof?.summary || ''),
    ].map(esc).join(','));
  }
  return lines.join('\n');
}

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  brands: Brand[];
  preselected: number[];
  notify: (m: string) => void;
}

export function ExportDialog({ open, onOpenChange, brands, preselected, notify }: Props) {
  const [picked, setPicked] = useState<string[]>([]);
  const [sents, setSents] = useState<string[]>([]);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [rel, setRel] = useState('onbrand');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ordered = [...brands].sort((a, b) => Number(!!b.is_primary) - Number(!!a.is_primary) || a.display_name.localeCompare(b.display_name));

  useEffect(() => {
    if (!open) return;
    setPicked(preselected.map(String));
    setSents([]);
    const e = new Date();
    const s = new Date();
    s.setDate(e.getDate() - 30);
    setStart(iso(s));
    setEnd(iso(e));
    setRel('onbrand');
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const quick = (days: number) => {
    const e = new Date();
    const s = new Date();
    s.setDate(e.getDate() - days);
    setStart(iso(s));
    setEnd(iso(e));
  };

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const chosen = picked.length ? brands.filter((b) => picked.includes(String(b.id))) : brands;
      const topics = chosen.map((b) => `Brand Monitoring ${b.display_name}`);
      // The full matching set, not the posts on screen
      const data = await getSocialPosts(topics.length ? topics : undefined, 30, rel === 'onbrand' ? 0.4 : 0, undefined, rel === 'all', {
        startDate: start || undefined, endDate: end || undefined, limit: 20000,
      });
      let posts = data.posts ?? [];
      if (sents.length) posts = posts.filter((p) => sents.includes(sentOf(p.sentiment)));
      if (!posts.length) {
        setError('No posts match these choices.');
        return;
      }
      // Account profiles are optional; a site without them exports without author columns filled
      const profiles = await listAccountProfiles().catch(() => [] as BWAccountProfile[]);
      const rank = Object.fromEntries(ordered.map((b, i) => [b.display_name, i]));
      const suffix = chosen.length === 1 ? chosen[0].display_name.toLowerCase().replace(/\s+/g, '-') : `${chosen.length || 'all'}-brands`;
      download(`social-posts-${suffix}-${iso(new Date())}.csv`, toCsv(posts, rank, profiles));
      notify(`${posts.length} posts exported`);
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Export social posts"
      description="A CSV of every matching post, not just the ones on screen."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" disabled={busy} onClick={() => void run()}>{busy ? 'Exporting…' : 'Download CSV'}</Button>
        </>
      }
    >
      <Stack gap="lg">
        {error && <Banner tone="warning" title="Nothing exported" description={error} />}
        <FilterChipRow label="Brands" allLabel="All brands" options={ordered.map((b) => ({ value: String(b.id), label: `${b.display_name}${b.is_primary ? ' (primary)' : ''}` }))} selected={picked} onChange={setPicked} maxVisible={20} />
        <FilterChipRow
          label="Sentiment"
          options={[{ value: 'positive', label: 'Positive' }, { value: 'neutral', label: 'Neutral' }, { value: 'negative', label: 'Negative' }, { value: 'unrated', label: 'Not scored' }]}
          selected={sents}
          onChange={setSents}
        />
        <Stack gap="sm">
          <Grid columns={2} stackAt="small" gap="md">
            <TextField label="From" type="date" value={start} max={end || undefined} onChange={setStart} />
            <TextField label="To" type="date" value={end} min={start || undefined} onChange={setEnd} />
          </Grid>
          <Stack direction="row" gap="sm">
            {[7, 30, 90, 180, 365].map((d) => <Button key={d} variant="ghost" size="sm" onClick={() => quick(d)}>{d < 365 ? `Last ${d} days` : 'Last year'}</Button>)}
          </Stack>
        </Stack>
        <Select
          label="Include"
          fullWidth
          options={[
            { value: 'onbrand', label: 'On-brand posts only (relevance 0.4 or more)' },
            { value: 'scored', label: 'All scored posts, including off-topic ones' },
            { value: 'all', label: 'Everything, including posts not yet scored' },
          ]}
          value={rel}
          onValueChange={setRel}
        />
        <Text variant="caption">Leaving brands or sentiment on “All” exports every one.</Text>
      </Stack>
    </Dialog>
  );
}
