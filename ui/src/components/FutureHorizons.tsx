/**
 * Future Horizons Tab Component with Futures Cone Visualization
 */

import { ChevronLeft, ChevronRight } from 'lucide-react';

interface Scenario {
  title: string;
  description: string;
  probability: 'Plausible' | 'Probable' | 'Possible' | 'Preferable' | 'Wildcard';
  timeframe: string;
  icon?: string;
}

interface FutureHorizonsProps {
  scenarios: Scenario[];
}

export function FutureHorizons({ scenarios }: FutureHorizonsProps) {
  // Group scenarios by probability
  const plausibleScenarios = scenarios.filter(s => s.probability === 'Plausible');
  const probableScenarios = scenarios.filter(s => s.probability === 'Probable');

  return (
    <div className="space-y-6">
      {/* Futures Cone Visualization */}
      <div className="bg-white border border-gray-200 rounded-xl p-8 relative">
        {/* Navigation arrows */}
        <button className="absolute left-4 top-1/2 transform -translate-y-1/2 w-8 h-8 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center">
          <ChevronLeft className="w-5 h-5 text-gray-700" />
        </button>
        <button className="absolute right-4 top-1/2 transform -translate-y-1/2 w-8 h-8 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center">
          <ChevronRight className="w-5 h-5 text-gray-700" />
        </button>

        {/* Futures Cone SVG */}
        <svg viewBox="0 0 800 400" className="w-full h-64">
          {/* Cone layers */}
          <path
            d="M 50 350 Q 200 200, 750 100 L 750 320 Q 200 380, 50 350 Z"
            fill="#FCD34D"
            opacity="0.3"
          />
          <path
            d="M 50 350 Q 200 220, 700 120 L 700 300 Q 200 370, 50 350 Z"
            fill="#FCD34D"
            opacity="0.4"
          />
          <path
            d="M 50 350 Q 200 240, 650 140 L 650 280 Q 200 360, 50 350 Z"
            fill="#FCD34D"
            opacity="0.5"
          />
          <path
            d="M 50 350 Q 200 260, 600 160 L 600 260 Q 200 350, 50 350 Z"
            fill="#FCD34D"
            opacity="0.6"
          />
          <path
            d="M 50 350 Q 200 280, 550 180 L 550 240 Q 200 340, 50 350 Z"
            fill="#FCD34D"
            opacity="0.7"
          />

          {/* Labels */}
          <text x="100" y="340" fill="#92400E" fontSize="14" fontWeight="600">Plausible</text>
          <text x="200" y="290" fill="#92400E" fontSize="14" fontWeight="600">Possible</text>
          <text x="300" y="240" fill="#92400E" fontSize="14" fontWeight="600">Probable</text>
          <text x="400" y="190" fill="#92400E" fontSize="14" fontWeight="600">Preferable</text>
          <text x="520" y="140" fill="#92400E" fontSize="14" fontWeight="600">Wildcard</text>

          {/* Example scenario card on cone */}
          <foreignObject x="250" y="220" width="200" height="80">
            <div className="bg-white rounded-lg shadow-lg p-3 border border-gray-200">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold">Legal Clarification</span>
                <span className="text-xs text-gray-500">📝</span>
              </div>
              <p className="text-xs text-gray-700">Courts gradually clarify existing copyright law for AI content</p>
            </div>
          </foreignObject>
        </svg>

        {/* Timeline */}
        <div className="flex justify-between items-center mt-4 px-4">
          <div className="flex items-center gap-8">
            <div className="text-center">
              <div className="w-3 h-3 bg-gray-400 rounded-full mx-auto mb-1"></div>
              <div className="text-xs text-gray-700">2025</div>
              <div className="text-xs text-gray-600">Present</div>
            </div>
            <div className="text-center">
              <div className="w-3 h-3 bg-gray-400 rounded-full mx-auto mb-1"></div>
              <div className="text-xs text-gray-700">2026</div>
              <div className="text-xs text-gray-600">Short-term</div>
            </div>
            <div className="text-center">
              <div className="w-3 h-3 bg-gray-400 rounded-full mx-auto mb-1"></div>
              <div className="text-xs text-gray-700">2027</div>
              <div className="text-xs text-gray-600">Mid-term</div>
            </div>
            <div className="text-center">
              <div className="w-3 h-3 bg-gray-400 rounded-full mx-auto mb-1"></div>
              <div className="text-xs text-gray-700">2028</div>
              <div className="text-xs text-gray-600">Long-term</div>
            </div>
            <div className="text-center">
              <div className="w-3 h-3 bg-gray-400 rounded-full mx-auto mb-1"></div>
              <div className="text-xs text-gray-700">2029</div>
              <div className="text-xs text-gray-600">Horizon</div>
            </div>
          </div>
        </div>
      </div>

      {/* Scenario Cards Grid */}
      <div className="grid grid-cols-2 gap-6">
        {/* Plausible Scenarios */}
        <div>
          <div className="bg-yellow-100 text-yellow-900 px-4 py-2 rounded-t-xl font-semibold text-sm">
            Plausible - Reasonably possible
          </div>
          <div className="bg-gray-50 border border-gray-200 rounded-b-xl p-4 space-y-3">
            {plausibleScenarios.length > 0 ? plausibleScenarios.map((scenario, idx) => (
              <ScenarioCard key={idx} scenario={scenario} />
            )) : (
              <div className="space-y-3">
                <ScenarioCard scenario={{
                  title: 'Legal Clarification',
                  description: 'Courts gradually clarify existing copyright law for AI content',
                  probability: 'Plausible',
                  timeframe: '2025-2027',
                  icon: '📝'
                }} />
                <ScenarioCard scenario={{
                  title: 'Legal Clarification',
                  description: 'Courts gradually clarify existing copyright law for AI content',
                  probability: 'Plausible',
                  timeframe: '2025-2027',
                  icon: '📝'
                }} />
                <ScenarioCard scenario={{
                  title: 'Legal Clarification',
                  description: 'Courts gradually clarify existing copyright law for AI content',
                  probability: 'Plausible',
                  timeframe: '2025-2027',
                  icon: '📝'
                }} />
              </div>
            )}
            {/* Timeline for plausible scenarios */}
            <div className="mt-4 pt-4 border-t border-gray-300">
              <div className="flex justify-between text-xs text-gray-700 mb-2">
                <span>2025</span>
                <span>2026</span>
                <span>2027</span>
                <span>2028</span>
                <span>2029</span>
              </div>
              <div className="relative h-2">
                <div className="absolute inset-0 bg-gray-200 rounded-full"></div>
                <div className="absolute left-0 h-2 bg-yellow-400 rounded-full" style={{width: '40%'}}></div>
              </div>
            </div>
          </div>
        </div>

        {/* Probable Scenarios */}
        <div>
          <div className="bg-blue-500 text-white px-4 py-2 rounded-t-xl font-semibold text-sm">
            Probable - Most likely outcomes
          </div>
          <div className="bg-gray-50 border border-gray-200 rounded-b-xl p-4 space-y-3">
            {probableScenarios.length > 0 ? probableScenarios.map((scenario, idx) => (
              <ScenarioCard key={idx} scenario={scenario} />
            )) : (
              <div className="space-y-3">
                <ScenarioCard scenario={{
                  title: 'Legal Clarification',
                  description: 'Courts gradually clarify existing copyright law for AI content',
                  probability: 'Probable',
                  timeframe: '2025-2027',
                  icon: '📝'
                }} />
                <ScenarioCard scenario={{
                  title: 'Legal Clarification',
                  description: 'Courts gradually clarify existing copyright law for AI content',
                  probability: 'Probable',
                  timeframe: '2025-2027',
                  icon: '📝'
                }} />
                <ScenarioCard scenario={{
                  title: 'Legal Clarification',
                  description: 'Courts gradually clarify existing copyright law for AI content',
                  probability: 'Probable',
                  timeframe: '2025-2027',
                  icon: '📝'
                }} />
              </div>
            )}
            {/* Timeline for probable scenarios */}
            <div className="mt-4 pt-4 border-t border-gray-300">
              <div className="flex justify-between text-xs text-gray-700 mb-2">
                <span>Present</span>
                <span>2026</span>
                <span>2027</span>
                <span>2028</span>
                <span>2029</span>
              </div>
              <div className="relative h-2">
                <div className="absolute inset-0 bg-gray-200 rounded-full"></div>
                <div className="absolute left-0 h-2 bg-blue-500 rounded-full" style={{width: '60%'}}></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Icons Legend */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <h3 className="font-semibold mb-4">Icons Legend</h3>
        <div className="grid grid-cols-2 gap-x-8 gap-y-3">
          <div className="flex items-center gap-2">
            <span className="text-gray-500">😐</span>
            <span className="text-sm text-gray-800">Mixed/Neutral</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-yellow-500">😊👍</span>
            <span className="text-sm text-gray-800">Mixed/Positive</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-orange-500">⚠️</span>
            <span className="text-sm text-gray-800">Critical/Neutral</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-green-500">✅</span>
            <span className="text-sm text-gray-800">Positive</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-red-500">❌</span>
            <span className="text-sm text-gray-800">Negative/Disruptive</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-blue-500">📈</span>
            <span className="text-sm text-gray-800">Evolution/Trend</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-purple-500">📝</span>
            <span className="text-sm text-gray-800">Trend/Evolution</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-gray-600">⚠️</span>
            <span className="text-sm text-gray-800">Disruption/Warning</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-pink-500">🚀</span>
            <span className="text-sm text-gray-800">Breakthrough</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-amber-500">⚡</span>
            <span className="text-sm text-gray-800">Warning/Disruption</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: Scenario }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="font-semibold text-sm">{scenario.title}</h4>
            {scenario.icon && <span className="text-sm">{scenario.icon}</span>}
          </div>
          <p className="text-xs text-gray-700">{scenario.description}</p>
        </div>
        <button className="text-gray-500 hover:text-gray-700">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
