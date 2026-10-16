import { Chip, Icon } from '@aunoo/ui';

/*
 * Shows that an article was matched by an observer agent, as the old AgentSignalBadge. Agents tag
 * the articles they match with SIGNAL_<AGENT_NAME> (sometimes stored as "signal:SIGNAL_…").
 * Exported for the article lists that show these tags.
 */

export function extractSignalTags(tags: string | string[] | undefined | null): string[] {
  if (!tags) return [];
  const list = Array.isArray(tags) ? tags : String(tags).split(',').map((t) => t.trim());
  return list.map((t) => (t.includes(':') ? t.split(':').pop()! : t)).filter((t) => t.startsWith('SIGNAL_'));
}

/** "SIGNAL_SUPPLY_CHAIN_RISK" → "Supply Chain Risk" */
export const agentNameFromTag = (tag: string) =>
  tag.replace('SIGNAL_', '').split('_').filter(Boolean).map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');

export function AgentSignalBadge({ agentNames, compact = false }: { agentNames: string[]; compact?: boolean }) {
  if (!agentNames.length) return null;
  const names = agentNames.map(agentNameFromTag);
  const text = compact ? `${names.length} agent${names.length === 1 ? '' : 's'}` : names[0];
  return (
    <Chip tone="accent" size="sm" icon={<Icon name="Robot" size="sm" />} label={`Matched by ${names.join(', ')}`}>
      {text}
    </Chip>
  );
}
