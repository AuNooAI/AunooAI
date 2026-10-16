import { useId } from 'react';
import * as RadixSlider from '@radix-ui/react-slider';
import './Slider.css';

export interface SliderProps {
  /** Visible label (the accessible name), e.g. "Relevance threshold". */
  label: string;
  /** Controlled value. Pair with `onValueChange`. */
  value: number;
  /** `(value) => void` — called while dragging and on arrow keys. */
  onValueChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  /** Pre-formatted reading shown after the label and announced, e.g. "60%" or "Off". */
  valueText?: string;
  /** Helper text under the track. */
  hint?: React.ReactNode;
  disabled?: boolean;
  id?: string;
  className?: string;
}

/**
 * Single-value range input (Radix Slider: arrow keys, Home/End, Page Up/Down). The track uses
 * chipCount like Switch's off track; the filled part and thumb use the accent (§3.1 on state).
 */
export function Slider({ label, value, onValueChange, min = 0, max = 100, step = 1, valueText, hint, disabled = false, id: idProp, className }: SliderProps) {
  const autoId = useId();
  const id = idProp ?? autoId;
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className={['slider', className].filter(Boolean).join(' ')} data-disabled={disabled ? '' : undefined}>
      <div className="slider__head">
        <label id={`${id}-label`} className="slider__label">{label}</label>
        <span className="slider__value" aria-hidden="true">{valueText ?? value}</span>
      </div>
      <RadixSlider.Root
        className="slider__root"
        value={[value]}
        onValueChange={([next]) => onValueChange(next)}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
      >
        <RadixSlider.Track className="slider__track">
          <RadixSlider.Range className="slider__range" />
        </RadixSlider.Track>
        <RadixSlider.Thumb
          className="slider__thumb"
          aria-labelledby={`${id}-label`}
          aria-describedby={hintId}
          aria-valuetext={valueText}
        />
      </RadixSlider.Root>
      {hint && <p id={hintId} className="slider__hint">{hint}</p>}
    </div>
  );
}
