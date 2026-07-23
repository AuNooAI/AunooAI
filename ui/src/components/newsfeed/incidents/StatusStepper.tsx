/**
 * Incident lifecycle as a clickable progress control. Statuses are not
 * strictly linear (a resolved case can reopen), so every step stays
 * clickable — the fill just visualizes how far along the case is.
 */
export const INCIDENT_STATUSES = ['open', 'investigating', 'contained', 'resolved', 'closed'] as const;

const STEP_HELP: Record<string, string> = {
  open: 'New case — evidence gathering has not concluded',
  investigating: 'Actively being worked',
  contained: 'Impact stopped spreading; monitoring continues',
  resolved: 'Dealt with — kept for the record',
  closed: 'Archived',
};

export function StatusStepper({ status, onChange, disabled }: {
  status: string;
  onChange: (status: string) => void;
  disabled?: boolean;
}) {
  const idx = INCIDENT_STATUSES.indexOf(status as typeof INCIDENT_STATUSES[number]);
  return (
    <div className="flex items-center" role="group" aria-label="Incident status">
      {INCIDENT_STATUSES.map((st, i) => {
        const active = st === status;
        const passed = idx >= 0 && i < idx;
        return (
          <div key={st} className="flex items-center">
            {i > 0 && <div className={`w-4 sm:w-6 h-0.5 ${passed || active ? 'bg-blue-400' : 'bg-gray-200 dark:bg-gray-600'}`} />}
            <button onClick={() => !disabled && !active && onChange(st)} disabled={disabled}
              title={`${STEP_HELP[st]}${active ? '' : ' — click to set'}`}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                active ? 'bg-blue-600 text-white border-blue-600 font-medium'
                : passed ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-800'
                : 'bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-300 dark:border-gray-600 hover:border-blue-300'}`}>
              {st}
            </button>
          </div>
        );
      })}
    </div>
  );
}
