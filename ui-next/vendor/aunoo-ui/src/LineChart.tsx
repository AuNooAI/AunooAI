import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Button } from './Button';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import { Table } from './Table';
import './LineChart.css';

/** CSS variable behind each series colour (used for the PNG export, which can't read classes). */
const SERIES_VAR = {
  1: '--viz-series-1', 2: '--viz-series-2', 3: '--viz-series-3', 4: '--viz-series-4', 5: '--viz-series-5',
  positive: '--success', negative: '--error', neutral: '--viz-neutral',
} as const;

export interface LineSeries {
  id: string;
  /** Legend, tooltip, table and end-label text. */
  label: string;
  /** Categorical slot (proposed --viz-series-N tokens). Colour follows the entity — keep it fixed. */
  color: 1 | 2 | 3 | 4 | 5 | 'positive' | 'negative' | 'neutral';
  /** Dashed stroke, e.g. a benchmark such as a competitor average. */
  dashed?: boolean;
  /** Dots on each data point (default: solid series only). */
  markers?: boolean;
  /** Area wash (series hue at low opacity) from the line down to the bottom of the plot. */
  fill?: boolean;
  /** One value per category; `null` = no data (skipped). Lines bridge the gaps; dots show real data. */
  values: (number | null)[];
}

export interface LineChartProps {
  /** Names the chart for screen readers, the table caption and the PNG file. */
  title: string;
  /** Short x labels, e.g. "11-03". */
  categories: string[];
  /** Long label for the tooltip and table, e.g. "Week of 3 Nov 2025". Defaults to the short label. */
  categoryLabels?: string[];
  series: LineSeries[];
  /** [min, max] of the y scale. Values outside are clamped to the edge. */
  yDomain: [number, number];
  yTicks: number[];
  /** Drawn as a stronger line, e.g. 0 for net sentiment. */
  baseline?: number;
  /** e.g. `(v) => (v > 0 ? `+${v}` : String(v))` */
  formatValue?: (value: number) => string;
  /** One-sentence takeaway read by screen readers before the table. */
  summary?: string;
  /**
   * Numbered markers on a series at a category, listed under the chart with their text — labels
   * never sit on the plot, so they can't overlap. Also shown in the tooltip for that category.
   */
  annotations?: LineAnnotation[];
  className?: string;
}

export interface LineAnnotation {
  id: string;
  /** Category index the marker sits on. */
  index: number;
  /** Series the marker sits on (its value at `index`). */
  seriesId: string;
  label: string;
  /** Text under the label in the list, e.g. a scenario with citations. */
  detail?: React.ReactNode;
}

interface Geometry {
  width: number;
  height: number;
  start: number;
  end: number;
  top: number;
  bottom: number;
  ring: number;
  marker: number;
}

const px = (el: Element, name: string) => parseFloat(getComputedStyle(el).getPropertyValue(name)) || 0;

/** Monotone cubic (Fritsch–Carlson): smooth, never overshoots a data point. */
function monotonePath(points: { x: number; y: number }[]) {
  const n = points.length;
  if (n === 0) return '';
  if (n === 1) return `M${points[0].x},${points[0].y}`;
  if (n === 2) return `M${points[0].x},${points[0].y}L${points[1].x},${points[1].y}`;
  const dx: number[] = [];
  const m: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    dx[i] = points[i + 1].x - points[i].x;
    m[i] = (points[i + 1].y - points[i].y) / dx[i];
  }
  const t: number[] = [m[0]];
  for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2;
  t[n - 1] = m[n - 2];
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) {
      t[i] = 0;
      t[i + 1] = 0;
      continue;
    }
    const a = t[i] / m[i];
    const b = t[i + 1] / m[i];
    const s = a * a + b * b;
    if (s > 9) {
      const tau = 3 / Math.sqrt(s);
      t[i] = tau * a * m[i];
      t[i + 1] = tau * b * m[i];
    }
  }
  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 0; i < n - 1; i++) {
    const p0 = points[i];
    const p1 = points[i + 1];
    d += `C${p0.x + dx[i] / 3},${p0.y + (t[i] * dx[i]) / 3},${p1.x - dx[i] / 3},${p1.y - (t[i + 1] * dx[i]) / 3},${p1.x},${p1.y}`;
  }
  return d;
}

/** Copies the computed paint of each element onto its clone, so the exported image matches the screen. */
const PAINT = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity', 'font-family', 'font-size', 'font-weight', 'text-anchor', 'dominant-baseline'];
function inlinePaint(source: Element, clone: Element) {
  const style = getComputedStyle(source);
  (clone as SVGElement).setAttribute('style', PAINT.map((p) => `${p}:${style.getPropertyValue(p)}`).join(';'));
  Array.from(source.children).forEach((child, i) => clone.children[i] && inlinePaint(child, clone.children[i]));
}

/**
 * Multi-series line chart (SVG): one y axis, solid hairline grid, a stronger baseline, monotone
 * lines that bridge skipped values, dots on real data, legend + end labels, a crosshair tooltip
 * (pointer or ←/→ keys), a table view and PNG download.
 */
export function LineChart({
  title,
  categories,
  categoryLabels,
  series,
  yDomain,
  yTicks,
  baseline,
  formatValue = (v) => String(v),
  summary,
  annotations = [],
  className,
}: LineChartProps) {
  const id = useId();
  const plotRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [geo, setGeo] = useState<Geometry | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const longLabel = (i: number) => categoryLabels?.[i] ?? categories[i];

  // Size from the container; gutters and mark sizes from the --viz-* tokens
  useLayoutEffect(() => {
    const el = plotRef.current;
    if (!el) return;
    const measure = () =>
      setGeo({
        width: el.clientWidth,
        height: el.clientHeight,
        start: px(el, '--viz-gutter-start'),
        end: px(el, '--viz-gutter-end'),
        top: px(el, '--viz-gutter-top'),
        bottom: px(el, '--viz-gutter-bottom'),
        ring: px(el, '--viz-ring-w'),
        marker: px(el, '--viz-marker-r'),
      });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
    // The plot element is replaced when switching back from the table view — observe the new one
  }, [showTable]);

  const scale = useMemo(() => {
    if (!geo) return null;
    const plotW = Math.max(0, geo.width - geo.start - geo.end);
    const plotH = Math.max(0, geo.height - geo.top - geo.bottom);
    const [min, max] = yDomain;
    const x = (i: number) => geo.start + (categories.length > 1 ? (i / (categories.length - 1)) * plotW : plotW / 2);
    const y = (v: number) => geo.top + ((max - Math.min(max, Math.max(min, v))) / (max - min)) * plotH;
    // Show as many x labels as fit — one label slot is the y gutter wide
    const step = Math.max(1, Math.ceil(categories.length / Math.max(1, Math.floor(plotW / Math.max(1, geo.start)))));
    // Every `step`-th label, plus the last one — dropping the regular label just before it if
    // the two would be closer than one slot and overlap
    const labelled = new Set<number>();
    for (let i = 0; i < categories.length; i += step) labelled.add(i);
    const last = categories.length - 1;
    const prev = last - (last % step);
    if (prev !== last && last - prev < step) labelled.delete(prev);
    labelled.add(last);
    return { x, y, plotW, plotH, labelled };
  }, [geo, yDomain, categories.length]);

  const lines = useMemo(() => {
    if (!scale) return [];
    return series.map((s) => {
      const points = s.values
        .map((v, i) => (v === null ? null : { i, v, x: scale.x(i), y: scale.y(v) }))
        .filter((p): p is { i: number; v: number; x: number; y: number } => p !== null);
      return { ...s, points, d: monotonePath(points), showMarkers: s.markers ?? !s.dashed };
    });
  }, [series, scale]);

  // End labels — drop one that would collide with a label already placed (legend still names it)
  const endLabels = useMemo(() => {
    const placed: { id: string; label: string; x: number; y: number }[] = [];
    for (const line of lines) {
      const last = line.points[line.points.length - 1];
      if (!last || !geo) continue;
      if (placed.some((p) => Math.abs(p.y - last.y) < geo.bottom / 2 && Math.abs(p.x - last.x) < geo.end)) continue;
      placed.push({ id: line.id, label: line.label, x: last.x, y: last.y });
    }
    return placed;
  }, [lines, geo]);

  const indexAt = useCallback(
    (clientX: number) => {
      if (!scale || !plotRef.current || categories.length === 0) return null;
      const left = plotRef.current.getBoundingClientRect().left;
      const ratio = (clientX - left - (geo?.start ?? 0)) / Math.max(1, scale.plotW);
      return Math.min(categories.length - 1, Math.max(0, Math.round(ratio * (categories.length - 1))));
    },
    [scale, geo, categories.length],
  );

  const onKeyDown = (event: React.KeyboardEvent) => {
    const last = categories.length - 1;
    const current = active ?? last;
    const next =
      event.key === 'ArrowLeft' ? Math.max(0, current - 1)
      : event.key === 'ArrowRight' ? Math.min(last, current + 1)
      : event.key === 'Home' ? 0
      : event.key === 'End' ? last
      : null;
    if (event.key === 'Escape') {
      setActive(null);
      return;
    }
    if (next === null) return;
    event.preventDefault();
    setActive(next);
  };

  const readout = active === null ? '' : `${longLabel(active)}: ${annotations.filter((a) => a.index === active).map((a) => `${a.label}. `).join('')}${series.map((s) => `${s.label} ${s.values[active] === null ? 'no data' : formatValue(s.values[active] as number)}`).join(', ')}`;

  const downloadPng = async () => {
    const svg = svgRef.current;
    if (!svg || !geo) return;
    const clone = svg.cloneNode(true) as SVGSVGElement;
    inlinePaint(svg, clone);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.querySelector('.line-chart__crosshair')?.remove();
    // Legend and title into the image, since on screen they're HTML
    const ns = 'http://www.w3.org/2000/svg';
    const legendH = geo.bottom;
    const titleH = geo.bottom;
    const style = getComputedStyle(svg);
    const textStyle = `font-family:${style.getPropertyValue('font-family')};fill:${style.getPropertyValue('--text-primary')};font-size:${style.getPropertyValue('--fs-12')}`;
    const wrapper = document.createElementNS(ns, 'svg');
    wrapper.setAttribute('xmlns', ns);
    wrapper.setAttribute('width', String(geo.width));
    wrapper.setAttribute('height', String(geo.height + legendH + titleH));
    const bg = document.createElementNS(ns, 'rect');
    bg.setAttribute('width', '100%');
    bg.setAttribute('height', '100%');
    bg.setAttribute('fill', style.getPropertyValue('--card-light') || 'white');
    wrapper.appendChild(bg);
    const heading = document.createElementNS(ns, 'text');
    heading.setAttribute('x', String(geo.start));
    heading.setAttribute('y', String(titleH / 1.5));
    heading.setAttribute('style', `${textStyle};font-weight:600`);
    heading.textContent = title;
    wrapper.appendChild(heading);
    const body = document.createElementNS(ns, 'g');
    body.setAttribute('transform', `translate(0, ${titleH})`);
    body.appendChild(clone);
    wrapper.appendChild(body);
    let x = geo.start;
    for (const s of series) {
      const stroke = style.getPropertyValue(SERIES_VAR[s.color]);
      const key = document.createElementNS(ns, 'line');
      key.setAttribute('x1', String(x));
      key.setAttribute('x2', String(x + geo.start / 2));
      key.setAttribute('y1', String(titleH + geo.height + legendH / 2));
      key.setAttribute('y2', String(titleH + geo.height + legendH / 2));
      key.setAttribute('style', `stroke:${stroke};stroke-width:${style.getPropertyValue('--viz-line-w')};${s.dashed ? `stroke-dasharray:${style.getPropertyValue('--viz-dash')}` : ''}`);
      wrapper.appendChild(key);
      const label = document.createElementNS(ns, 'text');
      label.setAttribute('x', String(x + geo.start / 2 + geo.top));
      label.setAttribute('y', String(titleH + geo.height + legendH / 2));
      label.setAttribute('dominant-baseline', 'middle');
      label.setAttribute('style', textStyle);
      label.textContent = s.label;
      wrapper.appendChild(label);
      x += geo.start + s.label.length * px(svg, '--fs-12') * 0.6 + geo.start / 2;
    }
    const data = new XMLSerializer().serializeToString(wrapper);
    const img = new Image();
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(data)}`;
    await img.decode();
    const ratio = 2;
    const canvas = document.createElement('canvas');
    canvas.width = geo.width * ratio;
    canvas.height = (geo.height + legendH + titleH) * ratio;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(ratio, ratio);
    ctx.drawImage(img, 0, 0);
    const link = document.createElement('a');
    link.download = `${title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  };

  // Close the tooltip when the pointer leaves the page
  useEffect(() => {
    const clear = () => setActive(null);
    window.addEventListener('blur', clear);
    return () => window.removeEventListener('blur', clear);
  }, []);

  const tooltipLeft = active !== null && scale && geo ? scale.x(active) : 0;
  const flip = geo ? tooltipLeft > geo.width / 2 : false;

  return (
    <div className={['line-chart', className].filter(Boolean).join(' ')}>
      <div className="line-chart__toolbar">
        <Button variant="ghost" size="sm" iconStart={<Icon name={showTable ? 'ChartLineUp' : 'ListBullets'} size="sm" />} aria-pressed={showTable} onClick={() => setShowTable((v) => !v)}>
          Table view
        </Button>
        <IconButton icon={<Icon name="DownloadSimple" size="sm" />} label={`Download ${title} as PNG`} onClick={downloadPng} />
      </div>

      {showTable ? (
        <Table
          caption={title}
          hideCaption
          rowKey={(row) => row.key}
          rows={categories.map((_, i) => ({ key: String(i), i }))}
          columns={[
            { key: 'category', header: 'Week', rowHeader: true, render: (row) => longLabel(row.i) },
            ...series.map((s) => ({
              key: s.id,
              header: s.label,
              align: 'end' as const,
              render: (row: { i: number }) => (s.values[row.i] === null ? '—' : formatValue(s.values[row.i] as number)),
            })),
          ]}
        />
      ) : (
        <>
          <div
            ref={plotRef}
            className="line-chart__plot"
            tabIndex={0}
            role="group"
            aria-label={`${title}. Use the left and right arrow keys to read each week.`}
            aria-describedby={summary ? `${id}-summary` : undefined}
            onPointerMove={(event) => setActive(indexAt(event.clientX))}
            onPointerLeave={() => setActive(null)}
            onKeyDown={onKeyDown}
            onBlur={() => setActive(null)}
          >
            {geo && scale && (
              <svg ref={svgRef} className="line-chart__svg" width={geo.width} height={geo.height} aria-hidden="true">
                {yTicks.map((tick) => (
                  <g key={tick}>
                    <line
                      className={tick === baseline ? 'line-chart__baseline' : 'line-chart__grid'}
                      x1={geo.start}
                      x2={geo.start + scale.plotW}
                      y1={scale.y(tick)}
                      y2={scale.y(tick)}
                    />
                    <text className="line-chart__tick" x={geo.start - geo.top} y={scale.y(tick)} textAnchor="end" dominantBaseline="middle">
                      {tick}
                    </text>
                  </g>
                ))}
                {categories.map((label, i) =>
                  scale.labelled.has(i) ? (
                    <text key={label + i} className="line-chart__tick" x={scale.x(i)} y={geo.height - geo.bottom / 3} textAnchor="middle">
                      {label}
                    </text>
                  ) : null,
                )}
                {active !== null && (
                  <line className="line-chart__crosshair" x1={scale.x(active)} x2={scale.x(active)} y1={geo.top} y2={geo.top + scale.plotH} />
                )}
                {lines.map((line) => (
                  <g key={line.id} className={`line-chart__series line-chart__series--${line.color}`}>
                    {line.fill && line.points.length > 1 && (
                      <path
                        className="line-chart__area"
                        d={`${line.d}L${line.points[line.points.length - 1].x},${geo.top + scale.plotH}L${line.points[0].x},${geo.top + scale.plotH}Z`}
                      />
                    )}
                    <path className={['line-chart__line', line.dashed && 'line-chart__line--dashed'].filter(Boolean).join(' ')} d={line.d} />
                    {line.points
                      .filter((p) => line.showMarkers || line.points.length === 1 || p.i === active)
                      .map((p) => (
                        <circle key={p.i} className="line-chart__marker" cx={p.x} cy={p.y} r={geo.marker} strokeWidth={geo.ring} />
                      ))}
                  </g>
                ))}
                {annotations.map((a, n) => {
                  const line = lines.find((l) => l.id === a.seriesId);
                  const value = line?.values[a.index];
                  if (!line || value === null || value === undefined) return null;
                  const cx = scale.x(a.index);
                  const cy = scale.y(value);
                  return (
                    <g key={a.id} className={`line-chart__annotation line-chart__series--${line.color}`}>
                      <circle cx={cx} cy={cy} r={geo.marker * 2} strokeWidth={geo.ring} />
                      <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central">{n + 1}</text>
                    </g>
                  );
                })}
                {endLabels.map((l) => (
                  <text key={l.id} className="line-chart__end-label" x={l.x + geo.marker + geo.ring + geo.top} y={l.y} dominantBaseline="middle">
                    {l.label}
                  </text>
                ))}
              </svg>
            )}
            {active !== null && scale && (
              <div className={['line-chart__tooltip', flip && 'line-chart__tooltip--flip'].filter(Boolean).join(' ')} style={{ insetInlineStart: tooltipLeft }} aria-hidden="true">
                <div className="line-chart__tooltip-title">{longLabel(active)}</div>
                {annotations.map((a, n) => (a.index === active ? (
                  <div key={a.id} className="line-chart__tooltip-note">{n + 1}. {a.label}</div>
                ) : null))}
                {series.map((s) => (
                  <div key={s.id} className="line-chart__tooltip-row">
                    <span className={`line-chart__key line-chart__series--${s.color}${s.dashed ? ' line-chart__key--dashed' : ''}`} />
                    <strong className="line-chart__tooltip-value">{s.values[active] === null ? '—' : formatValue(s.values[active] as number)}</strong>
                    <span>{s.label}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <span className="visually-hidden" aria-live="polite">{readout}</span>
        </>
      )}

      <ul className="line-chart__legend" aria-label={`${title} legend`}>
        {series.map((s) => (
          <li key={s.id} className="line-chart__legend-item">
            <span className={`line-chart__key line-chart__series--${s.color}${s.dashed ? ' line-chart__key--dashed' : ''}`} aria-hidden="true" />
            {s.label}
            {s.dashed && <span className="visually-hidden"> (dashed line)</span>}
          </li>
        ))}
      </ul>
      {annotations.length > 0 && (
        <ol className="line-chart__annotations" aria-label={`${title} markers`}>
          {annotations.map((a, n) => {
            const s = series.find((x) => x.id === a.seriesId);
            return (
              <li key={a.id} className="line-chart__annotation-item">
                <span className={`line-chart__annotation-number line-chart__series--${s?.color ?? 1}`} aria-hidden="true">{n + 1}</span>
                <div>
                  <div className="line-chart__annotation-label">
                    {a.label}
                    <span className="line-chart__annotation-meta"> · {s?.label} · {longLabel(a.index)}</span>
                  </div>
                  {a.detail && <div className="line-chart__annotation-detail">{a.detail}</div>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {summary && <p id={`${id}-summary`} className="visually-hidden">{summary}</p>}
    </div>
  );
}
