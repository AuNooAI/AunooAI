import { Icon } from './Icon';
import { IconButton } from './IconButton';
import './Pagination.css';

export interface PaginationProps {
  /** 1-based. */
  page: number;
  pageCount: number;
  /** `(page) => void` */
  onPageChange: (page: number) => void;
  /** Accessible name, e.g. "Articles pages". */
  label?: string;
  className?: string;
}

/** Previous / "2 / 21" / next. The page text is announced as "Page 2 of 21". */
export function Pagination({ page, pageCount, onPageChange, label = 'Pagination', className }: PaginationProps) {
  return (
    <nav className={['pagination', className].filter(Boolean).join(' ')} aria-label={label}>
      <IconButton icon={<Icon name="CaretLeft" size="sm" />} label="Previous page" disabled={page <= 1} onClick={() => onPageChange(page - 1)} />
      <span className="pagination__status" aria-live="polite">
        <span aria-hidden="true">{page} / {pageCount}</span>
        <span className="visually-hidden">Page {page} of {pageCount}</span>
      </span>
      <IconButton icon={<Icon name="CaretRight" size="sm" />} label="Next page" disabled={page >= pageCount} onClick={() => onPageChange(page + 1)} />
    </nav>
  );
}
