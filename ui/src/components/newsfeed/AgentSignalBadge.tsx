/**
 * AgentSignalBadge Component
 * Displays a visual indicator when articles have been tagged by Research Agents
 */

import { Bot } from 'lucide-react';

interface AgentSignalBadgeProps {
  agentNames: string[];
  compact?: boolean;
}

/**
 * Extracts SIGNAL_* tags from an article's tags field
 */
export function extractSignalTags(tags: string | string[] | undefined | null): string[] {
  if (!tags) return [];
  const tagArray = Array.isArray(tags)
    ? tags
    : String(tags).split(',').map(t => t.trim());
  return tagArray.filter(tag => tag.startsWith('SIGNAL_'));
}

/**
 * Formats agent name for display (removes SIGNAL_ prefix and underscores)
 */
function formatAgentName(signalTag: string): string {
  return signalTag
    .replace('SIGNAL_', '')
    .replace(/_/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/**
 * Badge component showing that an article was matched by a Research Agent
 */
export function AgentSignalBadge({ agentNames, compact = false }: AgentSignalBadgeProps) {
  if (agentNames.length === 0) return null;

  const formattedNames = agentNames.map(formatAgentName);
  const displayText = compact
    ? `${agentNames.length}`
    : formattedNames[0];

  const tooltipText = formattedNames.length > 1
    ? `Matched by: ${formattedNames.join(', ')}`
    : `Matched by: ${formattedNames[0]}`;

  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-pink-100 text-pink-700 text-xs font-medium rounded"
      title={tooltipText}
    >
      <Bot className="w-3 h-3" />
      {displayText}
    </span>
  );
}
