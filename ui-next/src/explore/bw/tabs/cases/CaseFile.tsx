import { useMemo, useState } from 'react';
import {
  ActivityRow, ArticleCard, Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Eyebrow, FilterChipRow, Grid, Icon,
  Menu, Panel, Select, Stack, Stat, Text, TextField, TextLink, type MenuItem,
} from '@aunoo/ui';
import { addIncidentNote, incidentFileUrl, translateForReport, updateIncident } from '@monolith/brandWatcherApi';
import { downloadIncidentReport } from './incidentReport';
import { errorText } from '../../../../shell';
import { Markdown } from '../../../../shell/Markdown';
import { RISKY_VERDICTS, VERDICT_LABEL, cleanText, hostOf, needsTranslation, synthesizeCase, type CoverageItem } from './caseSynthesis';
import { SEVERITIES, STATUSES, STATUS_HELP, sevTone, statusTone } from './ListRail';
import { SignalsChips, sigKey, useSignalsOverrides } from './signals';
import type { IncidentCase } from './useIncidentCase';

/*
 * One incident, laid out around the questions an analyst asks (old IncidentCaseFile.tsx):
 * what is happening, how big it is, what's out there, who is involved, how it unfolded,
 * and the tamper-evident record. AI-found items wait for a ✓ or ✕ before joining the case.
 * Translation of foreign-language items and the report summary call the AI, so both are buttons.
 */

const SEV_ORDER = ['low', 'medium', 'high', 'critical'];
const lowerSeverity = (s: string) => SEV_ORDER[Math.max(0, SEV_ORDER.indexOf(s) - 1)] ?? 'low';
const nf = (n: number) => (n >= 10000 ? `${Math.round(n / 1000)}k` : n.toLocaleString('en-GB'));
const PLATFORM_KEY: Record<string, string> = { Bluesky: 'bluesky', X: 'x', Reddit: 'reddit', TikTok: 'tiktok', Instagram: 'instagram' };
const suggKey = (id: number, at?: string | null) => `bw_inc_sugg_dismissed:${id}:${at ?? ''}`;

function auditLine(ev: { kind: string; note?: string | null; old_value?: string | null; new_value?: string | null }) {
  switch (ev.kind) {
    case 'note': return ev.note ?? '';
    case 'evidence_added': return `captured ${ev.new_value} evidence: ${cleanText(ev.note ?? '')}`;
    case 'created': return `opened the case (${ev.new_value})`;
    case 'agent_brief': return `wrote an assessment: ${cleanText(ev.note ?? '')}`;
    case 'enrichment': return cleanText(ev.note || 'investigation finished');
    case 'agent_suggestion': return `suggestion: ${ev.note ?? ''}`;
    default: return `${ev.kind.replace(/_/g, ' ')}: ${ev.old_value ?? '–'} → ${ev.new_value}${ev.note ? ` (${ev.note})` : ''}`;
  }
}

export function CaseFile({ c, onBack, notify, openSignals }: {
  c: IncidentCase;
  onBack: () => void;
  notify: (m: string) => void;
  openSignals: (a: { uri: string; title?: string; brand_id?: number | null }) => void;
}) {
  const inc = c.detail!;
  const syn = useMemo(() => synthesizeCase(inc, c.enrich), [inc, c.enrich]);
  const running = c.enrich?.run?.status === 'running';
  const overrides = useSignalsOverrides();
  const [platform, setPlatform] = useState<string[]>([]);
  const [translations, setTranslations] = useState<Record<string, string>>({});
  const [translating, setTranslating] = useState(false);
  const [owner, setOwner] = useState(inc.owner ?? '');
  const [hiddenSugg, setHiddenSugg] = useState(0);
  const [reporting, setReporting] = useState(false);

  const setField = (updates: Record<string, string>) =>
    updateIncident(inc.id, updates).then(c.refreshIncident, (e: unknown) => notify(`Not saved: ${errorText(e)}`));

  // Agent notes. Duplicate flags are computed live by the server (duplicate_candidates) instead
  const suggestions = (inc.timeline ?? [])
    .filter((ev) => ev.kind === 'agent_suggestion' && ev.note)
    .filter((ev) => {
      void hiddenSugg;
      try {
        return !localStorage.getItem(suggKey(inc.id, ev.at));
      } catch {
        return true;
      }
    })
    .filter((ev) => {
      const n = ev.note ?? '';
      if (/^possible duplicate of incident #/.test(n)) return false;
      if (n.startsWith('severity review:') && !['high', 'critical'].includes(inc.severity)) return false;
      return true;
    });
  const dismissSugg = (at?: string | null) => {
    try {
      localStorage.setItem(suggKey(inc.id, at), '1');
    } catch {
      // per visit only
    }
    setHiddenSugg((n) => n + 1);
  };

  const foreign = syn.coverage.filter((it) => needsTranslation(it.title) || (it.body && needsTranslation(it.body)));
  const translate = async () => {
    const items: { id: string; text: string }[] = [];
    for (const it of foreign) {
      if (needsTranslation(it.title)) items.push({ id: `${it.key}|t`, text: it.title });
      if (it.body && needsTranslation(it.body)) items.push({ id: `${it.key}|b`, text: it.body.slice(0, 800) });
    }
    setTranslating(true);
    try {
      const map = await translateForReport(items);
      setTranslations(Object.fromEntries(items.filter((i) => map[i.id]?.text).map((i) => [i.id, map[i.id].text])));
    } catch (e) {
      notify(`Translation failed: ${errorText(e)}`);
    } finally {
      setTranslating(false);
    }
  };

  const report = async (fmt: 'html' | 'md' | 'pdf') => {
    setReporting(true);
    try {
      await downloadIncidentReport({ incident: inc, enrichment: c.enrich }, fmt);
    } catch (e) {
      notify(`Report failed: ${errorText(e)}`);
    } finally {
      setReporting(false);
    }
  };

  const acceptable = (c.enrich?.candidates ?? []).filter((x) => x.candidate_type !== 'account_profile' && (x.recommendation === 'attach' || x.triage_score == null)).length;
  const brief = cleanText(c.enrich?.run?.brief ?? '');
  const shown = platform.length ? syn.coverage.filter((it) => platform.includes(it.platform ?? '')) : syn.coverage;

  const coverageCard = (it: CoverageItem) => {
    const tTitle = translations[`${it.key}|t`];
    const tBody = translations[`${it.key}|b`];
    const title = tTitle || it.title;
    const actions: MenuItem[] = !it.inCase && it.candidateId != null
      ? [{ id: 'attach', label: 'Add to the case', icon: 'Check' }, { id: 'dismiss', label: 'Not relevant, don’t suggest again', icon: 'X' }]
      : [];
    const summary = it.url && it.type === 'article' ? overrides[sigKey(it.url, inc.brand_id)] ?? it.signals : it.signals;
    return (
      <ArticleCard
        key={it.key}
        as="li"
        variant="row"
        headingLevel={4}
        meta={[it.platform, it.type === 'article' && it.url ? hostOf(it.url) : null, it.date].filter(Boolean).join(' · ')}
        flag={it.inCase ? undefined : <Chip size="sm" tone="accent" icon={<Icon name="Sparkle" size="sm" />}>Found by AI</Chip>}
        title={it.url?.startsWith('http') ? <TextLink href={it.url} external>{title}</TextLink> : title}
        summary={tBody ? `${tBody} (translated)` : undefined}
        tags={
          <>
            {tTitle && <Chip size="sm" tone="info" icon={<Icon name="Translate" size="sm" />}>Translated</Chip>}
            {it.engagementLine && <Chip size="sm" tone="muted">{it.engagementLine}</Chip>}
            {summary && it.url && <SignalsChips summary={summary} available uri={it.url} onOpen={() => openSignals({ uri: it.url!, title: it.title, brand_id: inc.brand_id })} />}
          </>
        }
        details={(it.body || it.aiReason) ? (
          <Stack gap="sm">
            {it.body && <Text variant="description">{it.body}</Text>}
            {it.aiReason && <Text variant="caption">Why the AI suggested it: {it.aiReason}</Text>}
          </Stack>
        ) : undefined}
        actions={actions.length ? actions : undefined}
        actionsLabel={`Actions for “${title}”`}
        onAction={(id) => it.candidateId != null && void c.decideOne(it.candidateId, id as 'attach' | 'dismiss')}
      />
    );
  };

  return (
    <>
      <div><Button variant="ghost" size="sm" iconStart={<Icon name="CaretLeft" size="sm" />} onClick={onBack}>All incidents</Button></div>

      {c.chain && !c.chain.intact && (
        <Banner tone="error" title="The evidence record has been altered" description={`The hash chain breaks at item(s) ${c.chain.broken_ids.join(', ')}. Treat this case’s evidence as compromised until it is looked into.`} />
      )}

      <Panel
        title={inc.title}
        description={`${inc.brand_name} · case #${inc.id} · opened ${(inc.created_at ?? '').slice(0, 10)}${inc.resolved_at ? ` · resolved ${inc.resolved_at.slice(0, 10)}` : ''}`}
        headerAside={
          <Stack direction="row" gap="sm">
            <Select label="Severity" hideLabel options={SEVERITIES.map((s) => ({ value: s, label: `Severity: ${s}` }))} value={inc.severity} onValueChange={(severity) => void setField({ severity })} />
            <Select label="Status" hideLabel options={STATUSES.map((s) => ({ value: s, label: s, description: STATUS_HELP[s] }))} value={inc.status} onValueChange={(status) => void setField({ status })} />
          </Stack>
        }
      >
        <Stack gap="md">
          <Stack direction="row" gap="sm">
            <Chip tone={statusTone(inc.status)}>{inc.status}</Chip>
            <Chip tone={sevTone(inc.severity)}>Severity: {inc.severity}</Chip>
          </Stack>
          {inc.description && <Text variant="description">{cleanText(inc.description)}</Text>}
          <TextField
            label="Owner"
            placeholder="Unassigned"
            value={owner}
            onChange={setOwner}
            action={<Button size="lg" variant="secondary" disabled={owner === (inc.owner ?? '')} onClick={() => void setField({ owner })}>Save</Button>}
          />
          <Stack direction="row" gap="sm">
            {acceptable > 0 && (
              <Button iconStart={<Icon name="Check" size="sm" />} disabled={c.enrichBusy} onClick={() => void c.acceptAll()}>
                Accept {acceptable} recommended {acceptable === 1 ? 'finding' : 'findings'}
              </Button>
            )}
            <Button variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} disabled={running} onClick={() => void c.startEnrich()}>
              {running ? (c.enrich?.run?.stage || 'Investigating…') : 'Investigate with AI'}
            </Button>
            <Menu
              trigger={<Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} disabled={reporting}>{reporting ? 'Writing report…' : 'Download report'}</Button>}
              items={[{ id: 'pdf', label: 'PDF' }, { id: 'html', label: 'Web page (HTML)' }, { id: 'md', label: 'Markdown' }]}
              onSelect={(id) => void report(id as 'html' | 'md' | 'pdf')}
              label="Report format"
            />
          </Stack>
          <Text variant="caption">Investigate sweeps for related coverage, checks who is spreading it, screens articles and writes an assessment. The report adds an AI-written summary and translations.</Text>

          {(inc.duplicate_candidates ?? []).map((dup) => (
            <Banner
              key={dup.id}
              tone="warning"
              title={`Possibly the same incident as case #${dup.id}`}
              description={`This case and #${dup.id} (“${dup.title}”) share evidence. If they cover one event, work it in one case and close the other.`}
              action={
                <Stack direction="row" gap="sm">
                  <Button size="sm" onClick={() => void c.mergeInto(dup.id)}>Merge into #{dup.id}</Button>
                  <Button size="sm" variant="secondary" onClick={() => c.openIncident(dup.id)}>View #{dup.id}</Button>
                  <Button size="sm" variant="ghost" onClick={() => void addIncidentNote(inc.id, `not a duplicate of case #${dup.id} — confirmed by analyst`).then(c.refreshIncident, (e: unknown) => notify(errorText(e)))}>Not a duplicate</Button>
                </Stack>
              }
            />
          ))}
          {suggestions.map((ev, i) => {
            const severity = (ev.note ?? '').startsWith('severity review:');
            return severity ? (
              <Banner
                key={i}
                tone="warning"
                title="Severity may be too high"
                description={`Every screened item in this case came back low-risk: nothing is independently confirmed or coordinated. Severity is ${inc.severity}.`}
                action={
                  <Stack direction="row" gap="sm">
                    <Button size="sm" onClick={() => { void setField({ severity: lowerSeverity(inc.severity) }); dismissSugg(ev.at); }}>Lower to {lowerSeverity(inc.severity)}</Button>
                    <Button size="sm" variant="ghost" onClick={() => dismissSugg(ev.at)}>Keep {inc.severity}</Button>
                  </Stack>
                }
              />
            ) : (
              <Banner key={i} tone="info" title="AI suggestion" description={ev.note ?? ''} action={<Button size="sm" variant="ghost" onClick={() => dismissSugg(ev.at)}>Dismiss</Button>} />
            );
          })}
        </Stack>
      </Panel>

      <Panel title="How big it is" headingLevel={3}>
        <Stack gap="md">
          <Grid as="ul" columns={4} stackAt="small" gap="sm" label="Case size">
            <li><Stat size="compact" label="Coverage" value={syn.coverage.length} meta={`${syn.coverage.filter((i) => i.type === 'social_post').length} posts · ${syn.coverage.filter((i) => i.type === 'article').length} articles`} /></li>
            <li><Stat size="compact" label="Platforms" value={syn.platforms.length} meta={syn.platforms.map((p) => p.name).join(', ') || '–'} /></li>
            <li><Stat size="compact" label="Engagement" value={nf(syn.totalEngagement)} meta="likes, reposts and comments" /></li>
            <li>
              <Stat
                size="compact"
                label="Credibility check"
                value={syn.worstVerdict ? VERDICT_LABEL[syn.worstVerdict] ?? syn.worstVerdict : 'Not screened'}
                meta={syn.worstVerdict ? `${syn.verdicts.length} ${syn.verdicts.length === 1 ? 'item' : 'items'} screened` : 'Investigate runs it'}
                tone={syn.worstVerdict ? (RISKY_VERDICTS.has(syn.worstVerdict) ? 'error' : 'success') : 'default'}
                wrapValue
              />
            </li>
          </Grid>
          {brief ? (
            <Collapsible>
              <Stack gap="sm">
                <Stack direction="row" justify="between" gap="sm">
                  <Eyebrow as="h4">AI assessment{c.enrich?.run?.finished_at ? `, ${c.enrich.run.finished_at.slice(0, 16).replace('T', ' ')}` : ''}</Eyebrow>
                  <Stack direction="row" gap="sm">
                    <Button size="sm" variant="ghost" onClick={c.attachBrief}>Save to record</Button>
                    <CollapsibleTrigger variant="ghost" size="sm">Read in full</CollapsibleTrigger>
                  </Stack>
                </Stack>
                <Text variant="description">{brief.replace(/[#*_>`]/g, '').slice(0, 320)}{brief.length > 320 ? '…' : ''}</Text>
                <CollapsibleContent><Markdown text={brief} /></CollapsibleContent>
              </Stack>
            </Collapsible>
          ) : !running ? (
            <Text variant="caption">No AI assessment yet. “Investigate with AI” sweeps for coverage, checks credibility and writes one.</Text>
          ) : null}
          {c.enrich?.run?.status === 'failed' && (
            <Banner tone="error" title="The AI investigation failed" description={c.enrich.run.error ?? undefined} action={<Button size="sm" variant="secondary" onClick={() => void c.startEnrich()}>Try again</Button>} />
          )}
        </Stack>
      </Panel>

      <Panel
        title="Coverage"
        description={`${syn.coverage.filter((i) => i.inCase).length} in the case${syn.agentFound.length ? ` · ${syn.agentFound.length} found by AI, waiting for your decision` : ''}${syn.reassignedCount ? ` · ${syn.reassignedCount} moved to other cases (kept in the record)` : ''}`}
        headingLevel={3}
        headerAside={
          <Stack direction="row" gap="sm">
            {foreign.length > 0 && !Object.keys(translations).length && (
              <Button size="sm" variant="secondary" iconStart={<Icon name="Translate" size="sm" />} disabled={translating} onClick={() => void translate()}>
                {translating ? 'Translating…' : `Translate ${foreign.length} into English`}
              </Button>
            )}
            <Menu
              trigger={<Button size="sm" variant="secondary" iconStart={<Icon name="Plus" size="sm" />}>Add evidence</Button>}
              items={[
                { id: 'search', label: 'Search collected articles and posts', icon: 'MagnifyingGlass' },
                { id: 'profile', label: 'Account profile', icon: 'User' },
                { id: 'file', label: 'Upload a file (up to 25 MB)', icon: 'UploadSimple', disabled: c.fileBusy },
              ]}
              onSelect={(id) => {
                if (id === 'search') c.setSearch((s) => ({ ...s, open: true }));
                else if (id === 'profile') c.openProfilePicker();
                else c.fileInputRef.current?.click();
              }}
              align="end"
            />
          </Stack>
        }
      >
        <Stack gap="md">
          <TextField
            label="Capture a link"
            placeholder="Paste a URL"
            value={c.evidenceUrl}
            onChange={c.setEvidenceUrl}
            onSubmit={() => void c.captureUrl()}
            action={<Button size="lg" variant="secondary" disabled={!c.evidenceUrl.trim()} onClick={() => void c.captureUrl()}>Capture</Button>}
          />
          <input ref={c.fileInputRef} type="file" hidden aria-label="File to add as evidence" onChange={(e) => void c.onFilePicked(e.target.files?.[0])} />
          {syn.platforms.length > 1 && (
            <FilterChipRow label="Platform" options={syn.platforms.map((p) => ({ value: p.name, label: `${p.name} ${p.count}` }))} selected={platform} onChange={setPlatform} />
          )}
          {shown.length ? <Stack as="ul" gap="sm" label="Coverage">{shown.map(coverageCard)}</Stack> : (
            <Text>Nothing here yet. Investigate finds coverage, or add items by hand.</Text>
          )}
        </Stack>
      </Panel>

      {syn.accounts.length > 0 && (
        <Panel title="Accounts involved" headingLevel={3}>
          <Stack as="ul" gap="sm" label="Accounts">
            {syn.accounts.map((a) => (
              <li key={a.key}>
                <Stack direction="row" justify="between" gap="sm">
                  <ActivityRow
                    primary={`${a.displayName || `@${a.handle}`} (@${a.handle} · ${a.platform})`}
                    secondary={[a.followers != null ? `${nf(Number(a.followers))} followers` : null, a.posts ? `${a.posts} ${a.posts === 1 ? 'post' : 'posts'} here` : null, a.engagement ? `${nf(a.engagement)} engagement` : null, a.profiled ? 'profiled' : null].filter(Boolean).join(' · ')}
                  />
                  {!a.profiled && PLATFORM_KEY[a.platform] && (
                    <Button size="sm" variant="secondary" disabled={c.profileBusy != null} onClick={() => void c.profileAndAttach(PLATFORM_KEY[a.platform], a.handle)}>
                      {c.profileBusy === `${PLATFORM_KEY[a.platform]}:${a.handle}` ? 'Profiling…' : 'Profile and add'}
                    </Button>
                  )}
                </Stack>
              </li>
            ))}
          </Stack>
          <Text variant="caption">“Profile and add” builds the account’s profile (posting history, reach, behaviour) with a paid lookup and adds the snapshot to the case.</Text>
        </Panel>
      )}

      {syn.chronology.length > 0 && (
        <Panel title="How it unfolded" headingLevel={3}>
          <Stack as="ul" gap="sm" label="Timeline">
            {syn.chronology.map((row, i) => (
              <ActivityRow key={i} as="li" primary={row.label} secondary={row.kind === 'milestone' ? 'Case milestone' : row.item?.platform} timestamp={row.date} dateTime={row.date} dotTone={row.kind === 'milestone' ? 'accent' : undefined} />
            ))}
          </Stack>
        </Panel>
      )}

      <Panel
        title="Audit log"
        description={`${(inc.timeline ?? []).length} entries · tamper-evident`}
        headingLevel={3}
        headerAside={<Button size="sm" variant="secondary" iconStart={<Icon name="ShieldCheck" size="sm" />} onClick={c.runVerifyChain}>Verify integrity</Button>}
      >
        <Collapsible>
          <Stack gap="md">
            {c.chain?.intact && <Banner tone="success" title="Record intact" description={`${c.chain.items} item(s) checked; nothing was altered or removed.`} />}
            <div><CollapsibleTrigger variant="secondary" size="sm">Show the record</CollapsibleTrigger></div>
            <CollapsibleContent>
              <Stack gap="lg">
                {syn.otherEvidence.length > 0 && (
                  <Stack gap="sm">
                    <Eyebrow as="h4">Files, notes and alerts on record</Eyebrow>
                    <Stack as="ul" gap="sm" label="Other evidence">
                      {syn.otherEvidence.map((ev) => {
                        const m = (ev.meta ?? {}) as { file_id?: number; filename?: string };
                        return (
                          <li key={ev.id}>
                            <Stack direction="row" gap="sm">
                              <Chip size="sm" tone="muted">{ev.evidence_type.replace(/_/g, ' ')}</Chip>
                              {ev.evidence_type === 'file' && m.file_id ? (
                                <TextLink href={incidentFileUrl(inc.id, m.file_id)}>{m.filename ?? 'File'}</TextLink>
                              ) : (
                                <Text as="span">{cleanText(ev.title || ev.content || ev.source_ref || '').slice(0, 120)}</Text>
                              )}
                              <Text variant="caption" as="span">{(ev.captured_at ?? '').slice(0, 10)}</Text>
                            </Stack>
                          </li>
                        );
                      })}
                    </Stack>
                  </Stack>
                )}
                <Stack gap="sm">
                  <Eyebrow as="h4">Audit trail</Eyebrow>
                  <Stack as="ul" gap="sm" label="Audit trail">
                    {(inc.timeline ?? []).map((ev, i) => {
                      const agent = ['agent_brief', 'enrichment', 'agent_suggestion'].includes(ev.kind) || String(ev.actor ?? '').startsWith('agent');
                      return <ActivityRow key={i} as="li" primary={auditLine(ev)} secondary={agent ? 'AI' : ev.actor ?? undefined} timestamp={(ev.at ?? '').slice(5, 16).replace('T', ' ')} dateTime={ev.at ?? undefined} dotTone={agent ? 'accent' : undefined} />;
                    })}
                  </Stack>
                </Stack>
                <TextField
                  label="Add a note to the record"
                  value={c.noteText}
                  onChange={c.setNoteText}
                  onSubmit={c.saveNote}
                  action={<Button size="lg" variant="secondary" disabled={!c.noteText.trim()} onClick={c.saveNote}>Add note</Button>}
                />
              </Stack>
            </CollapsibleContent>
          </Stack>
        </Collapsible>
      </Panel>
    </>
  );
}
