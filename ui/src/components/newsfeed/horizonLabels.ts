/**
 * Label placement for the Market Horizon map. The same rules as the shared
 * report's SVG (app/services/market_report_html.py, `_label_spots`): no
 * label sits on a dot, another label or a leader line, and no leader line
 * crosses one either.
 */

export type LabelDot = { x: number; y: number; ring: number; width: number };
export type LabelSpot = {
  bx: number; by: number; tx: number; anchor: 'start' | 'end' | 'middle';
  hits: number; leader: { x1: number; y1: number; x2: number; y2: number } | null;
};

/** About how wide the label is at 10px in a sans-serif face, from the
 * letters in it. Slightly generous, so a wider face still fits. */
export function labelWidth(text: string): number {
  let total = 4;
  for (const ch of text) {
    if ("iljtfr .'-,".includes(ch)) total += 3;
    else if ('mwMW'.includes(ch)) total += 8.5;
    else if (/[A-Z0-9]/.test(ch)) total += 7;
    else total += 5.8;
  }
  return total;
}

/** Does the segment cross the box? Liang–Barsky clipping. */
function segHitsBox(x1: number, y1: number, x2: number, y2: number,
                    bx: number, by: number, bw: number, bh: number): boolean {
  const dx = x2 - x1, dy = y2 - y1;
  let t0 = 0, t1 = 1;
  const edges: [number, number][] = [[-dx, x1 - bx], [dx, bx + bw - x1], [-dy, y1 - by], [dy, by + bh - y1]];
  for (const [p, q] of edges) {
    if (p === 0) { if (q < 0) return false; continue; }
    const t = q / p;
    if (p < 0) { if (t > t1) return false; t0 = Math.max(t0, t); }
    else { if (t < t0) return false; t1 = Math.min(t1, t); }
  }
  return t0 <= t1;
}

type Seg = { x1: number; y1: number; x2: number; y2: number };

/** Do two segments cross? */
function segsCross(a: Seg, b: Seg): boolean {
  const side = (px: number, py: number, qx: number, qy: number, rx: number, ry: number) =>
    (qx - px) * (ry - py) - (qy - py) * (rx - px);
  const d1 = side(b.x1, b.y1, b.x2, b.y2, a.x1, a.y1), d2 = side(b.x1, b.y1, b.x2, b.y2, a.x2, a.y2);
  const d3 = side(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1), d4 = side(a.x1, a.y1, a.x2, a.y2, b.x2, b.y2);
  return ((d1 > 0) !== (d2 > 0)) && ((d3 > 0) !== (d4 > 0));
}

/** How far the point is from the nearest point of the segment. */
function segNearPoint(x1: number, y1: number, x2: number, y2: number, px: number, py: number): number {
  const dx = x2 - x1, dy = y2 - y1, l2 = dx * dx + dy * dy;
  const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / l2));
  return Math.hypot(x1 + t * dx - px, y1 + t * dy - py);
}

/** Does the box overlap the circle? */
function boxHitsRing(bx: number, by: number, bw: number, bh: number, cx: number, cy: number, r: number): boolean {
  const nx = Math.max(bx, Math.min(cx, bx + bw)), ny = Math.max(by, Math.min(cy, by + bh));
  return Math.hypot(nx - cx, ny - cy) < r;
}

// Twenty-four directions a label can sit in, and the distances it can
// stand off, nearest first.
const DIRS: [number, number][] = [];
for (let a = 0; a < 360; a += 15) DIRS.push([Math.cos(a * Math.PI / 180), Math.sin(a * Math.PI / 180)]);
const STEPS = [0, 8, 16, 24, 34, 46, 60, 76, 94, 115, 140];

/**
 * Where every dot's label goes. A zero label width is a dot with no label
 * (it still keeps labels off itself); `width` and `maxY` bound the labels
 * on the right and below. Returns one entry per dot, null for the
 * unlabelled. `obstacles` are boxes already on the map (the band names)
 * that a label must keep off.
 *
 * Two passes. First, every label that fits beside its own dot takes that
 * spot, most crowded dots first, so nothing later can take it. Then the
 * labels that did not fit move out on a leader line, nearest clear spot
 * first, preferring the side that faces away from the dot's neighbours so
 * a crowd's labels fan outwards instead of across each other.
 */
export function labelSpots(dots: LabelDot[], height: number, width: number, maxY: number,
                           obstacles: { x: number; y: number; w: number; h: number }[] = []): (LabelSpot | null)[] {
  const n = dots.length;
  // `obstacles` are boxes already on the map that a label must keep off.
  const labels: { x: number; y: number; w: number; h: number }[] = [...obstacles];
  const leaders: Seg[] = [];
  const neighbours = (i: number) => {
    const out: number[] = [];
    for (let j = 0; j < n; j++) {
      if (j !== i && Math.abs(dots[j].x - dots[i].x) < 48 && Math.abs(dots[j].y - dots[i].y) < 48) out.push(j);
    }
    return out;
  };
  const crowd = dots.map((_, i) => neighbours(i).length);
  const order = dots.map((_, i) => i).filter(i => dots[i].width > 0)
    .sort((a, b) => (crowd[b] - crowd[a]) || (dots[a].y - dots[b].y) || (dots[a].x - dots[b].x));
  const out: (LabelSpot | null)[] = dots.map(() => null);

  const candidate = (i: number, step: number, ux: number, uy: number): LabelSpot | null => {
    const { x, y, ring: g, width: w } = dots[i];
    const d = g + 2 + step;
    const px = x + d * ux, py = y + d * uy;
    const bx = px - w / 2 + ux * w / 2, by = py - height / 2 + uy * height / 2;
    if (bx < 0 || bx + w > width || by < 0 || by + height > maxY) return null;
    // Overlap, weighted: text over text or over a dot is the worst (10), a
    // label under a leader line or a leader line over text next (6), a
    // leader line through a dot's core (2), a label brushing a marker ring
    // or two leader lines crossing (1). A leader line may pass under a
    // marker ring; the dot itself is drawn over it.
    let hits = 0;
    for (let k = 0; k < n; k++) {
      if (k === i) continue;
      const o = dots[k];
      if (boxHitsRing(bx - 2, by - 1, w + 4, height + 2, o.x, o.y, o.ring)) {
        hits += boxHitsRing(bx, by, w, height, o.x, o.y, 6) ? 10 : 1;
      }
    }
    for (const l of labels) {
      if (bx - 3 < l.x + l.w && l.x < bx + w + 3 && by - 2 < l.y + l.h && l.y < by + height + 2) hits += 10;
    }
    for (const s of leaders) if (segHitsBox(s.x1, s.y1, s.x2, s.y2, bx, by, w, height)) hits += 6;
    const sx = x + (g + 1) * ux, sy = y + (g + 1) * uy;
    if (step > 0) {
      for (let k = 0; k < n; k++) {
        if (k === i) continue;
        const o = dots[k];
        if (Math.hypot(sx - o.x, sy - o.y) >= 6 && segNearPoint(sx, sy, px, py, o.x, o.y) < 6) hits += 2;
      }
      for (const l of labels) if (segHitsBox(sx, sy, px, py, l.x, l.y, l.w, l.h)) hits += 6;
      for (const s of leaders) if (segsCross({ x1: sx, y1: sy, x2: px, y2: py }, s)) hits += 1;
    }
    const anchor = ux > 0.35 ? 'start' : ux < -0.35 ? 'end' : 'middle';
    return {
      bx, by, anchor, hits,
      tx: anchor === 'start' ? bx : anchor === 'end' ? bx + w : bx + w / 2,
      leader: step === 0 ? null : { x1: sx, y1: sy, x2: px, y2: py },
    };
  };
  const take = (i: number, spot: LabelSpot) => {
    labels.push({ x: spot.bx, y: spot.by, w: dots[i].width, h: height });
    if (spot.leader) leaders.push(spot.leader);
    out[i] = spot;
  };

  // Pass one: beside the dot, sideways before up or down.
  const sideways = [...DIRS].sort((a, b) => Math.abs(a[1]) - Math.abs(b[1]));
  for (const i of order) {
    for (const [ux, uy] of sideways) {
      const c = candidate(i, 0, ux, uy);
      if (c && c.hits === 0) { take(i, c); break; }
    }
  }
  // Pass two: out on a leader line. A spot's price is its distance plus
  // what it overlaps; one point of overlap costs the same as forty pixels
  // of leader line, so a label goes a long way round to avoid text but not
  // to avoid a ring's edge.
  for (const i of order) {
    if (out[i]) continue;
    const { x, y } = dots[i];
    const nb = neighbours(i);
    let away: [number, number] | null = null;
    if (nb.length) {
      const mx = nb.reduce((s, j) => s + dots[j].x, 0) / nb.length;
      const my = nb.reduce((s, j) => s + dots[j].y, 0) / nb.length;
      const norm = Math.hypot(x - mx, y - my);
      if (norm > 0.5) away = [(x - mx) / norm, (y - my) / norm];
    }
    let best: LabelSpot | null = null, bestCost = Infinity;
    for (const step of STEPS) {
      for (const [ux, uy] of DIRS) {
        const cost = step + 3 * Math.abs(uy) + (away ? 12 * (1 - (ux * away[0] + uy * away[1])) : 0);
        if (cost >= bestCost) continue;
        const c = candidate(i, step, ux, uy);
        if (c && cost + 40 * c.hits < bestCost) { best = c; bestCost = cost + 40 * c.hits; }
      }
      if (bestCost <= step + 3) break;
    }
    if (best) take(i, best);
  }
  return out;
}
