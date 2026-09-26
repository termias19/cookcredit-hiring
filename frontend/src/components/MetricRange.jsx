import { useId } from 'react'
import './MetricRange.css'

// Native inputs retain keyboard, touch and screen-reader behavior.
export default function MetricRange({ title, minimum, maximum, limit = 100, step = 1, unit = '/ 100', onChange }) {
  const id = useId()
  return <fieldset className="cc-metric-range">
    <legend>{title}: <strong>{minimum}–{maximum} {unit}</strong></legend>
    <div className="cc-metric-range-track" style={{ '--range-start': `${minimum / limit * 100}%`, '--range-end': `${maximum / limit * 100}%` }} aria-hidden="true" />
    <div className="cc-metric-range-controls">
      <label htmlFor={`${id}-min`}>Minimum
        <input id={`${id}-min`} type="range" min="0" max={limit} step={step} value={minimum}
          aria-label={`${title} minimum`} aria-valuetext={`${minimum} ${unit}`}
          onChange={event => onChange(Math.min(Number(event.target.value), maximum), maximum)} />
      </label>
      <label htmlFor={`${id}-max`}>Maximum
        <input id={`${id}-max`} type="range" min="0" max={limit} step={step} value={maximum}
          aria-label={`${title} maximum`} aria-valuetext={`${maximum} ${unit}`}
          onChange={event => onChange(minimum, Math.max(Number(event.target.value), minimum))} />
      </label>
    </div>
  </fieldset>
}
