import './DiffView.css';

export interface DiffViewProps {
  /** Names the comparison, e.g. "System prompt changes". */
  label: string;
  /** Older text (left column). */
  before: string;
  /** Newer text (right column). */
  after: string;
  /** Column headings, e.g. "Selected version" / "Current active version". */
  beforeLabel: React.ReactNode;
  afterLabel: React.ReactNode;
  /** Shown above the columns when both texts match. */
  sameText?: string;
  className?: string;
}

type Op = { kind: 'same' | 'removed' | 'added'; text: string };

/** Line diff by longest common subsequence — fine for prompt-sized texts. */
function diffLines(a: string[], b: string[]): Op[] {
  const n = a.length;
  const m = b.length;
  const lcs = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  }
  const ops: Op[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      ops.push({ kind: 'same', text: a[i] });
      i += 1;
      j += 1;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) ops.push({ kind: 'removed', text: a[i++] });
    else ops.push({ kind: 'added', text: b[j++] });
  }
  while (i < n) ops.push({ kind: 'removed', text: a[i++] });
  while (j < m) ops.push({ kind: 'added', text: b[j++] });
  return ops;
}

const HIDDEN = { removed: 'Removed: ', added: 'Added: ', same: '' };

/**
 * Two texts side by side with their line differences marked: removed lines (left) on an error
 * tint with a strikethrough, added lines (right) on a success tint. Each change is also announced
 * in words, so colour isn't the only signal.
 */
export function DiffView({ label, before, after, beforeLabel, afterLabel, sameText = 'No differences', className }: DiffViewProps) {
  const ops = diffLines(before.split('\n'), after.split('\n'));
  const column = (side: 'before' | 'after') =>
    ops
      .filter((op) => op.kind === 'same' || op.kind === (side === 'before' ? 'removed' : 'added'))
      .map((op, index) => (
        <div key={index} className={`diff-view__line diff-view__line--${op.kind}`}>
          {op.kind !== 'same' && <span className="visually-hidden">{HIDDEN[op.kind]}</span>}
          {op.text || ' '}
        </div>
      ));

  return (
    <section className={['diff-view', className].filter(Boolean).join(' ')} aria-label={label}>
      {before === after && <p className="diff-view__same">{sameText}</p>}
      <div className="diff-view__columns">
        <div className="diff-view__column">
          <div className="diff-view__heading">{beforeLabel}</div>
          <div className="diff-view__code" tabIndex={0} role="region" aria-label={`${label}: before`}>{column('before')}</div>
        </div>
        <div className="diff-view__column">
          <div className="diff-view__heading">{afterLabel}</div>
          <div className="diff-view__code" tabIndex={0} role="region" aria-label={`${label}: after`}>{column('after')}</div>
        </div>
      </div>
    </section>
  );
}
