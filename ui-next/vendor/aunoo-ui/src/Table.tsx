import { useId } from 'react';
import { Icon } from './Icon';
import './Table.css';

export interface TableColumn<Row> {
  key: string;
  header: React.ReactNode;
  /** Numbers read best right-aligned. */
  align?: 'start' | 'end';
  /** Cell content. Defaults to `row[key]`. */
  render?: (row: Row) => React.ReactNode;
  /** This column names the row (rendered as a row header `<th scope="row">`). */
  rowHeader?: boolean;
  /** Let long content (lists, sentences) wrap instead of keeping the cell on one line. */
  wrap?: boolean;
  /** The header becomes a sort button (needs `sort` + `onSortChange` on the table). */
  sortable?: boolean;
}

export interface TableProps<Row> {
  /** Table name (the `<caption>`). */
  caption: string;
  /** Keep the caption for screen readers only (e.g. when a Panel title already names it). */
  hideCaption?: boolean;
  columns: TableColumn<Row>[];
  rows: Row[];
  /** `(row) => string` — stable key per row. */
  rowKey: (row: Row) => string;
  /** Long tables: cap the height (--table-max-h) and scroll under a pinned header. */
  scroll?: boolean;
  /** Shown in place of the rows when `rows` is empty. */
  emptyText?: React.ReactNode;
  /** Current sort, for sortable columns: `{ key, direction }`. Sorting the rows is up to the app. */
  sort?: { key: string; direction: 'asc' | 'desc' };
  /** `(key) => void` — a sortable header was pressed. */
  onSortChange?: (key: string) => void;
  className?: string;
}

/**
 * Data table on an inset surface. Scrolls sideways inside its own focusable region on narrow
 * screens, so the page never does.
 */
export function Table<Row>({ caption, hideCaption = false, columns, rows, rowKey, scroll = false, emptyText, sort, onSortChange, className }: TableProps<Row>) {
  const captionId = useId();
  return (
    <div className={['table', scroll && 'table--scroll', className].filter(Boolean).join(' ')} role="region" aria-labelledby={captionId} tabIndex={0}>
      <table className="table__table">
        <caption id={captionId} className={hideCaption ? 'visually-hidden' : 'table__caption'}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => {
              const active = sort?.key === column.key;
              return (
                <th
                  key={column.key}
                  scope="col"
                  className={column.align === 'end' ? 'table__cell--end' : undefined}
                  aria-sort={column.sortable ? (active ? (sort!.direction === 'asc' ? 'ascending' : 'descending') : 'none') : undefined}
                >
                  {column.sortable && onSortChange ? (
                    <button type="button" className="table__sort" onClick={() => onSortChange(column.key)}>
                      {column.header}
                      <Icon name={active ? (sort!.direction === 'asc' ? 'ArrowUp' : 'ArrowDown') : 'CaretDown'} size="sm" className={active ? undefined : 'table__sort-idle'} />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && emptyText && (
            <tr>
              <td colSpan={columns.length} className="table__empty">{emptyText}</td>
            </tr>
          )}
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => {
                const content = column.render ? column.render(row) : (row as Record<string, React.ReactNode>)[column.key];
                const className = [column.align === 'end' && 'table__cell--end', column.wrap && 'table__cell--wrap'].filter(Boolean).join(' ') || undefined;
                return column.rowHeader ? (
                  <th key={column.key} scope="row" className={className}>{content}</th>
                ) : (
                  <td key={column.key} className={className}>{content}</td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
