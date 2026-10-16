import { Logo } from './Logo';
import './TopNav.css';

export interface TopNavProps {
  /** Defaults to `<Logo />`. */
  logo?: React.ReactNode;
  /** Next to the logo, e.g. `<Breadcrumbs surface="dark">`. */
  lead?: React.ReactNode;
  /**
   * Start `lead` at a fixed distance from the bar's left edge, read from the
   * `--top-nav-lead-start` custom property (set by a parent such as ConsoleLayout, so `lead`
   * lines up with the content below). The logo is clipped if it's wider than that space.
   */
  alignLead?: boolean;
  /** Right side, e.g. actions and/or `<UserMenu>`. */
  children?: React.ReactNode;
  className?: string;
}

/** 64px dark top bar: logo (+ optional lead content) on the left, anything on the right. */
export function TopNav({ logo = <Logo />, lead, alignLead = false, children, className }: TopNavProps) {
  return (
    <header className={['top-nav', alignLead && 'top-nav--align-lead', className].filter(Boolean).join(' ')}>
      <div className="top-nav__brand">{logo}</div>
      {lead && <div className="top-nav__lead">{lead}</div>}
      {children && <div className="top-nav__right">{children}</div>}
    </header>
  );
}
