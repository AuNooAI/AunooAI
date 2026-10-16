import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CodeBlock, Eyebrow, Icon, Stack, Table, Text, TextLink } from '@aunoo/ui';

/** Minimal hast node, for reading table cells. */
interface HNode {
  type: string;
  tagName?: string;
  value?: string;
  children?: HNode[];
}

const textOf = (n: HNode | undefined): string =>
  !n ? '' : n.type === 'text' ? (n.value ?? '') : (n.children ?? []).map(textOf).join('');

const rowsOf = (n: HNode | undefined, cell: 'th' | 'td') =>
  (n?.children ?? [])
    .filter((c) => c.tagName === 'thead' || c.tagName === 'tbody')
    .flatMap((section) => (section.children ?? []).filter((r) => r.tagName === 'tr'))
    .map((r) => (r.children ?? []).filter((c) => c.tagName === cell || c.tagName === 'td' || c.tagName === 'th').map(textOf))
    .filter((cells) => cells.length > 0);

/**
 * Markdown (GFM) drawn with library components, so docs match the rest of the page.
 * Table cells keep their text but not inline formatting.
 */
const components: Components = {
  // Doc headings sit inside a Panel (its own h2), so they start at h3
  h1: ({ children }) => <Eyebrow as="h3">{children}</Eyebrow>,
  h2: ({ children }) => <Eyebrow as="h3">{children}</Eyebrow>,
  h3: ({ children }) => <Eyebrow as="h4">{children}</Eyebrow>,
  h4: ({ children }) => <Text variant="label" as="p">{children}</Text>,
  p: ({ children }) => <Text variant="description">{children}</Text>,
  a: ({ href, children }) => <TextLink href={href ?? '#'} external={Boolean(href && /^https?:/.test(href))}>{children}</TextLink>,
  ul: ({ children }) => <Stack as="ul" gap="sm" label="List">{children}</Stack>,
  ol: ({ children }) => <Stack as="ul" gap="sm" label="Numbered list">{children}</Stack>,
  li: ({ children }) => <li><Text variant="description" as="span">{children}</Text></li>,
  // GFM task lists: a read-only tick or circle
  input: ({ checked }) => <Icon name={checked ? 'CheckCircle' : 'Minus'} size="sm" label={checked ? 'Done' : 'Not done'} />,
  blockquote: ({ children }) => <Text variant="hint" as="div">{children}</Text>,
  hr: () => null,
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children }) => {
    const text = String(children ?? '');
    return /language-|\n/.test(`${className ?? ''}${text.trimEnd()}`) ? <CodeBlock label={className?.replace('language-', '') || 'Code'} code={text.replace(/\n$/, '')} /> : <code>{children}</code>;
  },
  table: ({ node }) => {
    const n = node as unknown as HNode;
    const thead = (n.children ?? []).find((c) => c.tagName === 'thead');
    const header = rowsOf({ type: 'element', children: thead ? [thead] : [] }, 'th')[0] ?? [];
    const body = rowsOf({ type: 'element', children: (n.children ?? []).filter((c) => c.tagName === 'tbody') }, 'td');
    const cols = header.length ? header : body[0]?.map((_, i) => `Column ${i + 1}`) ?? [];
    return (
      <Table
        caption={cols.join(', ')}
        hideCaption
        rowKey={(r) => r.__key}
        rows={body.map((cells, i) => ({ __key: String(i), ...Object.fromEntries(cells.map((c, j) => [`c${j}`, c])) }))}
        columns={cols.map((h, j) => ({ key: `c${j}`, header: h, wrap: true, rowHeader: j === 0 }))}
      />
    );
  },
};

export function Markdown({ text }: { text: string }) {
  return (
    <Stack gap="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </Stack>
  );
}
