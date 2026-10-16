import { Button, Chip, Dialog, DialogClose, SettingRow, Stack, Text } from '@aunoo/ui';
import type { Campaign } from '../api';
import { fmtDate } from '../labels';
import { ValueChips } from '../parts';

/** One campaign's details, as the old CampaignDetailModal, with a way to its articles */
export function CampaignDialog({ campaign, onClose, onArticles }: { campaign: Campaign | null; onClose: () => void; onArticles: (c: Campaign) => void }) {
  if (!campaign) return null;
  const c = campaign;
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={c.name}
      description={c.threat_actor_name ? `Attributed to ${c.threat_actor_name}` : undefined}
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>
          <Button size="lg" disabled={!c.article_count} onClick={() => onArticles(c)}>{`Show its ${c.article_count} article${c.article_count === 1 ? '' : 's'}`}</Button>
        </>
      }
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <Chip tone={c.is_active ? 'error' : 'muted'} size="sm">{c.is_active ? 'Active' : 'Over'}</Chip>
          <Text as="span" variant="caption">{`${c.threat_count} threat${c.threat_count === 1 ? '' : 's'} · ${c.article_count} article${c.article_count === 1 ? '' : 's'}`}</Text>
        </Stack>
        {c.description && <Text>{c.description}</Text>}
        {c.start_date && <SettingRow title="When" description={`${fmtDate(c.start_date)} to ${c.end_date ? fmtDate(c.end_date) : 'now'}`} />}
        {!!c.target_countries?.length && <Stack gap="sm"><Text variant="label">Target countries</Text><Stack direction="row" gap="sm"><ValueChips values={c.target_countries} /></Stack></Stack>}
        {!!c.target_industries?.length && <Stack gap="sm"><Text variant="label">Target industries</Text><Stack direction="row" gap="sm"><ValueChips values={c.target_industries} /></Stack></Stack>}
        {!!c.techniques_used?.length && <Stack gap="sm"><Text variant="label">Techniques (MITRE ATT&CK)</Text><Stack direction="row" gap="sm"><ValueChips values={c.techniques_used} /></Stack></Stack>}
        {!!c.malware_used?.length && <Stack gap="sm"><Text variant="label">Malware</Text><Stack direction="row" gap="sm"><ValueChips values={c.malware_used} /></Stack></Stack>}
      </Stack>
    </Dialog>
  );
}
