import './Breadcrumbs.css';

export interface BreadcrumbItem {
  id?: string;
  label: React.ReactNode;
  /** Omit for the current page (the last item). */
  href?: string;
}

export interface BreadcrumbsProps {
  /** `[{ id?, label, href? }]`, root first. The last item is the current page. */
  items: BreadcrumbItem[];
  /** light = on the area panel · dark = on dark chrome (top nav) */
  surface?: 'light' | 'dark';
  /** Accessible name for the landmark. */
  label?: string;
  className?: string;
}

/**
 * Where the current page sits, e.g. "Operations / System Health". The last item is marked
 * `aria-current="page"`. Truncates with an ellipsis when space runs out.
 */
export function Breadcrumbs({ items, surface = 'light', label = 'Breadcrumb', className }: BreadcrumbsProps) {
  return (
    <nav className={['breadcrumbs', `breadcrumbs--${surface}`, className].filter(Boolean).join(' ')} aria-label={label}>
      <ol className="breadcrumbs__list">
        {items.map((item, index) => {
          const isCurrent = index === items.length - 1;
          return (
            <li key={item.id ?? index} className="breadcrumbs__item">
              {index > 0 && <span className="breadcrumbs__separator" aria-hidden="true">/</span>}
              {isCurrent || !item.href ? (
                <span className="breadcrumbs__current" aria-current={isCurrent ? 'page' : undefined}>
                  {item.label}
                </span>
              ) : (
                <a className="breadcrumbs__link" href={item.href}>{item.label}</a>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
