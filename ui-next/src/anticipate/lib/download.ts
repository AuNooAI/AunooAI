import { ApiError } from '../../shell';

/** Fetches a file with the session cookie and hands it to the browser as a download. */
export async function downloadFile(url: string, filename: string) {
  const res = await fetch(url, { credentials: 'same-origin' });
  if (!res.ok) throw new ApiError(res.status === 404 ? 'Not found — generate the analysis first' : `${res.status} ${res.statusText}`, res.status);
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename.replace(/[\\/:*?"<>|]+/g, '-');
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}

/** Saves text as a file. */
export function saveText(text: string, filename: string, type = 'text/plain') {
  const href = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = href;
  a.download = filename.replace(/[\\/:*?"<>|]+/g, '-');
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}

/**
 * Saves an element as a PNG. html2canvas loads on first use, so it stays out of the page bundle.
 * The page background is painted in, so dark mode doesn't export as dark text on transparency.
 */
export async function savePng(el: HTMLElement, filename: string) {
  const { default: html2canvas } = await import('html2canvas');
  const canvas = await html2canvas(el, {
    backgroundColor: getComputedStyle(document.body).backgroundColor || '#ffffff',
    scale: Math.min(2, window.devicePixelRatio || 1) * 1.5,
    useCORS: true,
    logging: false,
  });
  const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, 'image/png'));
  if (!blob) throw new Error('The browser couldn’t encode the image');
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename.replace(/[\\/:*?"<>|]+/g, '-');
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}

/** File-name slug: "AI and Machine Learning" → "ai-and-machine-learning". */
export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'export';
