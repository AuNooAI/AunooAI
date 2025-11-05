# Aunoo AI Design System

This document describes the design system implementation for Aunoo AI, based on Radix UI color scales.

## Overview

The design system provides a comprehensive set of CSS custom properties (variables) for colors, spacing, typography, and other design tokens. This ensures consistency across the application and makes it easy to maintain and update the visual design.

## Files

- **`/static/css/aunoo-theme.css`** - Main design system file with all CSS variables
- **`/static/css/styles.css`** - Component-specific styles that use the design system variables

## Color System

The color system is based on Radix UI color scales, which provide 12 steps for each color ranging from very light (#1) to very dark (#12).

### Color Scales

#### Pink (Accent Color)
Primary brand color used for interactive elements, logos, and accents.

```css
var(--colors-pink-1)   /* #fef6fb - Lightest */
var(--colors-pink-2)   /* #fee9f5 */
var(--colors-pink-3)   /* #fdd8ed */
var(--colors-pink-4)   /* #fcc5e3 */
var(--colors-pink-5)   /* #fcadd7 */
var(--colors-pink-6)   /* #fa8fc9 */
var(--colors-pink-7)   /* #f769b7 */
var(--colors-pink-8)   /* #ec4899 - Primary pink */
var(--colors-pink-9)   /* #e93d82 */
var(--colors-pink-10)  /* #d6346c */
var(--colors-pink-11)  /* #c42b5c */
var(--colors-pink-12)  /* #8b1a42 - Darkest */
```

**Semantic aliases:**
```css
var(--colors-accent-1) through var(--colors-accent-12)
var(--primary-color) = var(--colors-accent-8)  /* Legacy alias */
```

#### Slate (Neutral Colors)
Used for text, backgrounds, and UI elements.

```css
var(--colors-slate-1)   /* #fcfcfd - Near white */
var(--colors-slate-2)   /* #f8f9fa - Light gray */
var(--colors-slate-3)   /* #f1f3f5 */
var(--colors-slate-4)   /* #e9ecef */
var(--colors-slate-5)   /* #dee2e6 */
var(--colors-slate-6)   /* #ced4da */
var(--colors-slate-7)   /* #adb5bd */
var(--colors-slate-8)   /* #868e96 */
var(--colors-slate-9)   /* #495057 */
var(--colors-slate-10)  /* #343a40 */
var(--colors-slate-11)  /* #212529 */
var(--colors-slate-12)  /* #111827 - Very dark gray */
```

**Semantic aliases:**
```css
var(--colors-neutral-1) through var(--colors-neutral-12)
var(--text-color) = var(--colors-neutral-12)  /* Legacy alias */
```

#### Green (Success)
Used for positive actions, success states, and confirmations.

```css
var(--colors-green-1) through var(--colors-green-12)
var(--colors-success-1) through var(--colors-success-12)
var(--success-color) = var(--colors-success-9)
```

#### Red (Error)
Used for errors, destructive actions, and warnings.

```css
var(--colors-red-1) through var(--colors-red-12)
var(--colors-error-1) through var(--colors-error-12)
var(--danger-color) = var(--colors-error-9)
```

#### Amber (Warning)
Used for warning states and cautionary messages.

```css
var(--colors-amber-1) through var(--colors-amber-12)
var(--colors-warning-1) through var(--colors-warning-12)
var(--warning-color) = var(--colors-warning-9)
```

#### Sky (Info)
Used for informational messages and neutral actions.

```css
var(--colors-sky-1) through var(--colors-sky-12)
var(--colors-info-1) through var(--colors-info-12)
var(--info-color) = var(--colors-info-9)
```

### Color Usage Guidelines

- **Backgrounds**: Use `--colors-neutral-1` to `--colors-neutral-3` for backgrounds
- **Borders**: Use `--colors-neutral-4` to `--colors-neutral-6` for borders
- **Text**: Use `--colors-neutral-11` or `--colors-neutral-12` for body text
- **Subtle text**: Use `--colors-neutral-9` or `--colors-neutral-10` for secondary text
- **Interactive elements**: Use `--colors-accent-8` to `--colors-accent-10` for buttons, links, etc.
- **Hover states**: Use lighter shades (e.g., `--colors-accent-1` or `--colors-accent-2`) for hover backgrounds

## Spacing Scale

Consistent spacing values based on a 4px grid:

```css
var(--spacing-1)  /* 0.25rem = 4px */
var(--spacing-2)  /* 0.5rem = 8px */
var(--spacing-3)  /* 0.75rem = 12px */
var(--spacing-4)  /* 1rem = 16px */
var(--spacing-5)  /* 1.25rem = 20px */
var(--spacing-6)  /* 1.5rem = 24px */
var(--spacing-7)  /* 2rem = 32px */
var(--spacing-8)  /* 2.5rem = 40px */
var(--spacing-9)  /* 3rem = 48px */
```

**Legacy aliases:**
```css
var(--spacing-xs) = var(--spacing-1)
var(--spacing-sm) = var(--spacing-2)
var(--spacing-md) = var(--spacing-4)
var(--spacing-lg) = var(--spacing-6)
var(--spacing-xl) = var(--spacing-7)
var(--spacing-xxl) = var(--spacing-9)
```

## Border Radius Scale

```css
var(--radius-1)  /* 0.125rem = 2px */
var(--radius-2)  /* 0.25rem = 4px */
var(--radius-3)  /* 0.375rem = 6px */
var(--radius-4)  /* 0.5rem = 8px */
var(--radius-5)  /* 0.75rem = 12px */
var(--radius-6)  /* 1rem = 16px */
var(--radius-full)  /* 9999px - Full circle */
```

## Typography Scale

### Font Sizes

```css
var(--font-size-1)  /* 0.75rem = 12px */
var(--font-size-2)  /* 0.875rem = 14px */
var(--font-size-3)  /* 1rem = 16px - Base size */
var(--font-size-4)  /* 1.125rem = 18px */
var(--font-size-5)  /* 1.25rem = 20px */
var(--font-size-6)  /* 1.5rem = 24px */
var(--font-size-7)  /* 1.75rem = 28px */
var(--font-size-8)  /* 2.25rem = 36px */
var(--font-size-9)  /* 3rem = 48px */
```

### Font Families

```css
var(--font-family)  /* 'Inter', 'Roboto', 'Helvetica Neue', Arial, sans-serif */
var(--font-family-code)  /* 'Menlo', 'Monaco', 'Courier New', monospace */
```

### Font Weights

```css
var(--font-weight-light)  /* 300 */
var(--font-weight-normal)  /* 400 */
var(--font-weight-medium)  /* 500 */
var(--font-weight-bold)  /* 700 */
```

## Box Shadows

```css
var(--box-shadow)     /* 0 2px 5px rgba(0, 0, 0, 0.1) - Default */
var(--box-shadow-sm)  /* 0 1px 2px rgba(0, 0, 0, 0.05) */
var(--box-shadow-md)  /* 0 4px 6px rgba(0, 0, 0, 0.1) */
var(--box-shadow-lg)  /* 0 10px 15px rgba(0, 0, 0, 0.1) */
var(--box-shadow-xl)  /* 0 20px 25px rgba(0, 0, 0, 0.15) */
```

## Usage Examples

### Buttons

```css
.btn-topic-setup {
    background: var(--colors-neutral-3);  /* Grey background */
    border: none;
    color: var(--colors-neutral-12);  /* Dark grey text */
    padding: var(--spacing-2) var(--spacing-4);
    border-radius: var(--radius-3);
    font-size: var(--font-size-2);
    font-weight: var(--font-weight-medium);
}

.btn-topic-setup:hover {
    background: var(--colors-neutral-4);
}
```

### Cards

```css
.card {
    background: var(--colors-white);
    border: 1px solid var(--colors-neutral-4);
    border-radius: var(--radius-4);
    padding: var(--spacing-6);
    box-shadow: var(--box-shadow-sm);
}
```

### Accent Elements

```css
.logo {
    color: var(--colors-accent-8);  /* Pink brand color */
    font-size: var(--font-size-6);
    font-weight: var(--font-weight-bold);
}

.link:hover {
    background: var(--colors-accent-1);  /* Light pink hover */
    color: var(--colors-accent-8);
}
```

## Migration from Hardcoded Values

When updating existing code:

### Color Mappings

| Old Value | New Variable |
|-----------|--------------|
| `#ec4899` | `var(--colors-accent-8)` or `var(--primary-color)` |
| `#FF69B4` | `var(--colors-accent-7)` |
| `#111827` | `var(--colors-neutral-12)` or `var(--text-color)` |
| `#f3f4f6` | `var(--colors-neutral-3)` |
| `#e5e7eb` | `var(--colors-neutral-4)` |
| `#10b981` | `var(--colors-success-9)` or `var(--success-color)` |
| `#dc3545` | `var(--colors-error-9)` or `var(--danger-color)` |
| `white` | `var(--colors-white)` |
| `#f8f9fa` | `var(--colors-neutral-2)` or `var(--light-gray)` |

### Spacing Mappings

| Old Value | New Variable |
|-----------|--------------|
| `0.25rem` or `4px` | `var(--spacing-1)` |
| `0.5rem` or `8px` | `var(--spacing-2)` |
| `1rem` or `16px` | `var(--spacing-4)` |
| `1.5rem` or `24px` | `var(--spacing-6)` |
| `2rem` or `32px` | `var(--spacing-7)` |

## Benefits

1. **Consistency**: All colors and spacing follow a defined scale
2. **Maintainability**: Change colors/spacing in one place
3. **Accessibility**: Predefined color contrast ratios
4. **Theming**: Easy to create alternative themes (dark mode, etc.)
5. **Developer Experience**: Clear, semantic variable names

## Future Enhancements

- [ ] Dark mode theme implementation
- [ ] Alternative color schemes (blue, purple, etc.)
- [ ] Component library documentation
- [ ] Storybook integration
- [ ] CSS-in-JS migration for React components
