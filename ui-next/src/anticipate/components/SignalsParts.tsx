import { Stack, Text } from '@aunoo/ui';
import type { Payload } from '../lib/model';
import './signalsParts.css';

/*
 * Pieces of the old Market Signals view that the rebuild had flattened (ui/src/App.tsx,
 * 'market-signals'): impact colour coding, and the risk and opportunity cards' timeframe,
 * mitigation, value and action steps.
 */

const IMPACT_CLASS: Record<string, string> = { critical: 'high', high: 'high', medium: 'medium', low: 'low' };

/** Impact as a coloured dot and the word (red high, amber medium, blue low), as the old table coloured it */
export function ImpactLevel({ value }: { value: unknown }) {
  const s = String(value ?? '').trim();
  if (!s) return null;
  const cls = IMPACT_CLASS[s.toLowerCase()] ?? 'unknown';
  return (
    <span className="sig-impact">
      <i className={`sig-impact__dot sig-impact__dot--${cls}`} aria-hidden="true" />
      {s.charAt(0).toUpperCase() + s.slice(1)}
    </span>
  );
}

const list = (v: unknown): string[] => (Array.isArray(v) ? v : []).map((x) => (typeof x === 'string' ? x : String((x as Payload)?.action ?? (x as Payload)?.description ?? ''))).filter(Boolean);

/** The details under a risk or opportunity card: timeframe, value, and the first two steps */
export function CardExtras({ card, kind }: { card: Payload; kind: 'risk' | 'opportunity' }) {
  const steps = list(kind === 'risk' ? card.mitigation_strategies : card.action_steps).slice(0, 2);
  const timeframe = card.timeframe ? String(card.timeframe) : '';
  const value = kind === 'opportunity' && card.potential_value ? String(card.potential_value) : '';
  if (!timeframe && !value && !steps.length) return null;
  return (
    <Stack gap="sm">
      {(timeframe || value) && (
        <Text variant="caption">{[timeframe && `When: ${timeframe}`, value && `Value: ${value}`].filter(Boolean).join(' · ')}</Text>
      )}
      {steps.length > 0 && (
        <div>
          <Text variant="label" as="span">{kind === 'risk' ? 'Mitigation' : 'Actions'}</Text>
          <ul className="sig-steps">
            {steps.map((st, i) => <li key={i}><Text as="span" variant="caption">{st}</Text></li>)}
          </ul>
        </div>
      )}
    </Stack>
  );
}
