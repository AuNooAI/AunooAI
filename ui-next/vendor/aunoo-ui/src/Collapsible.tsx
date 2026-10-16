import * as RadixCollapsible from '@radix-ui/react-collapsible';
import { Button } from './Button';
import { Icon } from './Icon';
import './Collapsible.css';

export interface CollapsibleProps {
  /** Controlled open state. Pair with `onOpenChange`. */
  open?: boolean;
  defaultOpen?: boolean;
  /** `(open) => void` */
  onOpenChange?: (open: boolean) => void;
  className?: string;
  children?: React.ReactNode;
}

/**
 * Show/hide a section (Radix Collapsible). The trigger and content can sit anywhere inside the root,
 * e.g. the trigger in a header row and the content further down.
 */
export function Collapsible({ open, defaultOpen, onOpenChange, className, children }: CollapsibleProps) {
  return (
    <RadixCollapsible.Root open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange} className={className}>
      {children}
    </RadixCollapsible.Root>
  );
}

export interface CollapsibleTriggerProps {
  /** Button variant; use `onSurface` on an inset areaBg block. */
  variant?: 'secondary' | 'ghost' | 'onSurface';
  /** sm 28px · md 32px (default) */
  size?: 'sm' | 'md';
  className?: string;
  children: React.ReactNode;
}

/** Button with a chevron that toggles the nearest Collapsible. */
export function CollapsibleTrigger({ variant = 'secondary', size = 'md', className, children }: CollapsibleTriggerProps) {
  return (
    <RadixCollapsible.Trigger asChild>
      <Button
        variant={variant}
        size={size}
        className={['collapsible__trigger', className].filter(Boolean).join(' ')}
        iconEnd={<Icon name="CaretDown" size="sm" className="collapsible__chevron" />}
      >
        {children}
      </Button>
    </RadixCollapsible.Trigger>
  );
}

export interface CollapsibleContentProps {
  className?: string;
  children?: React.ReactNode;
}

/** The collapsible content. Animates its height; instant with reduced motion. */
export function CollapsibleContent({ className, children }: CollapsibleContentProps) {
  return (
    <RadixCollapsible.Content className={['collapsible__content', className].filter(Boolean).join(' ')}>
      {children}
    </RadixCollapsible.Content>
  );
}
