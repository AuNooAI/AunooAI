import './chartColors.css';

/** A chart colour: a categorical slot (1–5, 0 = neutral grey) or a sentiment role. */
export type ChartColor = 0 | 1 | 2 | 3 | 4 | 5 | 'positive' | 'negative' | 'caution' | 'neutral';

/** Class that sets `--chart-color` for an element and its children. */
export const chartColorClass = (color: ChartColor) => `chart-c-${color}`;
