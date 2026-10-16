import { useState } from 'react';
import { Banner, Button, Dialog, Icon, Skeleton, Stack, TabPanel, Tabs, Text } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { errorText } from '../../shell';
import { downloadFile, slug } from '../lib/download';
import { Events } from './Events';
import { useBrief } from './model';
import { Approval, ExecSummary, ListSection, PerTopic, WhatsChanged, useRegenerate } from './sections';

const TABS = [
  { value: 'exec', label: 'Exec summary' },
  { value: 'themes', label: 'Cross-cutting themes' },
  { value: 'framework', label: 'Decision framework' },
  { value: 'changed', label: 'What’s changed' },
  { value: 'topics', label: 'Per topic' },
  { value: 'events', label: 'Events' },
  { value: 'approval', label: 'Approval' },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cadence: string;
  periodLabel: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  /** After an approval, so the bundle card can refresh its status */
  onChanged?: () => void;
}

/**
 * Review, edit, lock and approve a bundle before it ships (the old QuarterlyBriefEditor). Locked
 * sections survive a regenerate; approval unblocks the bundle download for the recipient.
 */
export function BriefEditor({ open, onOpenChange, cadence, periodLabel, notify, askConfirm, onChanged }: Props) {
  const [tab, setTab] = useState('exec');
  const b = useBrief(cadence, periodLabel, notify);
  const regen = useRegenerate(b, notify);
  const brief = b.brief;
  const firstTopic = brief?.per_topic[0]?.topic ?? '';

  const approve = () =>
    askConfirm({
      title: 'Approve this bundle?',
      message: `Approving ${cadence} “${periodLabel}” records you as the approver and lets the recipient download it.`,
      action: 'Approve',
      onConfirm: async () => {
        if (await b.approve()) onChanged?.();
      },
    });
  const preview = () => {
    notify('Building the preview deck…');
    downloadFile(`${b.base}/preview.pptx`, `brief-preview-${slug(cadence)}-${slug(periodLabel)}.pptx`).catch((e) => notify(`No preview: ${errorText(e)}`));
  };

  const meta = [
    `${cadence} · ${periodLabel}`,
    brief?.updated_at && `updated ${new Date(brief.updated_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}`,
    brief?.review?.status && `review: ${brief.review.status.replace(/_/g, ' ')}`,
  ].filter(Boolean).join(' · ');

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="xl"
      title="Bundle brief editor"
      description={meta}
      footer={
        <Stack direction="row" justify="between" gap="sm">
          <Button variant="secondary" size="lg" iconStart={<Icon name="Eye" size="sm" />} disabled={!brief} onClick={preview}>Preview .pptx</Button>
          <Button size="lg" iconStart={<Icon name="CheckCircle" size="sm" />} disabled={!brief} onClick={approve}>Approve and release</Button>
        </Stack>
      }
    >
      {b.loading ? (
        <Skeleton lines={6} />
      ) : b.error || !brief ? (
        <Banner tone="warning" icon="Warning" title="Nothing to edit yet" description={b.error ?? 'No brief found.'} />
      ) : (
        <Stack gap="lg">
          {regen.running && <Banner tone="info" icon="ArrowsClockwise" title="Regenerating" description="Locked sections are kept. The brief reloads when it’s done." />}
          {regen.failed && <Banner tone="error" icon="WarningCircle" title="Regenerate failed" description={regen.failed} />}
          <Tabs label="Brief sections" scrollable value={tab} onValueChange={setTab} items={TABS}>
            <TabPanel value="exec"><ExecSummary b={b} regen={regen} topic={firstTopic} /></TabPanel>
            <TabPanel value="themes">
              <ListSection b={b} regen={regen} rootKey="cross_cutting_themes" title="Cross-cutting themes" description="Themes that run across the topics." fields={['lead', 'body']} askConfirm={askConfirm} />
            </TabPanel>
            <TabPanel value="framework">
              <ListSection b={b} regen={regen} rootKey="executive_decision_framework" title="Executive decision framework" description="Principles for the reader’s decisions." fields={['headline', 'body']} askConfirm={askConfirm} />
            </TabPanel>
            <TabPanel value="changed"><WhatsChanged b={b} /></TabPanel>
            <TabPanel value="topics"><PerTopic b={b} regen={regen} /></TabPanel>
            <TabPanel value="events">{tab === 'events' && <Events b={b} regen={regen} notify={notify} askConfirm={askConfirm} />}</TabPanel>
            <TabPanel value="approval"><Approval b={b} onApprove={approve} /></TabPanel>
          </Tabs>
          <Text variant="caption">Every save is recorded in the brief’s edit history with your name.</Text>
        </Stack>
      )}
    </Dialog>
  );
}
