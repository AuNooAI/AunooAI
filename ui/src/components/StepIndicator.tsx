/**
 * StepIndicator Component - Multi-step progress indicator
 */

interface StepIndicatorProps {
  currentStep: number;
  totalSteps: number;
  stepLabels?: string[];
}

export function StepIndicator({ currentStep, totalSteps, stepLabels = [] }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-between mb-8">
      {Array.from({ length: totalSteps }, (_, index) => {
        const stepNumber = index + 1;
        const isActive = stepNumber === currentStep;
        const isCompleted = stepNumber < currentStep;
        const isLast = stepNumber === totalSteps;

        return (
          <div key={stepNumber} className="flex items-center flex-1">
            {/* Step Circle */}
            <div className="flex flex-col items-center">
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold transition-colors ${
                  isActive
                    ? 'bg-pink-500 text-white'
                    : isCompleted
                    ? 'bg-green-500 text-white'
                    : 'bg-gray-200 text-gray-600'
                }`}
              >
                {isCompleted ? (
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  stepNumber
                )}
              </div>
              {stepLabels[index] && (
                <span className={`mt-2 text-xs ${isActive ? 'font-semibold text-gray-900' : 'text-gray-500'}`}>
                  {stepLabels[index]}
                </span>
              )}
            </div>

            {/* Connecting Line */}
            {!isLast && (
              <div
                className={`flex-1 h-0.5 mx-2 transition-colors ${
                  isCompleted ? 'bg-green-500' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
