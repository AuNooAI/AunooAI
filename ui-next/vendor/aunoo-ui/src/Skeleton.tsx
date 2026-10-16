import './Skeleton.css';

export interface SkeletonProps {
  /** text = a few lines · block = one tall box (cards, charts) */
  variant?: 'text' | 'block';
  /** Number of lines for `text`. */
  lines?: number;
  /** Height of `block` from the chart/card it stands in for. */
  size?: 'card' | 'chart';
  className?: string;
}

/**
 * Placeholder while content loads. Decorative: the container should carry `aria-busy` and a
 * visible or screen-reader "Loading…" message. Shimmer is off with reduced motion.
 */
export function Skeleton({ variant = 'text', lines = 3, size = 'card', className }: SkeletonProps) {
  if (variant === 'block') {
    return <div className={['skeleton', 'skeleton--block', `skeleton--${size}`, className].filter(Boolean).join(' ')} aria-hidden="true" />;
  }
  return (
    <div className={['skeleton-lines', className].filter(Boolean).join(' ')} aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton skeleton--line" data-last={i === lines - 1 ? '' : undefined} />
      ))}
    </div>
  );
}
