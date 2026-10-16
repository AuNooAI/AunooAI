/*
 * File exports shared by every Explore page: a PDF from Markdown (jsPDF), a PNG of one element on
 * the page (html2canvas), and a CSV from rows. All three build the file in the browser; nothing is
 * sent to the server.
 */

const AI_LINE = 'Generated with AI from collected sources and may contain errors. Check the linked source before acting on it.';

function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** jsPDF's built-in fonts only cover Latin-1; swap the common typographic characters for plain ones */
function latin1(s: string) {
  return s
    .replace(/[‘’‛]/g, "'")
    .replace(/[“”‟]/g, '"')
    .replace(/[–—−]/g, '-')
    .replace(/…/g, '...')
    .replace(/[•●▪]/g, '-')
    .replace(/ /g, ' ')
    .replace(/[^\x00-\xFF]/g, '');
}

/** Inline Markdown to plain text, keeping link targets so they can be made clickable */
function inline(s: string): { text: string; links: { label: string; url: string }[] } {
  const links: { label: string; url: string }[] = [];
  let text = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, label: string, url: string) => {
    links.push({ label, url });
    return label;
  });
  text = text.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/__([^_]+)__/g, '$1').replace(/(^|\W)\*([^*]+)\*(?=\W|$)/g, '$1$2').replace(/`([^`]+)`/g, '$1');
  return { text: latin1(text), links };
}

/** A PDF built from Markdown (headings, lists, links, tables) with the page's AI disclosure line at the foot */
export async function downloadPdf(opts: { filename: string; title: string; markdown: string; subtitle?: string }): Promise<void> {
  const { jsPDF } = await import('jspdf');
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const M = 48;
  const width = W - M * 2;
  let y = M;

  const ensure = (h: number) => {
    if (y + h > H - M) {
      doc.addPage();
      y = M;
    }
  };
  const write = (raw: string, size: number, style: 'normal' | 'bold' = 'normal', indent = 0, gapAfter = 4) => {
    const { text, links } = inline(raw);
    doc.setFont('helvetica', style);
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(text, width - indent) as string[];
    const lh = size * 1.35;
    for (const line of lines) {
      ensure(lh);
      doc.text(line, M + indent, y + size);
      // A line that holds a link's label becomes clickable over its width
      for (const l of links) {
        const at = line.indexOf(latin1(l.label));
        if (at >= 0) {
          const x = M + indent + doc.getTextWidth(line.slice(0, at));
          doc.link(x, y, doc.getTextWidth(latin1(l.label)), lh, { url: l.url });
        }
      }
      y += lh;
    }
    y += gapAfter;
  };

  write(opts.title, 18, 'bold', 0, 2);
  if (opts.subtitle) write(opts.subtitle, 10, 'normal', 0, 2);
  doc.setFontSize(9);
  doc.setTextColor(110);
  write(`Exported ${new Date().toLocaleString('en-GB')}`, 9, 'normal', 0, 10);
  doc.setTextColor(20);

  const lines = opts.markdown.replace(/\r/g, '').split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const t = line.trim();
    if (!t) {
      y += 4;
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(t);
    if (h) {
      y += 6;
      write(h[2], h[1].length === 1 ? 15 : h[1].length === 2 ? 13 : 11.5, 'bold', 0, 3);
      continue;
    }
    if (/^(-{3,}|\*{3,})$/.test(t)) {
      ensure(10);
      doc.setDrawColor(200);
      doc.line(M, y + 4, W - M, y + 4);
      y += 12;
      continue;
    }
    // Tables: header and rows as tab-separated text; the separator row is skipped
    if (t.startsWith('|')) {
      if (/^\|?\s*:?-{2,}/.test(t)) continue;
      const cells = t.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
      const isHeader = /^\|?\s*:?-{2,}/.test((lines[i + 1] ?? '').trim());
      write(cells.join('   |   '), 9.5, isHeader ? 'bold' : 'normal', 0, 2);
      continue;
    }
    const bullet = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line);
    if (bullet) {
      const depth = Math.min(3, Math.floor(bullet[1].length / 2));
      const mark = /\d/.test(bullet[2]) ? bullet[2] : '-';
      write(`${mark} ${bullet[3]}`, 10.5, 'normal', 12 + depth * 12, 2);
      continue;
    }
    if (t.startsWith('>')) {
      doc.setTextColor(90);
      write(t.replace(/^>\s?/, ''), 10.5, 'normal', 12, 3);
      doc.setTextColor(20);
      continue;
    }
    write(t, 10.5, 'normal', 0, 4);
  }

  y += 8;
  doc.setTextColor(110);
  write(AI_LINE, 8.5, 'normal', 0, 0);
  doc.save(opts.filename.endsWith('.pdf') ? opts.filename : `${opts.filename}.pdf`);
}

/** A PNG of one element on the page (a chart or a card), for "Download as image" */
export async function downloadElementPng(el: HTMLElement, filename: string): Promise<void> {
  const html2canvas = (await import('html2canvas')).default;
  const bg = getComputedStyle(document.body).backgroundColor || '#ffffff';
  const canvas = await html2canvas(el, { backgroundColor: bg, scale: Math.min(2, window.devicePixelRatio || 1) * 1.5, useCORS: true, logging: false });
  const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, 'image/png'));
  if (!blob) throw new Error('The image could not be made');
  save(blob, filename.endsWith('.png') ? filename : `${filename}.png`);
}

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return '';
  const s = Array.isArray(v) ? v.join('; ') : typeof v === 'object' ? JSON.stringify(v) : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** A CSV file from rows; columns in the order given */
export function downloadCsv(filename: string, rows: Record<string, unknown>[], columns?: string[]): void {
  const cols = columns ?? [...new Set(rows.flatMap((r) => Object.keys(r)))];
  const text = [cols.map(csvCell).join(','), ...rows.map((r) => cols.map((c) => csvCell(r[c])).join(','))].join('\r\n');
  // The byte-order mark lets Excel read accented characters correctly
  save(new Blob(['﻿' + text], { type: 'text/csv;charset=utf-8' }), filename.endsWith('.csv') ? filename : `${filename}.csv`);
}
