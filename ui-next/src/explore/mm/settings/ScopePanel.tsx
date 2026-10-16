import { useEffect, useState } from 'react';
import { Banner, Button, Panel, Stack, TextArea } from '@aunoo/ui';
import { updateMarket } from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import type { MmContext } from '../context';

/**
 * What the tracked vendor group covers. The investor report quotes this word for word when it's
 * set, and says plainly that scope was never defined when it isn't; it never guesses a boundary
 * from who happens to be in the registry.
 */
export function ScopePanel({ ctx, onSaved }: { ctx: MmContext; onSaved: () => void }) {
  const m = ctx.market;
  const [scope, setScope] = useState('');
  const [inclusion, setInclusion] = useState('');
  const [exclusion, setExclusion] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  // Start from what's saved, so the form never looks as if nothing was ever set
  useEffect(() => {
    setScope(m.market_scope_description ?? '');
    setInclusion(m.inclusion_criteria ?? '');
    setExclusion(m.exclusion_criteria ?? '');
  }, [m.id, m.market_scope_description, m.inclusion_criteria, m.exclusion_criteria]);

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      await updateMarket(m.id, { market_scope_description: scope, inclusion_criteria: inclusion, exclusion_criteria: exclusion });
      setMsg({ tone: 'success', text: 'Market scope saved.' });
      ctx.notify('Market scope saved');
      onSaved();
    } catch (e) {
      setMsg({ tone: 'error', text: `Not saved: ${errorText(e)}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="Market scope"
      description="What the tracked vendor group actually covers. The investor report quotes this word for word when it’s set, and says plainly that scope was never defined when it isn’t. It never guesses a boundary from who happens to be in the registry."
    >
      <Stack gap="md">
        <TextArea
          label="Scope description"
          rows={4}
          value={scope}
          onChange={setScope}
          placeholder="The tracked vendor cohort covers companies for which AI-led investigation, triage or response automation is a material part of the product proposition. Broader security vendors may appear in market coverage without being included in the tracked cohort."
        />
        <TextArea label="Inclusion criteria (optional)" rows={2} value={inclusion} onChange={setInclusion} />
        <TextArea label="Exclusion criteria (optional)" rows={2} value={exclusion} onChange={setExclusion} />
        {msg && <Banner tone={msg.tone} title={msg.tone === 'error' ? 'Something went wrong' : 'Saved'} description={msg.text} />}
        <div><Button busy={busy} disabled={busy} onClick={() => void save()}>Save scope</Button></div>
      </Stack>
    </Panel>
  );
}
