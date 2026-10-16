import { useState } from 'react';
import { ActivityRow, Button, Eyebrow, Stack, Text, TextArea, TextField } from '@aunoo/ui';
import { errorText, session } from '../../../shell';
import { addIncidentNote, type SavedIncident } from '../../feed/api';
import { nameOf } from './helpers';

/*
 * Analyst notes on a saved incident, newest first, as the old AnalystNotesSection. The analyst name
 * is remembered in this browser under the same key the old page used (aunoo_analyst_name). A note
 * targets the saved row by its id; the old page dropped that id when it loaded the list, so a note
 * fell back to matching by name and topic.
 */

const NAME_KEY = 'aunoo_analyst_name';
const storedName = () => {
  try {
    return localStorage.getItem(NAME_KEY) || session.user.username || '';
  } catch {
    return session.user.username || '';
  }
};

interface Note { id: string; timestamp: string; analyst: string; comment: string }

export function IncidentNotes({ incident, topic, notify }: { incident: SavedIncident; topic: string; notify: (m: string) => void }) {
  const [notes, setNotes] = useState<Note[]>((incident.analyst_notes as Note[] | undefined) ?? []);
  const [analyst, setAnalyst] = useState(storedName);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  const add = async () => {
    if (!analyst.trim() || !comment.trim()) return;
    setBusy(true);
    try {
      try {
        localStorage.setItem(NAME_KEY, analyst.trim());
      } catch {
        // remembered for this visit only
      }
      const r = await addIncidentNote(nameOf(incident), topic, analyst.trim(), comment.trim(), incident._saved_id) as { note?: Note };
      const note = r?.note ?? { id: String(Date.now()), timestamp: new Date().toISOString(), analyst: analyst.trim(), comment: comment.trim() };
      setNotes((n) => [note, ...n]);
      setComment('');
      notify('Note added');
    } catch (e) {
      notify(`Note not added: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="sm">
      <Eyebrow as="h4">{`Analyst notes (${notes.length})`}</Eyebrow>
      {notes.length > 0 ? (
        <Stack as="ul" gap="sm" label="Analyst notes">
          {notes.map((n) => (
            <ActivityRow key={n.id} as="li" primary={n.comment} secondary={n.analyst} timestamp={n.timestamp.slice(0, 16).replace('T', ' ')} dateTime={n.timestamp} />
          ))}
        </Stack>
      ) : (
        <Text variant="caption">No notes yet.</Text>
      )}
      <TextField label="Your name" value={analyst} onChange={setAnalyst} maxLength={100} />
      <TextArea label="Add a note" rows={2} value={comment} onChange={setComment} />
      <div>
        <Button size="sm" variant="secondary" disabled={busy || !analyst.trim() || !comment.trim()} onClick={() => void add()}>
          {busy ? 'Adding…' : 'Add note'}
        </Button>
      </div>
    </Stack>
  );
}
