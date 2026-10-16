import { useId, useRef } from 'react';
import * as RadixPopover from '@radix-ui/react-popover';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import './Popover.css';

export interface PopoverProps {
  /** The opener: a single button element, e.g. `<IconButton>`. Gets `aria-expanded` / `aria-controls`. */
  trigger: React.ReactElement;
  /** Visible heading with a ✕ close button. Becomes the panel's accessible name. */
  title?: React.ReactNode;
  /** Accessible name when there's no `title`, e.g. "Page settings". */
  label?: string;
  /** Pinned under the content behind a hairline, e.g. a `<PopoverClose>` "Done" button. */
  footer?: React.ReactNode;
  /** auto = fits its content · wide = fixed wider panel for lists (notifications) */
  width?: 'auto' | 'wide';
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
  /** Controlled open state. Pair with `onOpenChange`. */
  open?: boolean;
  defaultOpen?: boolean;
  /** `(open) => void` */
  onOpenChange?: (open: boolean) => void;
  className?: string;
  children?: React.ReactNode;
}

/**
 * Floating panel anchored to a trigger (Radix Popover: focus moves in, Escape or an outside
 * click closes it, focus returns to the trigger). Overlay surface per §3.1. The body scrolls
 * when the panel would run past the window; the title and footer stay put.
 */
export function Popover({
  trigger,
  title,
  label,
  footer,
  width = 'auto',
  side = 'bottom',
  align = 'end',
  open,
  defaultOpen,
  onOpenChange,
  className,
  children,
}: PopoverProps) {
  const titleId = useId();
  const contentRef = useRef<HTMLDivElement>(null);
  return (
    <RadixPopover.Root open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content
          className={['popover', `popover--${width}`, title && 'popover--titled', className].filter(Boolean).join(' ')}
          side={side}
          align={align}
          aria-label={title ? undefined : label}
          aria-labelledby={title ? titleId : undefined}
          ref={contentRef}
          tabIndex={-1}
          // A titled popover's first control is its ✕. Focusing it on open would show the "Close"
          // tooltip, and the first Escape would only close that. Focus the panel instead: one Escape
          // closes it, and Tab still reaches ✕ first.
          onOpenAutoFocus={(event) => {
            if (!title) return;
            event.preventDefault();
            contentRef.current?.focus();
          }}
        >
          {title && (
            <div className="popover__header">
              <h2 id={titleId} className="popover__title">{title}</h2>
              <RadixPopover.Close asChild>
                <IconButton icon={<Icon name="X" size="sm" />} label="Close" tooltipSide="left" />
              </RadixPopover.Close>
            </div>
          )}
          <div className="popover__body">{children}</div>
          {footer && <div className="popover__footer">{footer}</div>}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}

export interface PopoverCloseProps {
  /** A single button element, e.g. `<Button>Done</Button>`. */
  children: React.ReactElement;
}

/** Closes the nearest Popover when its child is clicked. */
export function PopoverClose({ children }: PopoverCloseProps) {
  return <RadixPopover.Close asChild>{children}</RadixPopover.Close>;
}
