import { useMemo, useState } from 'react';
import './mm.css';
import { Collapsible, CollapsibleContent, CollapsibleTrigger, Select, Stack, Table, Text, type TableColumn } from '@aunoo/ui';
import { VendorSwatch } from './colours';

/*
 * A table you can sort and group, as the old DataTable.tsx, on the design system's Table. Missing
 * values sort last in both directions: a vendor with no headcount isn't the smallest vendor, it's
 * one we haven't measured. Grouping puts the biggest group first.
 */

export interface SortColumn<T> {
  key: string;
  label: string;
  /** Value for sorting and grouping; defaults to row[key] when that's a string or number */
  value?: (row: T) => string | number | null | undefined;
  render?: (row: T) => React.ReactNode;
  align?: 'start' | 'end';
  /** Default true */
  sortable?: boolean;
  groupable?: boolean;
  rowHeader?: boolean;
  wrap?: boolean;
}

function cellValue<T>(col: SortColumn<T>, row: T) {
  if (col.value) return col.value(row);
  const raw = (row as Record<string, unknown>)[col.key];
  return typeof raw === 'string' || typeof raw === 'number' ? raw : undefined;
}

function compare(a: unknown, b: unknown) {
  const ae = a === null || a === undefined || a === '';
  const be = b === null || b === undefined || b === '';
  if (ae && be) return 0;
  if (ae) return 1;
  if (be) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

export function SortTable<T>({
  caption, hideCaption = true, rows, columns, rowKey, initialSort, initialDir = 'asc', emptyText = 'Nothing to show.', scroll,
}: {
  caption: string;
  hideCaption?: boolean;
  rows: T[];
  columns: SortColumn<T>[];
  rowKey: (row: T) => string | number;
  initialSort?: string;
  initialDir?: 'asc' | 'desc';
  emptyText?: string;
  scroll?: boolean;
}) {
  const [sort, setSort] = useState<{ key: string; direction: 'asc' | 'desc' } | undefined>(initialSort ? { key: initialSort, direction: initialDir } : undefined);
  const [groupKey, setGroupKey] = useState('');
  const groupable = columns.filter((c) => c.groupable);

  const sorted = useMemo(() => {
    const col = sort && columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    // Missing values stay last whichever way the column is sorted
    return [...rows].sort((a, b) => {
      const va = cellValue(col, a);
      const vb = cellValue(col, b);
      const empty = (v: unknown) => v === null || v === undefined || v === '';
      if (empty(va) || empty(vb)) return compare(va, vb);
      return sort!.direction === 'asc' ? compare(va, vb) : compare(vb, va);
    });
  }, [rows, columns, sort]);

  const groups = useMemo(() => {
    const col = groupKey && columns.find((c) => c.key === groupKey);
    if (!col) return null;
    const m = new Map<string, T[]>();
    for (const r of sorted) {
      const v = cellValue(col, r);
      const k = v === null || v === undefined || v === '' ? 'Unknown' : String(v);
      m.set(k, [...(m.get(k) ?? []), r]);
    }
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [sorted, columns, groupKey]);

  const tableColumns: TableColumn<T>[] = columns.map((c) => ({
    key: c.key, header: c.label, align: c.align, render: c.render, rowHeader: c.rowHeader, wrap: c.wrap, sortable: c.sortable !== false,
  }));
  const onSortChange = (key: string) =>
    setSort((s) => (s?.key === key ? { key, direction: s.direction === 'asc' ? 'desc' : 'asc' } : { key, direction: 'asc' }));
  const key = (r: T) => String(rowKey(r));

  return (
    <Stack gap="sm">
      {groupable.length > 0 && rows.length > 0 && (
        <Select
          label="Group by"
          options={[{ value: 'none', label: 'No grouping' }, ...groupable.map((c) => ({ value: c.key, label: c.label }))]}
          value={groupKey || 'none'}
          onValueChange={(v) => setGroupKey(v === 'none' ? '' : v)}
        />
      )}
      {!groups ? (
        <Table caption={caption} hideCaption={hideCaption} rows={sorted} rowKey={key} columns={tableColumns} sort={sort} onSortChange={onSortChange} emptyText={emptyText} scroll={scroll} />
      ) : (
        groups.map(([g, list]) => (
          <Collapsible key={g}>
            <CollapsibleTrigger variant="ghost" size="sm">{`${g} (${list.length})`}</CollapsibleTrigger>
            <CollapsibleContent>
              <Table caption={`${caption}: ${g}`} hideCaption rows={list} rowKey={key} columns={tableColumns} sort={sort} onSortChange={onSortChange} />
            </CollapsibleContent>
          </Collapsible>
        ))
      )}
    </Stack>
  );
}

/**
 * A vendor's name as a link to its page. A real link (?vendor=id), so it opens in a new tab too;
 * a plain click opens it in place.
 */
export function VendorLink({ id, name, color, onOpen }: { id: number; name: string; color?: string | null; onOpen: (id: number) => void }) {
  const href = `${window.location.pathname}?vendor=${id}`;
  return (
    <a
      className="text-link"
      href={href}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        onOpen(id);
      }}
    >
      <VendorSwatch color={color} />
      {name}
    </a>
  );
}

/** A dash for a value we don't have, with the reason as a tooltip-free caption */
export function Missing({ children = '—' }: { children?: React.ReactNode }) {
  return <Text as="span" variant="hint">{children}</Text>;
}

/** A count or phrase that opens the records behind it: an inline link that is really a button */
export function LinkButton({ onClick, label, children }: { onClick: () => void; label?: string; children: React.ReactNode }) {
  return (
    <button type="button" className="text-link mm-linkbutton" aria-label={label} onClick={(e) => { e.stopPropagation(); onClick(); }}>
      {children}
    </button>
  );
}
