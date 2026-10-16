import './Grid.css';

export interface GridProps {
  /** 4 columns drop to 2 at ≤1000px. `main-aside` = a wide main column and a one-third side rail ·
   *  `rail-main-rail` = fixed left rail, fluid main, fixed right rail (the right rail drops below at ≤1200px, the left at ≤1000px). */
  columns?: 2 | 3 | 4 | 'main-aside' | 'rail-main-rail';
  /** Where to stack to one column: wide ≤1000px (tiles) · small ≤560px (premium cards) · never */
  stackAt?: 'wide' | 'small' | 'never';
  gap?: 'sm' | 'md';
  /** Use `ul` with `li` children for lists. */
  as?: 'div' | 'ul';
  /** Accessible name when rendered as a list. */
  label?: string;
  className?: string;
  children?: React.ReactNode;
}

/**
 * Equal-column layout that collapses to one column at a breakpoint.
 * A child with `data-grid-span="full"` takes a whole row.
 */
export function Grid({ columns = 2, stackAt = 'wide', gap = 'sm', as: Comp = 'div', label, className, children }: GridProps) {
  return (
    <Comp
      className={['grid', `grid--cols-${columns}`, `grid--stack-${stackAt}`, `grid--gap-${gap}`, className].filter(Boolean).join(' ')}
      aria-label={label}
    >
      {children}
    </Comp>
  );
}
