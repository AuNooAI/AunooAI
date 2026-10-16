import { useEffect, useState } from 'react';
import type { Confirm } from '@aunoo/shell';
import { Banner, Button, EmptyState, Icon, IconButton, Panel, Skeleton, Stack, Text } from '@aunoo/ui';
import type { ResearchAgent } from '@monolith/researchAgentsApi';
import { AddAgentModal } from './AddAgentModal';
import { AgentCard } from './AgentCard';
import { RunAgentDialog, type RunChoice } from './RunAgentDialog';
import { ScheduleTimeline } from './ScheduleTimeline';
import { SchedulesTable } from './SchedulesTable';
import { loadSystemSchedules, type SystemSchedule } from './schedules';
import { SignalReports } from './SignalReports';
import { useResearchAgents } from './useResearchAgents';
import { VoiceDialog } from './VoiceDialog';

/*
 * Observer agents, as the old ResearchAgentsSection: each agent has a plain-language instruction and
 * reads recent articles with the AI to flag the ones that match. Loading only reads; runs start from
 * the Run buttons and keep going on the server. The reports agents write sit at the foot.
 */

export interface ObserverAgentsProps {
  /** The single topic picked in the filter bar (unused on a dedicated Brand Watcher site) */
  topic?: string;
  /** Topic names agents can watch (a dedicated site offers only its "Brand Monitoring …" topics) */
  topics: string[];
  dedicated: boolean;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
}

export function ObserverAgents({ topic, topics, dedicated, notify, askConfirm }: ObserverAgentsProps) {
  const ra = useResearchAgents(topic, notify);
  const [adding, setAdding] = useState(false);
  const [voicing, setVoicing] = useState<{ title: string; script: string; audioUrl?: string | null; voice?: string | null } | null>(null);
  const [editing, setEditing] = useState<ResearchAgent | null>(null);
  // undefined = closed, null = run all, an agent = run that one
  const [runTarget, setRunTarget] = useState<ResearchAgent | null | undefined>(undefined);
  const [systems, setSystems] = useState<SystemSchedule[]>([]);

  // The site's own scheduled jobs, refreshed each minute as before; not on a dedicated site
  useEffect(() => {
    if (dedicated) {
      setSystems([]);
      return;
    }
    let live = true;
    const load = () => loadSystemSchedules().then((s) => live && setSystems(s), () => undefined);
    void load();
    const t = setInterval(load, 60_000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [dedicated]);

  const active = ra.agents.filter((a) => a.is_active);
  const anyRunning = ra.running.size > 0;
  const unread = ra.alerts.length;
  const runTopic = dedicated ? undefined : topic;

  const startRun = (choice: RunChoice) => {
    const target = runTarget;
    setRunTarget(undefined);
    if (target) {
      notify(`${target.name} is running. Matches appear here when it finishes.`);
      void ra.runAgent(target.id, { topic: runTopic, daysBack: choice.daysBack, tagArticles: choice.tagArticles });
    } else {
      notify(`Running ${active.length} agents. Matches appear here as they finish.`);
      void ra.runAll({ topic: runTopic, daysBack: choice.daysBack, tagArticles: choice.tagArticles, generateUnifiedReport: choice.generateUnifiedReport });
    }
  };

  const remove = (a: ResearchAgent) =>
    askConfirm({
      title: `Delete ${a.name}?`,
      message: 'The agent stops running and its schedule is removed. Reports it already wrote are kept.',
      action: 'Delete agent',
      onConfirm: () => void ra.removeAgent(a.id).then((ok) => ok && notify(`${a.name} deleted`)),
    });

  const hasSchedules = ra.agents.some((a) => a.schedule_enabled) || systems.length > 0;

  return (
    <>
      <Panel
        title="Observer agents"
        description={`${ra.agents.length} agent${ra.agents.length === 1 ? '' : 's'}${unread ? `, ${unread} unread match${unread === 1 ? '' : 'es'}` : ''}${topic && !dedicated ? `, showing ${topic}` : ''}. Each agent reads recent articles with the AI and flags the ones that match its instruction.`}
        headerAside={
          <Stack direction="row" gap="sm">
            <Button variant="secondary" iconStart={<Icon name="Play" size="sm" />} busy={anyRunning} disabled={anyRunning || active.length === 0} onClick={() => setRunTarget(null)}>
              Run all
            </Button>
            <Button iconStart={<Icon name="Plus" size="sm" />} onClick={() => setAdding(true)}>Add agent</Button>
            <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Reload agents and matches" onClick={() => void ra.refresh()} />
          </Stack>
        }
      >
        <Stack gap="md">
          {ra.error && <Banner tone="error" title="Something went wrong" description={ra.error} action={<Button variant="secondary" size="sm" onClick={ra.clearError}>Dismiss</Button>} />}
          {ra.podcasts.length > 0 && (
            <Stack gap="sm">
              <Text variant="label">Spoken summaries from the last run</Text>
              {ra.podcasts.map((p, i) => (
                <Stack key={`${p.instruction_id}-${i}`} direction="row" justify="between" gap="sm" wrap={false}>
                  <Text variant="caption">{`${p.instruction_name} (${p.matches_count} matches): ${p.content.slice(0, 240)}${p.content.length > 240 ? '…' : ''}`}</Text>
                  <Stack direction="row" gap="sm" wrap={false}>
                    {/* A run with a voice set already voiced this; otherwise voicing it is a paid step the reader starts */}
                    <IconButton
                      icon={<Icon name="SpeakerHigh" size="sm" />}
                      label={p.audio_url ? `Listen to the summary for ${p.instruction_name}` : `Voice the summary for ${p.instruction_name} (paid)`}
                      onClick={() => setVoicing({ title: `${p.instruction_name}: spoken summary`, script: p.content, audioUrl: p.audio_url, voice: p.voice_id })}
                    />
                    <IconButton icon={<Icon name="X" size="sm" />} label={`Dismiss the summary for ${p.instruction_name}`} onClick={() => ra.dismissPodcast(i)} />
                  </Stack>
                </Stack>
              ))}
            </Stack>
          )}
          {!ra.loaded ? <Skeleton variant="text" lines={5} /> : ra.agents.length === 0 ? (
            <EmptyState icon="Robot" title="No observer agents yet" action={<Button iconStart={<Icon name="Plus" size="sm" />} onClick={() => setAdding(true)}>Create your first agent</Button>}>
              An agent watches the news for something you describe in plain words, such as a threat, an opportunity or a change in a market, and flags the articles that match.
            </EmptyState>
          ) : (
            <Stack as="ul" gap="md" label="Observer agents">
              {ra.agents.map((a) => (
                <li key={a.id}>
                  <AgentCard
                    agent={a}
                    matches={ra.alerts.filter((x) => x.instruction_id === a.id)}
                    running={ra.running.has(a.id)}
                    busy={anyRunning}
                    onRun={() => setRunTarget(a)}
                    onEdit={() => setEditing(a)}
                    onDelete={() => remove(a)}
                    onDismiss={(id) => void ra.dismiss(id)}
                    onDismissAll={() => void ra.dismissAllFor(a.id)}
                  />
                </li>
              ))}
            </Stack>
          )}
        </Stack>
      </Panel>

      {(ra.agents.length > 0 || systems.length > 0) && (
        <Panel title="Schedules" description={dedicated ? 'When each agent runs next.' : 'When each agent and the site’s own scheduled jobs run next.'}>
          <Stack gap="lg">
            {hasSchedules && <ScheduleTimeline agents={ra.agents} systems={systems} />}
            <SchedulesTable agents={ra.agents} alerts={ra.alerts} running={ra.running} systems={systems} />
          </Stack>
        </Panel>
      )}

      <SignalReports topic={dedicated ? undefined : topic} notify={notify} askConfirm={askConfirm} />

      {voicing && (
        <VoiceDialog open onOpenChange={(o) => !o && setVoicing(null)} title={voicing.title} script={voicing.script} audioUrl={voicing.audioUrl} defaultVoice={voicing.voice} notify={notify} />
      )}
      <AddAgentModal
        open={adding}
        onClose={() => setAdding(false)}
        onSave={async (agent) => {
          const ok = await ra.addAgent(agent);
          if (ok) {
            setAdding(false);
            notify(`${agent.name} created`);
          }
          return ok;
        }}
        topics={topics}
        loading={ra.saving}
      />
      <AddAgentModal
        open={!!editing}
        onClose={() => setEditing(null)}
        onSave={async (agent) => {
          if (!editing) return false;
          const ok = await ra.updateAgent(editing.id, agent);
          if (ok) {
            setEditing(null);
            notify(`${agent.name} saved`);
          }
          return ok;
        }}
        topics={topics}
        loading={ra.saving}
        editAgent={editing}
      />
      <RunAgentDialog
        open={runTarget !== undefined}
        onOpenChange={(o) => !o && setRunTarget(undefined)}
        agentName={runTarget ? runTarget.name : undefined}
        activeCount={active.length}
        onRun={startRun}
      />
    </>
  );
}
