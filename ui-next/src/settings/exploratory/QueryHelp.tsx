import { useState } from 'react';
import { Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Icon, IconButton, Select, Stack, Text, TextField } from '@aunoo/ui';
import { BUILDER_FIELDS, BUILDER_OPS } from './query';
import './exploratory.css';

/*
 * The old page's "Search & Filter Help" panel, quick filters and visual query builder. The builder
 * only writes text into the query; the server parses it.
 */

const QUICK = ['category="AI Business"', 'sentiment="Positive"', 'has:driver_type', 'publication_date>=last_week', 'publication_date>today'];

const SECTIONS: { title: string; rows: [string, string][] }[] = [
  { title: 'Operators', rows: [['= or equal', 'same as'], ['!= or not equal', 'different from'], ['> >= < <=', 'compare values']] },
  {
    title: 'Dates',
    rows: [
      ['publication_date>=last_week', 'articles from the last week'],
      ['publication_date>today', 'articles from today'],
      ['publication_date<=yesterday', 'articles up to yesterday'],
      ['publication_date>=2026-09-01', 'articles since a date'],
      ['today, yesterday, last_week, last_month, this_week, this_month', 'relative dates you can type'],
    ],
  },
  { title: 'Logic', rows: [['AND', 'all terms match'], ['OR', 'any term matches'], ['NOT', 'exclude the next term'], ['in(a,b,c)', 'one of a set'], ['has:field', 'the field is filled in'], ['field=min..max', 'a range']] },
  { title: 'Pipes', rows: [['| HEAD n', 'the first n results (default 100)'], ['| TAIL n', 'the last n results'], ['| SAMPLE n', 'a random sample of n']] },
  {
    title: 'Controls',
    rows: [
      ['sort:publication_date:desc', 'sort the results'],
      ['limit:50', 'cap the number of results (limit:0 for no cap)'],
      ['similar:<article id>', 'articles like a given one'],
      ['cluster=4', 'keep one cluster from the map'],
      ['keyword="exact words"', 'plain text search on title, summary and tags instead of meaning'],
      ['AI^3', 'weight a term more'],
      ['"exact phrase"', 'match the phrase exactly'],
    ],
  },
  {
    title: 'Examples',
    rows: [
      ['AI AND category="AI Business" sentiment=Positive', ''],
      ['AI NOT Google has:driver_type', ''],
      ['"artificial intelligence" sort:publication_date:desc limit:50', ''],
      ['category="Technology" AND publication_date>today', ''],
    ],
  },
];

interface Row { id: number; field: string; op: string; value: string }

export function QueryHelp({ onAdd }: { onAdd: (text: string) => void }) {
  const [rows, setRows] = useState<Row[]>([{ id: 1, field: 'category', op: '=', value: '' }]);
  const set = (id: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const built = rows.filter((r) => r.value.trim()).map((r) => `${r.field}${r.op}${/\s/.test(r.value.trim()) || r.op === '=' || r.op === '!=' ? `"${r.value.trim()}"` : r.value.trim()}`).join(' AND ');

  return (
    <Stack gap="sm">
      <Stack direction="row" gap="sm">
        <Text as="span" variant="label">Quick filters:</Text>
        {QUICK.map((q) => <Chip key={q} tone="neutral" icon={<Icon name="Plus" size="sm" />} label={`Add ${q}`} onClick={() => onAdd(q)}>{q}</Chip>)}
      </Stack>
      <Collapsible>
        <CollapsibleTrigger variant="ghost" size="sm" className="xa-wrap-trigger">Build a filter</CollapsibleTrigger>
        <CollapsibleContent>
          <Stack gap="sm">
            {rows.map((r, i) => (
              <Stack key={r.id} direction="row" gap="sm">
                <Select label={`Field ${i + 1}`} hideLabel options={BUILDER_FIELDS.map((f) => ({ value: f, label: f }))} value={r.field} onValueChange={(field) => set(r.id, { field })} />
                <Select label={`Comparison ${i + 1}`} hideLabel options={BUILDER_OPS.map((o) => ({ value: o, label: o }))} value={r.op} onValueChange={(op) => set(r.id, { op })} />
                <TextField label={`Value ${i + 1}`} hideLabel placeholder="value" value={r.value} onChange={(value) => set(r.id, { value })} />
                {rows.length > 1 && <IconButton icon={<Icon name="X" size="sm" />} label={`Remove condition ${i + 1}`} onClick={() => setRows((rs) => rs.filter((x) => x.id !== r.id))} />}
              </Stack>
            ))}
            <Stack direction="row" gap="sm">
              <Button variant="ghost" size="sm" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setRows((rs) => [...rs, { id: Math.max(...rs.map((x) => x.id)) + 1, field: 'sentiment', op: '=', value: '' }])}>Add a condition</Button>
              <Button variant="secondary" size="sm" disabled={!built} onClick={() => onAdd(built)}>Add to the query</Button>
            </Stack>
            {built && <Text variant="caption">{`Adds: ${built}`}</Text>}
          </Stack>
        </CollapsibleContent>
      </Collapsible>
      <Collapsible>
        <CollapsibleTrigger variant="ghost" size="sm" className="xa-wrap-trigger">How to write a query</CollapsibleTrigger>
        <CollapsibleContent>
          <Stack gap="md">
            <Text variant="caption">Type anything for a search by meaning, then narrow it with filters. Click a filter in Facets or in an article’s details to add it.</Text>
            {SECTIONS.map((s) => (
              <Stack key={s.title} gap="sm">
                <Text variant="label">{s.title}</Text>
                <Stack as="ul" gap="sm" label={s.title}>
                  {s.rows.map(([code, what]) => (
                    <li key={code}>
                      {/* Rows with a placeholder or a list are read, not added */}
                      {/[<,]/.test(code) && !code.startsWith('in(') ? <code>{code}</code> : <button type="button" className="text-link xa-link" title="Add to the query" onClick={() => onAdd(code)}><code>{code}</code></button>}
                      {what && <Text as="span" variant="caption">{` ${what}`}</Text>}
                    </li>
                  ))}
                </Stack>
              </Stack>
            ))}
          </Stack>
        </CollapsibleContent>
      </Collapsible>
    </Stack>
  );
}
