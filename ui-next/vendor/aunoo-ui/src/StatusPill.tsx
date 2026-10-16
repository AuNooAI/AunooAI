import type { ReactNode } from 'react';
import { StatusDot } from './StatusDot';
import './StatusPill.css';

export interface StatusPillProps {
  variant?: 'live' | 'muted' | 'compact';
  /** Dot colour: live = green · accent = pink (trial) · pending = amber */
  tone?: 'live' | 'accent' | 'pending';
  className?: string;
  children: ReactNode;
}

/**
 * Status label with a dot (§6.4 live-pill treatment).
 * - `live`: translucent white pill (plan pill in the page header)
 * - `muted`: grey chip (plan state)
 * - `compact`: small translucent pill ("Recommended")
 */
export function StatusPill({ variant = 'live', tone = 'live', className, children }: StatusPillProps) {
  return (
    <span className={['status-pill', `status-pill--${variant}`, className].filter(Boolean).join(' ')}>
      <StatusDot tone={tone} />
      {children}
    </span>
  );
}
