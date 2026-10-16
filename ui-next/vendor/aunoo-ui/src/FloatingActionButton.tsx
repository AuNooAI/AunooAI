import { Icon } from './Icon';
import type { IconName } from './icons';
import { Tooltip } from './Tooltip';
import './FloatingActionButton.css';

export interface FloatingActionButtonProps {
  /** Phosphor name registered in Icon, e.g. "Robot". */
  icon: IconName;
  /** Accessible name and tooltip, e.g. "Open Auspex assistant". */
  label: string;
  /** `() => void` */
  onClick?: () => void;
  className?: string;
}

/** Round accent button pinned to the bottom-right of the window, for one global action (an assistant). */
export function FloatingActionButton({ icon, label, onClick, className }: FloatingActionButtonProps) {
  return (
    <Tooltip content={label} side="left">
      <button type="button" className={['fab', className].filter(Boolean).join(' ')} aria-label={label} onClick={onClick}>
        <Icon name={icon} size="lg" />
      </button>
    </Tooltip>
  );
}
