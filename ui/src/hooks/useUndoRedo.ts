/**
 * useUndoRedo Hook
 * Provides undo/redo functionality for text editing with debounced history
 */

import { useState, useCallback, useRef, useEffect } from 'react';

interface HistoryState {
  past: string[];
  present: string;
  future: string[];
}

const MAX_HISTORY_SIZE = 50;
const DEBOUNCE_MS = 500;

export function useUndoRedo(initialValue: string) {
  const [state, setState] = useState<HistoryState>({
    past: [],
    present: initialValue,
    future: []
  });

  // Debounce timer for grouping rapid changes
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const lastValueRef = useRef(initialValue);
  const isInternalUpdateRef = useRef(false);

  /**
   * Set new value with optional immediate history push
   */
  const set = useCallback((newValue: string, immediate = false) => {
    // Clear existing debounce
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }

    if (immediate) {
      // Immediately add to history
      setState(prev => ({
        past: [...prev.past, prev.present].slice(-MAX_HISTORY_SIZE),
        present: newValue,
        future: []
      }));
      lastValueRef.current = newValue;
    } else {
      // Update present immediately for UI responsiveness
      setState(prev => ({ ...prev, present: newValue }));

      // Debounce: only add to history after pause in typing
      debounceRef.current = setTimeout(() => {
        if (lastValueRef.current !== newValue) {
          setState(prev => ({
            past: [...prev.past, lastValueRef.current].slice(-MAX_HISTORY_SIZE),
            present: newValue,
            future: []
          }));
          lastValueRef.current = newValue;
        }
      }, DEBOUNCE_MS);
    }
  }, []);

  /**
   * Undo to previous state
   */
  const undo = useCallback(() => {
    setState(prev => {
      if (prev.past.length === 0) return prev;

      const previous = prev.past[prev.past.length - 1];
      const newPast = prev.past.slice(0, -1);

      lastValueRef.current = previous;
      isInternalUpdateRef.current = true;

      return {
        past: newPast,
        present: previous,
        future: [prev.present, ...prev.future]
      };
    });
  }, []);

  /**
   * Redo to next state
   */
  const redo = useCallback(() => {
    setState(prev => {
      if (prev.future.length === 0) return prev;

      const next = prev.future[0];
      const newFuture = prev.future.slice(1);

      lastValueRef.current = next;
      isInternalUpdateRef.current = true;

      return {
        past: [...prev.past, prev.present],
        present: next,
        future: newFuture
      };
    });
  }, []);

  /**
   * Reset history with new initial value
   */
  const reset = useCallback((value: string) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    lastValueRef.current = value;
    setState({
      past: [],
      present: value,
      future: []
    });
  }, []);

  /**
   * Clear all history but keep current value
   */
  const clearHistory = useCallback(() => {
    setState(prev => ({
      past: [],
      present: prev.present,
      future: []
    }));
  }, []);

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  return {
    value: state.present,
    set,
    undo,
    redo,
    reset,
    clearHistory,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
    historyLength: state.past.length,
    futureLength: state.future.length
  };
}
