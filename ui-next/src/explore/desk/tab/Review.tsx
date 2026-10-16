import { useState } from 'react';
import { Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Stack, Table, Text, TextField } from '@aunoo/ui';
import type { BriefingReview, BriefingReviewFinding, DeskBriefing } from '@monolith/briefingDeskApi';
import './desk.css';

/*
 * The reviewer's account of a generated briefing, as the old Briefing Desk: an AI reviewer checks the
 * draft against its sources, and an error (a claim the sources don't support) holds it as a draft.
 */

const SEVERITY_TONE = { error: 'error', warning: 'warning', info: 'muted' } as const;
const ORDER = { error: 0, warning: 1, info: 2 } as const;
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;

export function FindingsList({ findings }: { findings: BriefingReviewFinding[] }) {
  const sorted = [...findings].sort((a, b) => ORDER[a.severity] - ORDER[b.severity]);
  return (
    <Stack as="ul" gap="sm" label="Reviewer findings">
      {sorted.map((f, i) => (
        <li key={i}>
          <Stack gap="sm">
            <Stack direction="row" gap="sm">
              <Chip tone={SEVERITY_TONE[f.severity]} size="sm">{f.severity}</Chip>
              <Text as="span" variant="caption">{f.target}</Text>
            </Stack>
            <Text>
              {f.finding}
              {f.evidence ? ` (${f.evidence})` : ''}
            </Text>
            {f.suggested_fix && <Text variant="caption">{`Fix: ${f.suggested_fix}`}</Text>}
          </Stack>
        </li>
      ))}
    </Stack>
  );
}

/** Shown on a draft the reviewer held: the findings, the held text, regenerate or finalize anyway */
export function ReviewHeld({ briefing, review, onRegenerate, onOverride, busy }: {
  briefing: DeskBriefing;
  review: BriefingReview;
  onRegenerate: () => void;
  onOverride: (note: string) => void;
  busy: boolean;
}) {
  const [note, setNote] = useState('');
  const errors = review.summary?.errors ?? review.findings.filter((f) => f.severity === 'error').length;
  const warnings = review.summary?.warnings ?? review.findings.filter((f) => f.severity === 'warning').length;
  return (
    <Stack gap="md">
      <Banner
        tone="error"
        title={`The reviewer held this briefing: ${plural(errors, 'error')}${warnings ? `, ${plural(warnings, 'warning')}` : ''}`}
        description="The summary was written but not finalized. Each error is a claim the sources don’t support. Write it again, or finalize it as it stands and edit the text afterwards."
      />
      <FindingsList findings={review.findings} />
      {briefing.synthesis && (
        <Collapsible>
          <CollapsibleTrigger variant="ghost" size="sm">Show the held summary</CollapsibleTrigger>
          <CollapsibleContent>
            <Text as="div" variant="caption"><p className="desk-held">{briefing.synthesis}</p></Text>
          </CollapsibleContent>
        </Collapsible>
      )}
      <Stack gap="sm">
        <TextField label="Reason for finalizing anyway" hint="Your name and this reason are stored on the briefing." value={note} onChange={setNote} maxLength={500} />
        <Stack direction="row" gap="sm">
          <Button variant="secondary" disabled={busy} onClick={onRegenerate}>Write it again with AI</Button>
          <Button variant="danger" disabled={busy || !note.trim()} onClick={() => onOverride(note.trim())}>Finalize anyway</Button>
        </Stack>
      </Stack>
    </Stack>
  );
}

const RESULT: Record<string, string> = {
  approved: 'clean',
  approved_with_warnings: 'warnings only',
  revision_requested: 'held',
  review_failed: 'review failed',
};

/** One line on how the review went, with the findings and repair passes on request */
export function ReviewNote({ review }: { review: BriefingReview }) {
  const errors = review.summary?.errors ?? 0;
  const warnings = review.summary?.warnings ?? 0;
  let label: string;
  if (review.status === 'review_failed') label = `The reviewer didn’t run${review.error ? ` (${review.error})` : ''}`;
  else if (review.override) label = `Finalized over ${plural(errors, 'reviewer error')} by ${review.override.by}${review.override.note ? `: ${review.override.note}` : ''}`;
  else if (errors) label = `Held by the reviewer: ${plural(errors, 'error')}${warnings ? `, ${plural(warnings, 'warning')}` : ''}`;
  else if (warnings) label = `Reviewed: ${plural(warnings, 'warning')}, no errors`;
  else label = 'Reviewed: no findings';

  const rounds = review.repair_rounds ?? [];
  const kept = review.repair_kept_round ?? 0;
  let repairs = '';
  if (rounds.length) {
    const dateFixes = rounds.filter((r) => r.kind === 'date_fix').length;
    const writer = rounds.length - dateFixes;
    const kinds = [dateFixes ? `${dateFixes} date fix${dateFixes === 1 ? '' : 'es'}` : '', writer ? `${writer} by the writer` : ''].filter(Boolean).join(', ');
    repairs = `${rounds.length} repair pass${rounds.length === 1 ? '' : 'es'}${kinds ? ` (${kinds})` : ''}; ${kept ? `kept pass ${kept}` : 'kept the first draft'}`;
    if (review.confirmation && (review.confirmation.confirmed || review.confirmation.withdrawn)) {
      repairs += `; reviewer errors checked again: ${review.confirmation.confirmed} confirmed, ${review.confirmation.withdrawn} withdrawn`;
    }
  }
  const rows = rounds.length
    ? [
      { key: '0', label: 'First draft', errors: rounds[0].errors_before, warnings: rounds[0].warnings_before, result: '', round: 0 },
      ...rounds.map((r) => ({
        key: String(r.round),
        label: r.kind === 'date_fix' ? `${r.round}: date fix${r.fixed ? ` (${plural(r.fixed, 'sentence')})` : ''}` : `${r.round}: writer`,
        errors: r.errors_after,
        warnings: r.warnings_after,
        result: [RESULT[r.status || ''] || r.status || '', r.stopped === 'regression' ? 'stopped: this pass added errors' : r.status === 'repair_failed' ? 'the writer returned nothing usable' : ''].filter(Boolean).join('; '),
        round: r.round,
      })),
    ]
    : [];

  return (
    <Stack gap="sm">
      <Text variant="caption">{label}</Text>
      {review.findings.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger variant="ghost" size="sm">{`Show the ${plural(review.findings.length, 'finding')}`}</CollapsibleTrigger>
          <CollapsibleContent><FindingsList findings={review.findings} /></CollapsibleContent>
        </Collapsible>
      )}
      {rows.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger variant="ghost" size="sm" className="desk-wrap-trigger">{repairs}</CollapsibleTrigger>
          <CollapsibleContent>
            <Table
              caption="Repair passes"
              hideCaption
              rows={rows}
              rowKey={(r) => r.key}
              columns={[
                { key: 'label', header: 'Pass', rowHeader: true, render: (r) => `${r.label}${r.round === kept ? ' (kept)' : ''}` },
                { key: 'errors', header: 'Errors', align: 'end' },
                { key: 'warnings', header: 'Warnings', align: 'end' },
                { key: 'result', header: 'Result', wrap: true },
              ]}
            />
          </CollapsibleContent>
        </Collapsible>
      )}
    </Stack>
  );
}
