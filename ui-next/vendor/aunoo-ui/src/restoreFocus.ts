/**
 * Focus after an app-opened Dialog or Sheet closes: back to the element that had focus when it
 * opened. If that element is gone (the dialog deleted it), fall back to the dialog underneath,
 * so keyboard focus isn't dropped on <body>. Internal helper — not exported from the barrel.
 */
export function restoreFocus(opener: HTMLElement | null, closing: HTMLElement | null) {
  if (opener?.isConnected) {
    opener.focus();
    return;
  }
  const open = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]')).filter((el) => el !== closing);
  open.at(-1)?.focus();
}
