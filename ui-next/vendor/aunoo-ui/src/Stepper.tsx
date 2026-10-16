import { Icon } from './Icon';
import './Stepper.css';

export interface StepperStep {
  id: string;
  label: string;
}

export interface StepperProps {
  steps: StepperStep[];
  /** Index of the current step (0-based). Earlier steps show as done. */
  current: number;
  /** Accessible name, e.g. "Set up topic progress". */
  label: string;
  className?: string;
}

/** Progress through a multi-step flow. Read-only: navigation is the flow's Back / Next buttons. */
export function Stepper({ steps, current, label, className }: StepperProps) {
  return (
    <ol className={['stepper', className].filter(Boolean).join(' ')} aria-label={label}>
      {steps.map((step, index) => {
        const state = index < current ? 'done' : index === current ? 'current' : 'upcoming';
        return (
          <li key={step.id} className="stepper__step" data-state={state} aria-current={state === 'current' ? 'step' : undefined}>
            <span className="stepper__marker" aria-hidden="true">
              {state === 'done' ? <Icon name="Check" size="sm" /> : index + 1}
            </span>
            <span className="stepper__label">
              {step.label}
              <span className="visually-hidden">{state === 'done' ? ' (done)' : state === 'upcoming' ? ' (not started)' : ''}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
