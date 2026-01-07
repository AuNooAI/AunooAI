/**
 * Global event system for opening Auspex chat with pre-filled queries
 *
 * Usage:
 * ```ts
 * import { openAuspexWithQuery } from '../utils/auspexEvents';
 *
 * // Open Auspex and pre-fill the input
 * openAuspexWithQuery('Analyze the impact of AI on healthcare');
 * ```
 */

// Custom event name
export const AUSPEX_OPEN_EVENT = 'auspex:open';

// Event detail type
export interface AuspexOpenEventDetail {
  query: string;
  autoSend?: boolean;  // If true, automatically send the query
}

/**
 * Opens the Auspex chat modal with an optional pre-filled query
 * @param query The query to pre-fill in the chat input
 * @param autoSend If true, automatically sends the query (default: false)
 */
export function openAuspexWithQuery(query: string, autoSend: boolean = false): void {
  const event = new CustomEvent<AuspexOpenEventDetail>(AUSPEX_OPEN_EVENT, {
    detail: { query, autoSend },
    bubbles: true,
    cancelable: true,
  });
  window.dispatchEvent(event);
}

/**
 * Opens the Auspex chat modal without a query
 */
export function openAuspex(): void {
  const event = new CustomEvent<AuspexOpenEventDetail>(AUSPEX_OPEN_EVENT, {
    detail: { query: '' },
    bubbles: true,
    cancelable: true,
  });
  window.dispatchEvent(event);
}

// Type for the event listener callback
export type AuspexOpenHandler = (detail: AuspexOpenEventDetail) => void;
