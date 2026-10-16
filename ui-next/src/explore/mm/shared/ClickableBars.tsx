import { useState } from 'react';
import { Text } from '@aunoo/ui';
import './mm.css';

/*
 * A bar chart whose bars are buttons, for the figures the old page drilled down from (the design
 * system's bar charts don't take clicks). Vertical columns suit a series over time; horizontal
 * bars suit a ranked list with long names. Bars still filling (the current week) are hatched, so a
 * short bar isn't read as a collapse. Every bar is reachable with the keyboard.
 */

export interface ClickableBar {
  id: string;
  label: string;
  value: number;
  /** A vendor's colour, say; defaults to the first chart colour */
  color?: string;
  /** Still filling: drawn hatched */
  partial?: boolean;
}

export function ClickableBars({ title, bars, orientation = 'vertical', onSelect, selectLabel, unit = '' }: {
  title: string;
  bars: ClickableBar[];
  orientation?: 'vertical' | 'horizontal';
  onSelect: (id: string) => void;
  /** Read out for each bar, e.g. "Open the 12 articles from the week of 6 Oct" */
  selectLabel: (b: ClickableBar) => string;
  unit?: string;
}) {
  const [active, setActive] = useState<ClickableBar | null>(null);
  const max = Math.max(1, ...bars.map((b) => b.value));
  if (!bars.length) return null;

  if (orientation === 'horizontal') {
    return (
      <ul className="mm-hbars" aria-label={title}>
        {bars.map((b) => (
          <li key={b.id}>
            <button type="button" className="mm-hbar" aria-label={selectLabel(b)} onClick={() => onSelect(b.id)}>
              <span className="mm-hbar__label">{b.label}</span>
              <span className="mm-hbar__track">
                <span className={`mm-hbar__fill${b.partial ? ' mm-bar--partial' : ''}`} style={{ inlineSize: `${(b.value / max) * 100}%`, background: b.color }} />
              </span>
              <span className="mm-hbar__value">{`${b.value.toLocaleString()}${unit ? ` ${unit}` : ''}`}</span>
            </button>
          </li>
        ))}
      </ul>
    );
  }

  const W = Math.max(320, bars.length * 34);
  const H = 180;
  const PAD_B = 22;
  const colW = W / bars.length;
  const every = Math.ceil(bars.length / 10);
  return (
    <figure className="mm-vbars">
      <div className="mm-vbars__scroll">
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="group" aria-label={title} className="mm-vbars__svg">
          <defs>
            <pattern id="mm-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" className="mm-hatch-bg" />
              <line x1="0" y1="0" x2="0" y2="6" className="mm-hatch-line" />
            </pattern>
          </defs>
          <line x1="0" x2={W} y1={H - PAD_B} y2={H - PAD_B} className="mm-vbars__axis" />
          {bars.map((b, i) => {
            const h = ((H - PAD_B - 8) * b.value) / max;
            const x = i * colW + colW * 0.15;
            return (
              <g key={b.id}>
                <rect
                  x={x}
                  y={H - PAD_B - h}
                  width={colW * 0.7}
                  height={Math.max(h, b.value ? 2 : 0)}
                  className={`mm-vbar${active?.id === b.id ? ' mm-vbar--active' : ''}`}
                  style={{ fill: b.partial ? 'url(#mm-hatch)' : b.color }}
                  tabIndex={0}
                  role="button"
                  aria-label={selectLabel(b)}
                  onMouseEnter={() => setActive(b)}
                  onFocus={() => setActive(b)}
                  onClick={() => onSelect(b.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelect(b.id);
                    }
                  }}
                >
                  <title>{`${b.label}: ${b.value}${b.partial ? ' so far' : ''}`}</title>
                </rect>
                {i % every === 0 && <text x={i * colW + colW / 2} y={H - 6} textAnchor="middle" className="mm-vbars__tick">{b.label}</text>}
              </g>
            );
          })}
        </svg>
      </div>
      <Text variant="caption" as="div">
        {active ? `${active.label}: ${active.value.toLocaleString()}${unit ? ` ${unit}` : ''}${active.partial ? ' so far (still filling)' : ''}. Select the bar to open them.` : 'Select a bar to open what it counts.'}
      </Text>
    </figure>
  );
}
