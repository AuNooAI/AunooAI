import { Chip, Eyebrow, Grid, Icon, Panel, SettingRow, Stack, Text, type IconName } from '@aunoo/ui';
import { Markdown } from '../../shell/Markdown';
import { parseBrief, type ActionGroup, type Item, type Section } from '../lib/brief';

// Short fields show as chips; the rest as lines under the item
const CHIP_FIELDS = new Set(['likelihood', 'impact', 'time horizon', 'window']);
const toneOf = (v: string) => (/^high/i.test(v) ? 'warning' : 'muted') as 'warning' | 'muted';

function ItemList({ label, items, empty }: { label: string; items: Item[]; empty: string }) {
  if (!items.length) return <Text variant="hint">{empty}</Text>;
  return (
    <Stack as="ul" gap="sm" label={label}>
      {items.map((it, i) => {
        const chips = it.fields.filter((f) => CHIP_FIELDS.has(f.label.toLowerCase()) && f.value);
        const lines = it.fields.filter((f) => !CHIP_FIELDS.has(f.label.toLowerCase()) && f.value);
        return (
          <li key={`${i}-${it.name}`}>
            <SettingRow title={it.name}>
              <Stack gap="sm">
                {chips.length > 0 && (
                  <Stack direction="row" gap="sm">
                    {chips.map((f) => <Chip key={f.label} size="sm" tone={toneOf(f.value)}>{`${f.label}: ${f.value}`}</Chip>)}
                  </Stack>
                )}
                {lines.map((f) => <Text key={f.label} variant="hint">{`${f.label}: ${f.value}`}</Text>)}
                {it.notes.map((n, j) => <Text key={j} variant="hint">{n}</Text>)}
              </Stack>
            </SettingRow>
          </li>
        );
      })}
    </Stack>
  );
}

const GROUP_ICON: Record<ActionGroup['key'], IconName> = { immediate: 'Lightning', near: 'Clock', strategic: 'Target' };

// The implications section's subsections as cards, as the old page drew them (an icon per kind)
const IMPLICATION_ICON: [RegExp, IconName][] = [
  [/strateg|long.term/i, 'Target'], [/operation|process/i, 'Lightning'], [/financ|budget|revenue|cost/i, 'CreditCard'],
  [/competit|market/i, 'ChartLineUp'], [/tactic|immediate/i, 'ArrowRight'],
];
function implicationCards(text: string): { title: string; cards: { kind: string; body: string; icon: IconName }[] } | null {
  const head = text.match(/^## (.+?)\s*$/m)?.[1] ?? '';
  if (!/implication/i.test(head)) return null;
  const cards = text.split(/(?=^### )/m).filter((x) => x.startsWith('### ')).map((sub) => {
    const kind = (sub.match(/^### (.+?)\s*$/m)?.[1] ?? '').replace(/\s*implications?\s*:?/i, '').trim();
    const body = sub.replace(/^### .+?$/m, '').trim();
    return { kind: kind || 'General', body, icon: IMPLICATION_ICON.find(([re]) => re.test(kind))?.[1] ?? 'Info' };
  }).filter((c) => c.body);
  return cards.length ? { title: head, cards } : null;
}

function Section({ s }: { s: Section }) {
  if (s.kind === 'markdown') {
    const impl = implicationCards(s.text);
    if (!impl) return <Markdown text={s.text} />;
    return (
      <Stack gap="md">
        <Eyebrow as="h3">{impl.title}</Eyebrow>
        <Grid columns={2} stackAt="small" gap="md">
          {impl.cards.map((c) => (
            <Panel key={c.kind} headingLevel={3} title={<><Icon name={c.icon} size="sm" /> {c.kind}</>}>
              <Markdown text={c.body} />
            </Panel>
          ))}
        </Grid>
      </Stack>
    );
  }
  if (s.kind === 'threats') {
    return (
      <Stack gap="md">
        <Eyebrow as="h3">{s.title}</Eyebrow>
        <Grid columns={2} stackAt="small" gap="md">
          <Panel headingLevel={3} title={<><Icon name="Warning" size="sm" /> Threats</>}>
            <ItemList label="Threats" items={s.threats} empty="No threats identified." />
          </Panel>
          <Panel headingLevel={3} title={<><Icon name="Sparkle" size="sm" /> Opportunities</>}>
            <ItemList label="Opportunities" items={s.opportunities} empty="No opportunities identified." />
          </Panel>
        </Grid>
      </Stack>
    );
  }
  return (
    <Stack gap="md">
      <Eyebrow as="h3">{s.title}</Eyebrow>
      <Grid columns={3} stackAt="small" gap="md">
        {s.groups.map((g) => (
          <Panel key={g.key} headingLevel={3} title={<><Icon name={GROUP_ICON[g.key]} size="sm" /> {g.title}</>} description={g.timeframe}>
            {g.actions.length === 0 ? (
              <Text variant="hint">{`No ${g.title.toLowerCase()} actions.`}</Text>
            ) : (
              <Stack as="ul" gap="sm" label={`${g.title} actions`}>
                {g.actions.map((a, i) => (
                  <li key={`${i}-${a.text}`}>
                    <SettingRow
                      title={a.text}
                      description={a.rationale}
                      actionsPlacement="title"
                      actions={a.owner && <Chip size="sm" tone="neutral">{a.owner}</Chip>}
                    />
                  </li>
                ))}
              </Stack>
            )}
          </Panel>
        ))}
      </Grid>
    </Stack>
  );
}

/**
 * The Situation Assessment brief, with the threat/opportunity and recommended-action sections laid
 * out as columns when they parse. Everything else, and any section that doesn't parse, is Markdown.
 */
export function BriefView({ brief }: { brief: string }) {
  // Runs of Markdown sections are joined so they render as one document (the implications section
  // stays on its own, so it can be laid out as cards)
  const sections = parseBrief(brief).reduce<Section[]>((acc, s) => {
    const last = acc[acc.length - 1];
    if (s.kind === 'markdown' && last?.kind === 'markdown' && !implicationCards(s.text) && !implicationCards(last.text)) last.text += s.text;
    else acc.push(s.kind === 'markdown' ? { ...s } : s);
    return acc;
  }, []);
  return (
    <Stack gap="lg">
      {sections.map((s, i) => <Section key={i} s={s} />)}
    </Stack>
  );
}
