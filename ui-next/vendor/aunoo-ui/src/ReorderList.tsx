import { useEffect, useId, useRef, useState } from 'react';
import { Icon } from './Icon';
import './ReorderList.css';

export interface ReorderListItem {
  id: string;
  /** Plain-text name, used in the handle's label and announcements ("CPU moved to position 2 of 6"). */
  label: string;
  /** Row content after the handle, e.g. a `<Checkbox>`. Defaults to the label. */
  content?: React.ReactNode;
}

export interface ReorderListProps {
  /** `[{ id, label, content? }]` in their current order. */
  items: ReorderListItem[];
  /** `(ids) => void` — the new order. The parent owns the order (controlled). */
  onReorder: (ids: string[]) => void;
  /** Accessible name for the list, e.g. "Metrics". */
  label: string;
  className?: string;
}

function move(ids: string[], from: number, to: number) {
  const next = [...ids];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/**
 * List the user can reorder: drag a row by its handle (mouse or touch), or focus the handle and
 * press ↑/↓. Moves are announced to screen readers.
 */
export function ReorderList({ items, onReorder, label, className }: ReorderListProps) {
  const hintId = useId();
  const rowRefs = useRef(new Map<string, HTMLLIElement>());
  const handleRefs = useRef(new Map<string, HTMLButtonElement>());
  const [dragId, setDragId] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const [focusId, setFocusId] = useState<string | null>(null);
  const ids = items.map((item) => item.id);

  // Keep keyboard focus on the moved item's handle after the parent re-renders the new order.
  useEffect(() => {
    if (focusId) {
      handleRefs.current.get(focusId)?.focus();
      setFocusId(null);
    }
  }, [focusId, items]);

  const announce = (item: ReorderListItem, index: number) =>
    setAnnouncement(`${item.label} moved to position ${index + 1} of ${items.length}`);

  const onKeyDown = (event: React.KeyboardEvent, item: ReorderListItem, index: number) => {
    const to = event.key === 'ArrowUp' ? index - 1 : event.key === 'ArrowDown' ? index + 1 : null;
    if (to === null) return;
    event.preventDefault();
    if (to < 0 || to >= items.length) return;
    onReorder(move(ids, index, to));
    announce(item, to);
    setFocusId(item.id);
  };

  const onPointerDown = (event: React.PointerEvent<HTMLButtonElement>, id: string) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragId(id);
  };

  const onPointerMove = (event: React.PointerEvent) => {
    if (!dragId) return;
    const from = ids.indexOf(dragId);
    // Target = how many of the other rows have their middle above the pointer
    const to = ids
      .filter((id) => id !== dragId)
      .filter((id) => {
        const rect = rowRefs.current.get(id)?.getBoundingClientRect();
        return rect ? rect.top + rect.height / 2 < event.clientY : false;
      }).length;
    if (to !== from) onReorder(move(ids, from, to));
  };

  const onPointerEnd = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (!dragId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const index = ids.indexOf(dragId);
    if (index >= 0) announce(items[index], index);
    setDragId(null);
  };

  return (
    <>
      <ul className={['reorder-list', className].filter(Boolean).join(' ')} aria-label={label}>
        {items.map((item, index) => (
          <li
            key={item.id}
            ref={(node) => {
              if (node) rowRefs.current.set(item.id, node);
              else rowRefs.current.delete(item.id);
            }}
            className="reorder-list__row"
            data-dragging={dragId === item.id ? '' : undefined}
          >
            <button
              type="button"
              ref={(node) => {
                if (node) handleRefs.current.set(item.id, node);
                else handleRefs.current.delete(item.id);
              }}
              className="reorder-list__handle"
              aria-label={`Reorder ${item.label}, position ${index + 1} of ${items.length}`}
              aria-describedby={hintId}
              onKeyDown={(event) => onKeyDown(event, item, index)}
              onPointerDown={(event) => onPointerDown(event, item.id)}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerEnd}
              onPointerCancel={onPointerEnd}
            >
              <Icon name="DotsSixVertical" size="sm" />
            </button>
            <div className="reorder-list__content">{item.content ?? item.label}</div>
          </li>
        ))}
      </ul>
      <span id={hintId} className="visually-hidden">Press the up or down arrow key to move.</span>
      <span className="visually-hidden" role="status" aria-live="polite">{announcement}</span>
    </>
  );
}
