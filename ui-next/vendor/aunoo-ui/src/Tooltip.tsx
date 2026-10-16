import * as RadixTooltip from '@radix-ui/react-tooltip';
import './Tooltip.css';

export interface TooltipProps {
  /** Tooltip text. Supplementary only — the trigger must still have its own accessible name. */
  content: React.ReactNode;
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
  /** Controlled open state (for stories / tests). */
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  /** The trigger: a single focusable element (e.g. a `<button>`) that accepts a ref. */
  children: React.ReactElement;
}

/**
 * Short label shown on hover and keyboard focus (Radix Tooltip; Escape closes it).
 * Overlay surface per §3.1: card-light, hairline, r-2xl, shadowOverlay.
 */
export function Tooltip({ content, side = 'bottom', align = 'center', open, defaultOpen, onOpenChange, className, children }: TooltipProps) {
  return (
    <RadixTooltip.Provider>
      <RadixTooltip.Root open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange}>
        <RadixTooltip.Trigger
          asChild
          // Open on keyboard focus only. Overlays move focus to their first button when they open
          // from a click; without this its tooltip would pop up uninvited. (Radix skips its own
          // handler when this one calls preventDefault.)
          onFocus={(event) => {
            if (!event.currentTarget.matches(':focus-visible')) event.preventDefault();
          }}
        >
          {children}
        </RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content
            className={['tooltip', className].filter(Boolean).join(' ')}
            side={side}
            align={align}
          >
            {content}
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
