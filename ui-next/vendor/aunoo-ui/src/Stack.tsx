import './Stack.css';

export interface StackProps {
  /** sm 8 · md 12 · lg 16px */
  gap?: 'sm' | 'md' | 'lg';
  /** column (default) · row = items side by side, wrapping onto new lines (chips, pills) */
  direction?: 'column' | 'row';
  /** Row only: how leftover space is shared — between pushes the last group to the far end. */
  justify?: 'start' | 'between' | 'end';
  /** Row only: wrap onto new lines (default). Off for icon + text rows, so the text wraps beside the icon. */
  wrap?: boolean;
  as?: 'div' | 'section' | 'ul';
  /** Accessible name, e.g. when rendered as a list. */
  label?: string;
  className?: string;
  children?: React.ReactNode;
}

/** Stack with a fixed gap — components have no outer margin, so the parent spaces them. */
export function Stack({ gap = 'md', direction = 'column', justify = 'start', wrap = true, as: Comp = 'div', label, className, children }: StackProps) {
  return (
    <Comp className={['stack', `stack--${direction}`, `stack--gap-${gap}`, justify !== 'start' && `stack--justify-${justify}`, !wrap && 'stack--nowrap', className].filter(Boolean).join(' ')} aria-label={label}>
      {children}
    </Comp>
  );
}
