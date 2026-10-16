import { ArticleCard, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Icon, IconButton, Stack, Text } from '@aunoo/ui';
import type { ResearchAgent, SignalAlert } from '@monolith/researchAgentsApi';
import { when } from './schedules';
import './agents.css';

/*
 * One agent: its state and buttons, and when opened, its instruction and unread matches with the
 * AI's reason for each. As the old agent card in ResearchAgentsSection.
 */

const LEVEL: Record<string, { label: string; tone: 'error' | 'warning' | 'success' | 'muted' }> = {
  high: { label: 'High', tone: 'error' },
  medium: { label: 'Medium', tone: 'warning' },
  low: { label: 'Low', tone: 'success' },
};

interface Props {
  agent: ResearchAgent;
  matches: SignalAlert[];
  running: boolean;
  /** Another run is going, so starting this one waits */
  busy: boolean;
  onRun: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onDismiss: (alertId: number) => void;
  onDismissAll: () => void;
}

export function AgentCard({ agent, matches, running, busy, onRun, onEdit, onDelete, onDismiss, onDismissAll }: Props) {
  return (
    <Collapsible>
      <Stack gap="sm">
        <Stack direction="row" justify="between" gap="sm">
          <Stack gap="sm">
            <Stack direction="row" gap="sm">
              <CollapsibleTrigger variant="ghost" size="sm" className="agents-wrap-trigger">{agent.name}</CollapsibleTrigger>
              <Chip size="sm" tone={agent.is_active ? 'success' : 'muted'}>{agent.is_active ? 'Active' : 'Paused'}</Chip>
              {agent.topic && <Chip size="sm" tone="info">{agent.topic}</Chip>}
              {matches.length > 0 && <Chip size="sm" tone="accent">{`${matches.length} unread match${matches.length === 1 ? '' : 'es'}`}</Chip>}
              {running && <Chip size="sm" tone="info">Running…</Chip>}
            </Stack>
            {(agent.description || agent.last_run_at) && (
              <Text variant="caption">
                {[agent.description, agent.last_run_at ? `Last run ${when(agent.last_run_at)}${agent.last_run_status === 'error' ? ', failed' : ''}` : null].filter(Boolean).join(' · ')}
              </Text>
            )}
          </Stack>
          <Stack direction="row" gap="sm" wrap={false}>
            <IconButton
              icon={<Icon name="Play" size="sm" />}
              label={!agent.is_active ? `${agent.name} is paused` : running ? `${agent.name} is running` : `Run ${agent.name}`}
              disabled={running || busy || !agent.is_active}
              onClick={onRun}
            />
            <IconButton icon={<Icon name="PencilSimple" size="sm" />} label={`Edit ${agent.name}`} onClick={onEdit} />
            <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete ${agent.name}`} onClick={onDelete} />
          </Stack>
        </Stack>
        <CollapsibleContent>
          <Stack gap="md">
            <Stack gap="sm">
              <Text variant="label">What it looks for</Text>
              <p className="ag-instruction">{agent.instruction}</p>
            </Stack>
            {matches.length === 0 ? (
              <Text variant="caption">No unread matches. Run the agent to read recent articles.</Text>
            ) : (
              <Stack gap="sm">
                <Stack direction="row" justify="between" gap="sm">
                  <Text variant="label">{`Unread matches (${matches.length})`}</Text>
                  <Button variant="ghost" size="sm" iconStart={<Icon name="CheckCircle" size="sm" />} onClick={onDismissAll}>Dismiss all for this agent</Button>
                </Stack>
                <Stack as="ul" gap="sm" label={`Matches for ${agent.name}`}>
                  {matches.map((m) => {
                    const lvl = LEVEL[m.threat_level?.toLowerCase()] ?? { label: m.threat_level || 'Info', tone: 'muted' as const };
                    return (
                      <ArticleCard
                        key={m.id}
                        as="li"
                        variant="row"
                        headingLevel={4}
                        title={m.article_title || m.article_uri}
                        href={m.article_uri}
                        meta={[m.article_source, m.article_date ? new Date(m.article_date).toLocaleDateString('en-GB') : null].filter(Boolean).join(' · ') || undefined}
                        flag={<Chip size="sm" tone={lvl.tone}>{`${lvl.label} priority`}</Chip>}
                        summary={m.reasoning ? `Why it matches: ${m.reasoning}` : undefined}
                        actions={[{ id: 'dismiss', label: 'Dismiss', icon: 'CheckCircle' }]}
                        actionsLabel={`Actions for ${m.article_title}`}
                        onAction={() => onDismiss(m.id)}
                      />
                    );
                  })}
                </Stack>
              </Stack>
            )}
          </Stack>
        </CollapsibleContent>
      </Stack>
    </Collapsible>
  );
}
