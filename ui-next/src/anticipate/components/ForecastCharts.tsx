import type { AssessmentSnapshot } from '@monolith-types/forecastAssessment';
import { Text } from '@aunoo/ui';
import './forecastCharts.css';

/*
 * The Forecast Tracker's snapshot grid, as the old page's SnapshotHistoryPanel: one row per scenario,
 * one cell per paired re-assessment, coloured by its status, so a scenario drifting from cooling to
 * strengthening shows as a row turning green. The design template had only a counts table.
 */

const STATUS: Record<string, { cls: string; label: string }> = {
  'Above baseline': { cls: 'up', label: 'Strengthening' },
  'At baseline': { cls: 'flat', label: 'Stable' },
  'Below baseline': { cls: 'down', label: 'Cooling' },
};

const day = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });

export function SnapshotGrid({ snapshots, titles }: { snapshots: AssessmentSnapshot[]; titles?: Record<number, string> }) {
  const idxs = [...new Set(snapshots.flatMap((s) => s.per_scenario.map((p) => p.scenario_idx)))].sort((a, b) => a - b);
  if (!idxs.length) return null;
  return (
    <div className="fc-grid">
      <div className="fc-grid__scroll" tabIndex={0} role="region" aria-label="Scenario status at each re-assessment">
        <table className="fc-grid__table">
          <caption className="visually-hidden">Status of each scenario at each paired re-assessment, oldest first</caption>
          <thead>
            <tr>
              <th scope="col" className="fc-grid__name">Scenario</th>
              {snapshots.map((s, i) => (
                <th key={s.assessment_id} scope="col" className="fc-grid__date">
                  {i === 0 || i === snapshots.length - 1 ? day(s.assessed_at) : <span className="visually-hidden">{day(s.assessed_at)}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {idxs.map((idx) => (
              <tr key={idx}>
                <th scope="row" className="fc-grid__name">{titles?.[idx] ?? `Scenario ${idx}`}</th>
                {snapshots.map((s) => {
                  const c = s.per_scenario.find((p) => p.scenario_idx === idx);
                  const st = c ? STATUS[c.label ?? ''] : undefined;
                  const text = c ? `${day(s.assessed_at)}: ${st?.label ?? c.label ?? 'unknown'}, net ${((c.net_rate ?? 0) * 100).toFixed(2)}%` : `${day(s.assessed_at)}: not assessed`;
                  return (
                    <td key={s.assessment_id}>
                      <span className={`fc-grid__cell fc-grid__cell--${st?.cls ?? 'none'}`} title={text}>
                        <span className="visually-hidden">{text}</span>
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Text variant="caption">
        <span className="fc-key fc-grid__cell--up" /> Strengthening <span className="fc-key fc-grid__cell--flat" /> Stable{' '}
        <span className="fc-key fc-grid__cell--down" /> Cooling <span className="fc-key fc-grid__cell--none" /> Not assessed. A row turning green over time is a
        trajectory materialising.
      </Text>
    </div>
  );
}
