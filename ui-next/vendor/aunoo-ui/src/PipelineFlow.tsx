import './PipelineFlow.css';

export interface PipelineTag {
  label: string;
  /** Colour of the tag; the label must still name the model or mode. */
  tone?: 'accent' | 'info' | 'success' | 'warning' | 'neutral';
}

export interface PipelineStep {
  id: string;
  title: string;
  /** Line under the title, e.g. "DeBERTa → GPT". */
  detail?: string;
  tags?: PipelineTag[];
}

export interface PipelineFlowProps {
  /** Accessible name, e.g. "Article processing pipeline". */
  label: string;
  /** In processing order. */
  steps: PipelineStep[];
  className?: string;
}

/**
 * Ordered stages joined by a connector line (an `<ol>`, read as "1 of 6…"). Steps keep a
 * minimum width (--pipeline-node-w) and the row scrolls sideways on narrow screens.
 */
export function PipelineFlow({ label, steps, className }: PipelineFlowProps) {
  return (
    // Focusable so keyboard users can scroll it when it overflows
    <div className={['pipeline', className].filter(Boolean).join(' ')} role="region" aria-label={label} tabIndex={0}>
      <ol className="pipeline__list">
        {steps.map((step, index) => (
          <li key={step.id} className="pipeline__step">
            <span className="pipeline__index" aria-hidden="true">{index + 1}</span>
            <span className="pipeline__title">{step.title}</span>
            {step.tags && step.tags.length > 0 && (
              <span className="pipeline__tags">
                {step.tags.map((tag) => (
                  <span key={tag.label} className={`pipeline__tag pipeline__tag--${tag.tone ?? 'neutral'}`}>{tag.label}</span>
                ))}
              </span>
            )}
            {step.detail && <span className="pipeline__detail">{step.detail}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}
