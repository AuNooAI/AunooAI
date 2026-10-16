import type { ReactNode } from 'react';
import { useId } from 'react';
import './SettingRow.css';

export interface SettingRowProps {
  title: ReactNode;
  description?: ReactNode;
  /** Usually `<PriceChip>`. */
  price?: ReactNode;
  /** Right-hand controls: buttons, chips. */
  actions?: ReactNode;
  /**
   * side (default) = actions in a column beside all the content ·
   * title = actions on the title line; description and children use the full width
   */
  actionsPlacement?: 'side' | 'title';
  /** Nested content under the header. Makes the row top-aligned. */
  children?: ReactNode;
  /** Id for the title, so actions can reference it (`aria-describedby`). Auto-generated if omitted. */
  titleId?: string;
  className?: string;
}

/**
 * Inset row: title, description and price on the left, actions on the right.
 * `children` render under the header (e.g. topic pills) and top-align the row.
 */
export function SettingRow({ title, description, price, actions, actionsPlacement = 'side', titleId: titleIdProp, className, children }: SettingRowProps) {
  const autoId = useId();
  const titleId = titleIdProp ?? autoId;
  const titleEl = <div id={titleId} className="setting-row__title">{title}</div>;

  if (actionsPlacement === 'title') {
    return (
      <div className={['setting-row', 'setting-row--title-actions', className].filter(Boolean).join(' ')} role="group" aria-labelledby={titleId}>
        <div className="setting-row__head">
          {titleEl}
          {actions && <div className="setting-row__actions">{actions}</div>}
        </div>
        {description && <div className="setting-row__description">{description}</div>}
        {price && <div className="setting-row__price">{price}</div>}
        {children && <div className="setting-row__children">{children}</div>}
      </div>
    );
  }

  return (
    <div
      className={['setting-row', children && 'setting-row--tall', className].filter(Boolean).join(' ')}
      role="group"
      aria-labelledby={titleId}
    >
      <div className="setting-row__main">
        {titleEl}
        {description && <div className="setting-row__description">{description}</div>}
        {price && <div className="setting-row__price">{price}</div>}
        {children && <div className="setting-row__children">{children}</div>}
      </div>
      {actions && <div className="setting-row__actions">{actions}</div>}
    </div>
  );
}
