import { useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Dialog, DialogClose, Stack, Text, TextField } from '@aunoo/ui';
import { api, errorText } from '../../shell';

/*
 * Share by email, for every Explore page: a port of the old ui/src/components/ShareModal.tsx onto
 * the same /api/share/* routes. The payload is the body the matching route takes, minus `to_email`,
 * which this dialog adds. The recipient is remembered under the old key, so it carries over.
 */

export type ShareKind =
  | 'article' | 'briefing' | 'briefing-card' | 'emerging-topic' | 'executive-summary'
  | 'incident' | 'incidents' | 'narrative' | 'desk-briefing';

export interface ShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: ShareKind;
  /** What is being shared, in the shape the matching /api/share/<kind> route takes (see the old ShareModal) */
  payload: Record<string, unknown>;
  /** Shown in the dialog title, e.g. the article or briefing name */
  title?: string;
  notify?: (m: string) => void;
}

const EMAIL_KEY = 'aunoo_share_email';
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const KIND_LABEL: Record<ShareKind, string> = {
  article: 'article', briefing: 'briefing', 'briefing-card': 'briefing story', 'emerging-topic': 'emerging theme',
  'executive-summary': 'executive summary', incident: 'incident', incidents: 'incidents', narrative: 'narrative',
  'desk-briefing': 'briefing',
};

function endpointFor(kind: ShareKind, payload: Record<string, unknown>) {
  // The Briefing Desk builds the email on the server from the stored briefing
  if (kind === 'desk-briefing') return `/api/desk-briefings/${payload.briefing_id}/share`;
  return `/api/share/${kind}`;
}

function notesCount(kind: ShareKind, payload: Record<string, unknown>) {
  if (kind === 'incident') return (payload.analyst_notes as unknown[] | undefined)?.length ?? 0;
  if (kind === 'incidents') return ((payload.incidents as { analyst_notes?: unknown[] }[] | undefined) ?? []).reduce((n, i) => n + (i.analyst_notes?.length ?? 0), 0);
  return 0;
}

export function ShareDialog({ open, onOpenChange, kind, payload, title, notify }: ShareDialogProps) {
  const [email, setEmail] = useState('');
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [includeNotes, setIncludeNotes] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    try {
      setEmail(localStorage.getItem(EMAIL_KEY) ?? '');
    } catch {
      // per visit only
    }
    setConfigured(null);
    api<{ configured?: boolean }>('/api/email/status').then((r) => setConfigured(!!r.configured), () => setConfigured(false));
  }, [open]);

  const notes = notesCount(kind, payload);

  const send = async () => {
    const to = email.trim();
    if (!EMAIL_RE.test(to)) {
      setError('Enter a valid email address.');
      return;
    }
    setSending(true);
    setError(null);
    try {
      localStorage.setItem(EMAIL_KEY, to);
    } catch {
      // per visit only
    }
    let body: Record<string, unknown> = { ...payload, to_email: to };
    if (!includeNotes && kind === 'incident') body = { ...body, analyst_notes: undefined };
    if (!includeNotes && kind === 'incidents') {
      body = { ...body, incidents: ((payload.incidents as Record<string, unknown>[]) ?? []).map((i) => ({ ...i, analyst_notes: undefined })) };
    }
    if (kind === 'desk-briefing') body = { to_email: to };
    try {
      await api(endpointFor(kind, payload), { method: 'POST', json: body });
      notify?.(`Sent to ${to}`);
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Share this ${KIND_LABEL[kind]} by email`}
      description={title}
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={sending} disabled={sending || configured === false || !email.trim()} onClick={() => void send()}>Send email</Button>
        </>
      }
    >
      <Stack gap="md">
        {configured === false && (
          <Banner tone="warning" title="Email isn’t set up on this site" description="An administrator needs to configure the email service before anything can be shared." />
        )}
        <TextField label="Send to" type="email" autoComplete="email" placeholder="name@company.com" value={email} onChange={setEmail} onSubmit={() => void send()} />
        {notes > 0 && (
          <Checkbox label={`Include ${notes} analyst note${notes === 1 ? '' : 's'}`} checked={includeNotes} onCheckedChange={(v) => setIncludeNotes(v === true)} />
        )}
        <Text variant="caption">This sends one email now, from the site’s own address. The address is remembered in this browser for next time.</Text>
        {error && <Banner tone="error" title="Not sent" description={error} />}
      </Stack>
    </Dialog>
  );
}
