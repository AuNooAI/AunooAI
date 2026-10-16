import { Chip } from '@aunoo/ui';
import { severityLabel, severityTone } from './labels';

/** A name or count that opens something: an inline link that is really a button */
export function LinkButton({ onClick, label, children }: { onClick: () => void; label?: string; children: React.ReactNode }) {
  return (
    <button type="button" className="text-link threat-linkbutton" aria-label={label} onClick={(e) => { e.stopPropagation(); onClick(); }}>
      {children}
    </button>
  );
}

export function SeverityChip({ level }: { level: string | null | undefined }) {
  return <Chip tone={severityTone(level)} size="sm">{severityLabel(level)}</Chip>;
}

/** Chips for a list of short values (industries, regions, techniques), with "+N more" past a cap */
export function ValueChips({ values, max = 12 }: { values: string[] | null | undefined; max?: number }) {
  if (!values?.length) return null;
  return (
    <>
      {values.slice(0, max).map((v) => <Chip key={v} tone="muted" size="sm">{v}</Chip>)}
      {values.length > max && <Chip tone="muted" size="sm">{`+${values.length - max} more`}</Chip>}
    </>
  );
}
