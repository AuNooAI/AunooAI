/**
 * A table you can sort, group and follow.
 *
 * Written because every table in the market monitor was a static dump: no
 * sort, no grouping, and counts that named a number without offering a way to
 * see what was counted. A reader who wanted "the vendors hiring most" or "who
 * is in Israel" had to read the whole table and do it by eye.
 *
 * Deliberately small. It sorts, groups and links; it does not paginate, filter
 * or virtualise, because the tables here are tens of rows and adding those
 * would be building a grid library nobody asked for.
 */

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, ChevronUp, ExternalLink } from 'lucide-react';

export interface Column<T> {
  key: string;
  label: string;
  /** The value used for sorting and grouping. Falls back to the rendered cell
   *  when absent, which is right for plain text columns. */
  value?: (row: T) => string | number | null | undefined;
  render?: (row: T) => React.ReactNode;
  align?: 'left' | 'right';
  /** Off for columns where an ordering means nothing, like a row of icons. */
  sortable?: boolean;
  groupable?: boolean;
  /** Opens in a new tab. A cell with a link renders as one. */
  href?: (row: T) => string | null | undefined;
}

type Dir = 'asc' | 'desc';

function cellValue<T>(col: Column<T>, row: T): string | number | null | undefined {
  if (col.value) return col.value(row);
  const raw = (row as any)[col.key];
  return typeof raw === 'object' ? undefined : raw;
}

function compare(a: any, b: any): number {
  const aEmpty = a === null || a === undefined || a === '';
  const bEmpty = b === null || b === undefined || b === '';
  // Missing values sort last in both directions. A vendor with no headcount is
  // not the smallest vendor, it is a vendor we have not measured.
  if (aEmpty && bEmpty) return 0;
  if (aEmpty) return 1;
  if (bEmpty) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

export function DataTable<T>({
  rows, columns, initialSort, initialDir = 'asc', onRowClick, rowKey,
  emptyMessage = 'Nothing to show.', dense = false,
}: {
  rows: T[];
  columns: Column<T>[];
  initialSort?: string;
  initialDir?: Dir;
  onRowClick?: (row: T) => void;
  rowKey: (row: T) => string | number;
  emptyMessage?: string;
  dense?: boolean;
}) {
  const [sortKey, setSortKey] = useState<string | undefined>(initialSort);
  const [dir, setDir] = useState<Dir>(initialDir);
  const [groupKey, setGroupKey] = useState<string>('');
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  const groupable = columns.filter(c => c.groupable);

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const col = columns.find(c => c.key === sortKey);
    if (!col) return rows;
    const out = [...rows].sort((a, b) =>
      compare(cellValue(col, a), cellValue(col, b)));
    return dir === 'asc' ? out : out.reverse();
  }, [rows, columns, sortKey, dir]);

  const groups = useMemo(() => {
    if (!groupKey) return null;
    const col = columns.find(c => c.key === groupKey);
    if (!col) return null;
    const map = new Map<string, T[]>();
    for (const row of sorted) {
      const label = String(cellValue(col, row) ?? '—');
      (map.get(label) ?? map.set(label, []).get(label)!).push(row);
    }
    // Biggest group first: with a long tail of one-row groups, alphabetical
    // ordering buries whatever the grouping was meant to reveal.
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [sorted, columns, groupKey]);

  function toggleSort(key: string) {
    if (sortKey === key) {
      setDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setDir('asc');
    }
  }

  const pad = dense ? 'px-2 py-1' : 'px-3 py-2';

  const header = (
    <thead className="bg-slate-50 text-slate-600">
      <tr>
        {columns.map(col => (
          <th key={col.key}
              className={`${pad} text-xs font-medium whitespace-nowrap ${
                col.align === 'right' ? 'text-right' : 'text-left'}`}>
            {col.sortable === false ? col.label : (
              <button onClick={() => toggleSort(col.key)}
                      className="inline-flex items-center gap-1 hover:text-slate-900">
                {col.label}
                {sortKey === col.key && (dir === 'asc'
                  ? <ChevronUp className="w-3 h-3" />
                  : <ChevronDown className="w-3 h-3" />)}
              </button>
            )}
          </th>
        ))}
      </tr>
    </thead>
  );

  function renderRow(row: T) {
    return (
      <tr key={rowKey(row)}
          onClick={onRowClick ? () => onRowClick(row) : undefined}
          className={`hover:bg-slate-50 ${onRowClick ? 'cursor-pointer' : ''}`}>
        {columns.map(col => {
          const link = col.href?.(row);
          const body = col.render ? col.render(row) : (cellValue(col, row) ?? '—');
          return (
            <td key={col.key}
                className={`${pad} text-slate-700 ${
                  col.align === 'right' ? 'text-right tabular-nums' : ''}`}>
              {link ? (
                <a href={link} target="_blank" rel="noreferrer"
                   onClick={e => e.stopPropagation()}
                   className="text-slate-800 hover:underline inline-flex items-center gap-1">
                  {body}<ExternalLink className="w-3 h-3 shrink-0 text-slate-400" />
                </a>
              ) : body}
            </td>
          );
        })}
      </tr>
    );
  }

  if (rows.length === 0) {
    return <p className="text-sm text-slate-500 py-6 text-center">{emptyMessage}</p>;
  }

  return (
    <div className="space-y-2">
      {groupable.length > 0 && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-500">Group by</span>
          <button onClick={() => setGroupKey('')}
                  className={`px-2 py-0.5 rounded border ${
                    groupKey === '' ? 'bg-slate-800 text-white border-slate-800'
                                    : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
            nothing
          </button>
          {groupable.map(col => (
            <button key={col.key} onClick={() => setGroupKey(col.key)}
                    className={`px-2 py-0.5 rounded border ${
                      groupKey === col.key
                        ? 'bg-slate-800 text-white border-slate-800'
                        : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
              {col.label}
            </button>
          ))}
        </div>
      )}

      <div className="overflow-x-auto border rounded-lg bg-white">
        <table className="w-full text-sm">
          {header}
          {groups ? groups.map(([label, groupRows]) => {
            const open = openGroups[label] !== false;
            return (
              <tbody key={label} className="divide-y">
                <tr className="bg-slate-100/70">
                  <td colSpan={columns.length} className={`${pad}`}>
                    <button
                      onClick={() => setOpenGroups(g => ({ ...g, [label]: !open }))}
                      className="inline-flex items-center gap-1 text-sm font-medium
                                 text-slate-700">
                      {open ? <ChevronDown className="w-4 h-4" />
                            : <ChevronRight className="w-4 h-4" />}
                      {label}
                      <span className="text-slate-500 font-normal">
                        ({groupRows.length})
                      </span>
                    </button>
                  </td>
                </tr>
                {open && groupRows.map(renderRow)}
              </tbody>
            );
          }) : <tbody className="divide-y">{sorted.map(renderRow)}</tbody>}
        </table>
      </div>
    </div>
  );
}
