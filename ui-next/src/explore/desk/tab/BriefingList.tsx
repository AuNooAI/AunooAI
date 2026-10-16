import { Button, Chip, Grid, Icon, IconButton, Panel, Stack, Text } from '@aunoo/ui';
import type { BriefingSummary } from '@monolith/briefingDeskApi';
import { fmtDate } from './format';
import './desk.css';

/** The briefings as cards, newest change first (the server's order) */
export function BriefingList({ briefings, onOpen, onDelete, busyId }: {
  briefings: BriefingSummary[];
  onOpen: (id: number) => void;
  onDelete: (b: BriefingSummary) => void;
  busyId: number | null;
}) {
  return (
    <Grid columns={3} as="ul" label="Briefings">
      {briefings.map((b) => {
        const draft = b.status === 'draft';
        const empty = b.articles_count === 0 && b.incidents_count === 0 && (b.emerging_topics_count ?? 0) === 0;
        const counts = [
          `${b.articles_count} article${b.articles_count === 1 ? '' : 's'}`,
          `${b.incidents_count} incident${b.incidents_count === 1 ? '' : 's'}`,
          b.emerging_topics_count ? `${b.emerging_topics_count} emerging theme${b.emerging_topics_count === 1 ? '' : 's'}` : '',
        ].filter(Boolean).join(' · ');
        return (
          <li key={b.id}>
            <Panel
              title={b.name}
              headingLevel={3}
              description={b.description}
              headerAside={<Chip tone={draft ? 'muted' : 'success'} size="sm">{draft ? 'Draft' : 'Finalized'}</Chip>}
            >
              <Stack gap="sm">
                <Text variant="caption">{counts}</Text>
                <Text variant="caption">{`Updated ${fmtDate(b.updated_at)}`}</Text>
                {empty && draft && <Text variant="hint">Empty. Add articles, incidents or themes with “Add to briefing” on the other tabs.</Text>}
                <Stack direction="row" justify="between" gap="sm">
                  <Button variant="secondary" size="sm" busy={busyId === b.id} iconEnd={<Icon name="CaretRight" size="sm" />} onClick={() => onOpen(b.id)}>Open</Button>
                  <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete “${b.name}”`} onClick={() => onDelete(b)} />
                </Stack>
              </Stack>
            </Panel>
          </li>
        );
      })}
    </Grid>
  );
}
