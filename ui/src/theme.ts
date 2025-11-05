/**
 * Aunoo AI Design System - TypeScript/React Integration
 *
 * This file provides TypeScript-friendly access to the design system
 * defined in /static/css/aunoo-theme.css
 */

export const colors = {
  // Pink (Accent)
  pink: {
    1: '#fef6fb',
    2: '#fee9f5',
    3: '#fdd8ed',
    4: '#fcc5e3',
    5: '#fcadd7',
    6: '#fa8fc9',
    7: '#f769b7',
    8: '#ec4899', // Primary
    9: '#e93d82',
    10: '#d6346c',
    11: '#c42b5c',
    12: '#8b1a42',
  },

  // Slate (Neutral)
  slate: {
    1: '#fcfcfd',
    2: '#f8f9fa',
    3: '#f1f3f5',
    4: '#e9ecef',
    5: '#dee2e6',
    6: '#ced4da',
    7: '#adb5bd',
    8: '#868e96',
    9: '#495057',
    10: '#343a40',
    11: '#212529',
    12: '#111827',
  },

  // Green (Success)
  green: {
    1: '#f0fdf4',
    2: '#dcfce7',
    3: '#bbf7d0',
    4: '#86efac',
    5: '#4ade80',
    6: '#22c55e',
    7: '#16a34a',
    8: '#15803d',
    9: '#10b981', // Primary
    10: '#059669',
    11: '#047857',
    12: '#064e3b',
  },

  // Red (Error)
  red: {
    1: '#fef2f2',
    2: '#fee2e2',
    3: '#fecaca',
    4: '#fca5a5',
    5: '#f87171',
    6: '#ef4444',
    7: '#dc2626',
    8: '#b91c1c',
    9: '#dc3545', // Primary
    10: '#991b1b',
    11: '#7f1d1d',
    12: '#450a0a',
  },

  // Amber (Warning)
  amber: {
    1: '#fffbeb',
    2: '#fef3c7',
    3: '#fde68a',
    4: '#fcd34d',
    5: '#fbbf24',
    6: '#f59e0b',
    7: '#d97706',
    8: '#b45309',
    9: '#ffc107', // Primary
    10: '#92400e',
    11: '#78350f',
    12: '#451a03',
  },

  // Sky (Info)
  sky: {
    1: '#f0f9ff',
    2: '#e0f2fe',
    3: '#bae6fd',
    4: '#7dd3fc',
    5: '#38bdf8',
    6: '#0ea5e9',
    7: '#0284c7',
    8: '#0369a1',
    9: '#17a2b8', // Primary
    10: '#075985',
    11: '#0c4a6e',
    12: '#082f49',
  },

  // Semantic colors
  accent: {
    1: '#fef6fb',
    2: '#fee9f5',
    3: '#fdd8ed',
    4: '#fcc5e3',
    5: '#fcadd7',
    6: '#fa8fc9',
    7: '#f769b7',
    8: '#ec4899',
    9: '#e93d82',
    10: '#d6346c',
    11: '#c42b5c',
    12: '#8b1a42',
  },

  neutral: {
    1: '#fcfcfd',
    2: '#f8f9fa',
    3: '#f1f3f5',
    4: '#e9ecef',
    5: '#dee2e6',
    6: '#ced4da',
    7: '#adb5bd',
    8: '#868e96',
    9: '#495057',
    10: '#343a40',
    11: '#212529',
    12: '#111827',
  },

  success: {
    1: '#f0fdf4',
    2: '#dcfce7',
    3: '#bbf7d0',
    4: '#86efac',
    5: '#4ade80',
    6: '#22c55e',
    7: '#16a34a',
    8: '#15803d',
    9: '#10b981',
    10: '#059669',
    11: '#047857',
    12: '#064e3b',
  },

  error: {
    1: '#fef2f2',
    2: '#fee2e2',
    3: '#fecaca',
    4: '#fca5a5',
    5: '#f87171',
    6: '#ef4444',
    7: '#dc2626',
    8: '#b91c1c',
    9: '#dc3545',
    10: '#991b1b',
    11: '#7f1d1d',
    12: '#450a0a',
  },

  warning: {
    1: '#fffbeb',
    2: '#fef3c7',
    3: '#fde68a',
    4: '#fcd34d',
    5: '#fbbf24',
    6: '#f59e0b',
    7: '#d97706',
    8: '#b45309',
    9: '#ffc107',
    10: '#92400e',
    11: '#78350f',
    12: '#451a03',
  },

  info: {
    1: '#f0f9ff',
    2: '#e0f2fe',
    3: '#bae6fd',
    4: '#7dd3fc',
    5: '#38bdf8',
    6: '#0ea5e9',
    7: '#0284c7',
    8: '#0369a1',
    9: '#17a2b8',
    10: '#075985',
    11: '#0c4a6e',
    12: '#082f49',
  },

  // Basic colors
  white: '#ffffff',
  black: '#000000',
};

export const spacing = {
  1: '0.25rem',  // 4px
  2: '0.5rem',   // 8px
  3: '0.75rem',  // 12px
  4: '1rem',     // 16px
  5: '1.25rem',  // 20px
  6: '1.5rem',   // 24px
  7: '2rem',     // 32px
  8: '2.5rem',   // 40px
  9: '3rem',     // 48px
};

export const radius = {
  1: '0.125rem',  // 2px
  2: '0.25rem',   // 4px
  3: '0.375rem',  // 6px
  4: '0.5rem',    // 8px
  5: '0.75rem',   // 12px
  6: '1rem',      // 16px
  full: '9999px',
};

export const fontSize = {
  1: '0.75rem',   // 12px
  2: '0.875rem',  // 14px
  3: '1rem',      // 16px
  4: '1.125rem',  // 18px
  5: '1.25rem',   // 20px
  6: '1.5rem',    // 24px
  7: '1.75rem',   // 28px
  8: '2.25rem',   // 36px
  9: '3rem',      // 48px
};

export const fontWeight = {
  light: 300,
  normal: 400,
  medium: 500,
  bold: 700,
};

export const boxShadow = {
  sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
  base: '0 2px 5px rgba(0, 0, 0, 0.1)',
  md: '0 4px 6px rgba(0, 0, 0, 0.1)',
  lg: '0 10px 15px rgba(0, 0, 0, 0.1)',
  xl: '0 20px 25px rgba(0, 0, 0, 0.15)',
};

// Tailwind-compatible utilities
export const theme = {
  colors,
  spacing,
  radius,
  fontSize,
  fontWeight,
  boxShadow,
};

// Helper function to get CSS variable reference
export const cssVar = (path: string): string => {
  return `var(--${path})`;
};

// Common color helpers
export const primary = colors.accent[8];
export const primaryHover = colors.accent[9];
export const text = colors.neutral[12];
export const textLight = colors.neutral[9];
export const background = colors.neutral[2];
export const border = colors.neutral[4];

export default theme;
