import { Eyebrow } from './Eyebrow';
import './PageHeader.css';

export interface PageHeaderProps {
  /** Small label above the title, e.g. the parent section "Operations". */
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** e.g. `<StatusPill>Free plan</StatusPill>` */
  aside?: React.ReactNode;
  /** Keep the title for screen readers only (the breadcrumb already shows it); the subtitle and eyebrow are dropped. */
  hideTitle?: boolean;
  className?: string;
}

/** Page title (the page's only h1), subtitle, and an element on the right (e.g. plan pill). */
export function PageHeader({ eyebrow, title, subtitle, aside, hideTitle = false, className }: PageHeaderProps) {
  if (hideTitle) {
    const heading = <h1 className="visually-hidden">{title}</h1>;
    return aside ? (
      <div className={['page-header', 'page-header--aside-only', className].filter(Boolean).join(' ')}>
        {heading}
        <div className="page-header__aside">{aside}</div>
      </div>
    ) : (
      heading
    );
  }
  return (
    <div className={['page-header', className].filter(Boolean).join(' ')}>
      <div className="page-header__text">
        {eyebrow && <Eyebrow className="page-header__eyebrow">{eyebrow}</Eyebrow>}
        <h1 className="page-header__title">{title}</h1>
        {subtitle && <p className="page-header__subtitle">{subtitle}</p>}
      </div>
      {aside && <div className="page-header__aside">{aside}</div>}
    </div>
  );
}
