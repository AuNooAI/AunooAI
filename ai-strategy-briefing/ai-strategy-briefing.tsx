"use client"

import { useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  AlertTriangle,
  TrendingUp,
  Brain,
  ChevronLeft,
  ChevronRight,
  Target,
  Shield,
  Lightbulb,
  Clock,
  BarChart3,
  Zap,
} from "lucide-react"

const swimlaneData = [
  {
    category: "Market Correction/Bubble",
    timeframe: "1-5 years (2025-2030)",
    color: "bg-red-500",
    description: "High investment, risk of short-term correction, followed by stabilization",
    milestones: [
      { year: "2025", event: "Bubble Risk Peak", position: 20 },
      { year: "2027", event: "Market Correction", position: 40 },
      { year: "2030", event: "Stabilization", position: 60 },
    ],
  },
  {
    category: "Infrastructure Scaling",
    timeframe: "5-10 years (to 2030+)",
    color: "bg-orange-500",
    description: "Data center build-out, energy/resource bottlenecks, regional competition",
    milestones: [
      { year: "2025", event: "Capacity Constraints", position: 20 },
      { year: "2028", event: "Major Buildout", position: 50 },
      { year: "2032", event: "Infrastructure Maturity", position: 80 },
    ],
  },
  {
    category: "AI Regulation/Ethics",
    timeframe: "3-10 years",
    color: "bg-blue-500",
    description: "Gradual regulatory catch-up, focus on trust and safety",
    milestones: [
      { year: "2026", event: "Initial Frameworks", position: 30 },
      { year: "2029", event: "Comprehensive Rules", position: 60 },
      { year: "2033", event: "Global Standards", position: 85 },
    ],
  },
  {
    category: "Productivity, ROI",
    timeframe: "3-10 years (mid 2030s)",
    color: "bg-green-500",
    description: "Gradual evolution, delayed financial returns, ongoing platform innovation",
    milestones: [
      { year: "2027", event: "Early Returns", position: 35 },
      { year: "2030", event: "Measurable ROI", position: 65 },
      { year: "2035", event: "Full Productivity", position: 90 },
    ],
  },
  {
    category: "Job Market Disruption",
    timeframe: "10-25 years (to 2050)",
    color: "bg-purple-500",
    description: "Long-term adaptation, re-skilling, sectoral transformation",
    milestones: [
      { year: "2030", event: "Initial Displacement", position: 25 },
      { year: "2040", event: "Major Transition", position: 60 },
      { year: "2050", event: "New Equilibrium", position: 95 },
    ],
  },
  {
    category: "AGI/Superintelligence",
    timeframe: "10-30+ years",
    color: "bg-indigo-500",
    description: "Serious skepticism about 2025 timelines, more likely post-2040",
    milestones: [
      { year: "2035", event: "Advanced AI", position: 40 },
      { year: "2045", event: "AGI Potential", position: 75 },
      { year: "2055", event: "Superintelligence?", position: 100 },
    ],
  },
]

const marketSignals = [
  { signal: "AI will evolve gradually", frequency: "High", impact: "Immediate/Mid/Long-term", level: "high" },
  { signal: "AI will accelerate", frequency: "High", impact: "Immediate/Short-term", level: "high" },
  { signal: "AI is hype", frequency: "Moderate", impact: "Immediate/Long-term", level: "moderate" },
  { signal: "AI is a bubble", frequency: "Moderate", impact: "Immediate/Mid-term", level: "moderate" },
  { signal: "AI has plateaued", frequency: "Low", impact: "Immediate", level: "low" },
]

const risks = [
  {
    title: "Critical Risk: Market Correction (2025-2030)",
    description:
      "High investment levels create bubble risk. 98% of investors worried about power reliability for datacenters, yet 70% anticipate increased funding driven by AI demand.",
    type: "risk",
    icon: AlertTriangle,
  },
  {
    title: "Opportunity: Infrastructure Build-out",
    description:
      "Data center expansion creates competitive advantages for early movers who secure energy and infrastructure partnerships.",
    type: "opportunity",
    icon: Lightbulb,
  },
  {
    title: "Timeline Risk: AGI Overexpectation",
    description:
      "Ambitious timelines for achieving AGI may be overly optimistic due to diminishing returns and operational challenges.",
    type: "risk",
    icon: Clock,
  },
  {
    title: "Opportunity: Gradual Adoption Advantage",
    description:
      "Companies focusing on sustainable, gradual AI integration may outperform those chasing unrealistic AGI timelines.",
    type: "opportunity",
    icon: Target,
  },
]

const actionPlans = [
  {
    period: "NEAR-TERM (2025-2027)",
    icon: Target,
    actions: [
      "Focus on sustainable AI investments",
      "Prepare for market volatility",
      "Secure infrastructure partnerships",
      "Avoid AGI speculation",
    ],
    color: "from-red-500 to-orange-500",
  },
  {
    period: "MID-TERM (2027-2032)",
    icon: TrendingUp,
    actions: [
      "Plan for gradual productivity gains",
      "Anticipate regulatory changes",
      "Build energy-efficient operations",
      "Start workforce adaptation",
    ],
    color: "from-orange-500 to-yellow-500",
  },
  {
    period: "LONG-TERM (2032+)",
    icon: Brain,
    actions: [
      "Expect delayed but significant ROI",
      "Prepare for sectoral transformation",
      "Invest in continuous re-skilling",
      "Monitor AGI developments",
    ],
    color: "from-blue-500 to-purple-500",
  },
]

const consensusData = [
  {
    domain: "AGI & Superintelligence",
    consensusStart: 2040,
    consensusEnd: 2055,
    consensusConfidence: 78,
    optimisticOutlier: { year: 2027, label: "Tech leaders claim AGI by 2027", confidence: 15 },
    pessimisticOutlier: { year: 2070, label: "Fundamental barriers remain", confidence: 22 },
    keyInsight: "Most credible forecasts reject 2025-2030 AGI claims",
    color: "from-purple-500 to-indigo-600",
    icon: Brain,
  },
  {
    domain: "AI Safety & Security",
    consensusStart: 2025,
    consensusEnd: 2035,
    consensusConfidence: 85,
    optimisticOutlier: { year: 2024, label: "Safety protocols sufficient", confidence: 25 },
    pessimisticOutlier: { year: 2040, label: "Autonomous weapons proliferate", confidence: 35 },
    keyInsight: "Strong consensus on gradual safety framework development",
    color: "from-red-500 to-orange-500",
    icon: Shield,
  },
  {
    domain: "Economic Productivity",
    consensusStart: 2027,
    consensusEnd: 2035,
    consensusConfidence: 72,
    optimisticOutlier: { year: 2025, label: "Immediate 20% productivity gains", confidence: 18 },
    pessimisticOutlier: { year: 2045, label: "Minimal economic impact", confidence: 28 },
    keyInsight: "Delayed but significant ROI expected mid-2030s",
    color: "from-green-500 to-emerald-600",
    icon: TrendingUp,
  },
  {
    domain: "Workforce Disruption",
    consensusStart: 2030,
    consensusEnd: 2050,
    consensusConfidence: 68,
    optimisticOutlier: { year: 2026, label: "Mass unemployment begins", confidence: 32 },
    pessimisticOutlier: { year: 2060, label: "Minimal job displacement", confidence: 20 },
    keyInsight: "Gradual transition with significant adaptation time",
    color: "from-blue-500 to-cyan-600",
    icon: BarChart3,
  },
  {
    domain: "Regulatory Framework",
    consensusStart: 2026,
    consensusEnd: 2032,
    consensusConfidence: 81,
    optimisticOutlier: { year: 2024, label: "Global coordination achieved", confidence: 12 },
    pessimisticOutlier: { year: 2040, label: "Regulatory fragmentation", confidence: 38 },
    keyInsight: "Moderate consensus on gradual regulatory catch-up",
    color: "from-amber-500 to-yellow-600",
    icon: AlertTriangle,
  },
  {
    domain: "Infrastructure Scaling",
    consensusStart: 2025,
    consensusEnd: 2032,
    consensusConfidence: 76,
    optimisticOutlier: { year: 2024, label: "Energy bottlenecks solved", confidence: 22 },
    pessimisticOutlier: { year: 2038, label: "Persistent capacity limits", confidence: 31 },
    keyInsight: "Infrastructure buildout critical path identified",
    color: "from-orange-500 to-red-500",
    icon: Zap,
  },
]

const futuresScenarios = [
  {
    category: "Probable",
    color: "bg-blue-600",
    position: "left-[3%] top-[35%]",
    scenarios: [
      {
        title: "Legal Clarification",
        description: "Courts gradually clarify existing copyright law for AI content",
        sentiment: "⚖️",
        signal: "📈",
        tooltip: "Most likely outcome based on current trends",
      },
      {
        title: "Licensing Frameworks",
        description: "Standardized licensing models for training data become common",
        sentiment: "⚖️",
        signal: "📈",
        tooltip: "Industry-led standardization efforts",
      },
      {
        title: "Attribution Tools",
        description: "Widespread adoption of watermarking and provenance tracking",
        sentiment: "⚖️",
        signal: "📈",
        tooltip: "Technical solutions for attribution",
      },
    ],
  },
  {
    category: "Plausible",
    color: "bg-purple-600",
    position: "left-[24%] top-[25%]",
    scenarios: [
      {
        title: "Global Fragmentation",
        description: "Divergent regulations between US, EU, China create fractured landscape",
        sentiment: "⚠️",
        signal: "🔄",
        tooltip: "Regulatory divergence across regions",
      },
      {
        title: "AI as Legal Author",
        description: "Some jurisdictions recognize AI systems as legal authors",
        sentiment: "⚠️",
        signal: "🔄",
        tooltip: "Legal recognition of AI authorship",
      },
      {
        title: "Litigation Explosion",
        description: "Surge in lawsuits over data scraping and output ownership",
        sentiment: "⚠️",
        signal: "🔄",
        tooltip: "Legal battles intensify",
      },
    ],
  },
  {
    category: "Possible",
    color: "bg-pink-600",
    position: "left-[45%] top-[15%]",
    scenarios: [
      {
        title: "New IP Categories",
        description: 'Introduction of "sui generis AI rights" with limited protection',
        sentiment: "😐",
        signal: "📊",
        tooltip: "Novel legal frameworks emerge",
      },
      {
        title: "Automated Enforcement",
        description: "AI-driven copyright enforcement systems become ubiquitous",
        sentiment: "😐",
        signal: "📊",
        tooltip: "AI-powered copyright detection",
      },
      {
        title: "Creative Commons AI",
        description: "Global open-source data licensing movements emerge",
        sentiment: "😐",
        signal: "📊",
        tooltip: "Open data movements gain traction",
      },
    ],
  },
  {
    category: "Preferable",
    color: "bg-green-600",
    position: "right-[20%] top-[25%]",
    scenarios: [
      {
        title: "Global Standards",
        description: "International agreement balancing all stakeholder interests",
        sentiment: "✅",
        signal: "🚀",
        tooltip: "International cooperation succeeds",
      },
      {
        title: "Transparent Data Use",
        description: "Mandatory disclosure of training datasets to rights holders",
        sentiment: "✅",
        signal: "🚀",
        tooltip: "Full transparency in AI training",
      },
      {
        title: "Fair Compensation",
        description: "Revenue-sharing schemes for creators whose works train AI",
        sentiment: "✅",
        signal: "🚀",
        tooltip: "Creators benefit from AI use",
      },
    ],
  },
  {
    category: "Wildcard",
    color: "bg-red-600",
    position: "right-[20%] bottom-[30%]",
    scenarios: [
      {
        title: "Copyright Collapse",
        description: "Legal systems fail, widespread disregard for IP rights",
        sentiment: "❌",
        signal: "⚡",
        tooltip: "Complete system breakdown",
      },
      {
        title: "AI Content Flood",
        description: "AI-generated content overwhelms traditional IP frameworks",
        sentiment: "❌",
        signal: "⚡",
        tooltip: "Content oversaturation crisis",
      },
      {
        title: "Mass Opt-Out",
        description: "Coordinated creator boycotts force AI data sourcing changes",
        sentiment: "❌",
        signal: "⚡",
        tooltip: "Creator resistance movement",
      },
    ],
  },
]

const ConsensusAnalysis = () => {
  const [selectedDomain, setSelectedDomain] = useState<number | null>(null)

  return (
    <div className="space-y-8">
      <div className="text-center space-y-4">
        <h2 className="text-3xl font-bold text-gray-800">Evidence-Based Consensus vs. Outlier Forecasts</h2>
        <p className="text-lg text-gray-600">Synthesis of 300+ Research Articles & Industry Analysis (2024-2035+)</p>
      </div>

      {/* Interactive Domain Analysis */}
      <div className="grid gap-4">
        {consensusData.map((domain, index) => {
          const Icon = domain.icon
          const isSelected = selectedDomain === index

          return (
            <Card
              key={index}
              className={`cursor-pointer transition-all duration-300 ${
                isSelected ? "ring-2 ring-blue-500 shadow-lg" : "hover:shadow-md"
              }`}
              onClick={() => setSelectedDomain(isSelected ? null : index)}
            >
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg bg-gradient-to-r ${domain.color}`}>
                      <Icon className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <h3 className="font-bold text-lg text-gray-800">{domain.domain}</h3>
                      <p className="text-sm text-gray-600">{domain.keyInsight}</p>
                    </div>
                  </div>
                  <Badge variant="outline" className="text-blue-600 border-blue-600">
                    {domain.consensusConfidence}% Consensus
                  </Badge>
                </div>

                {/* Timeline Visualization */}
                <div className="relative">
                  <div className="flex items-center justify-between text-xs text-gray-500 mb-2">
                    <span>2024</span>
                    <span>2030</span>
                    <span>2040</span>
                    <span>2050+</span>
                  </div>

                  <div className="relative h-12 bg-gray-100 rounded-lg overflow-hidden">
                    {/* Consensus Band */}
                    <div
                      className={`absolute top-2 h-8 bg-gradient-to-r ${domain.color} opacity-60 rounded`}
                      style={{
                        left: `${((domain.consensusStart - 2024) / (2055 - 2024)) * 100}%`,
                        width: `${((domain.consensusEnd - domain.consensusStart) / (2055 - 2024)) * 100}%`,
                      }}
                    />

                    {/* Consensus Label */}
                    <div
                      className="absolute top-1/2 transform -translate-y-1/2 text-xs font-bold text-white"
                      style={{
                        left: `${(((domain.consensusStart + domain.consensusEnd) / 2 - 2024) / (2055 - 2024)) * 100}%`,
                        transform: "translateX(-50%) translateY(-50%)",
                      }}
                    >
                      CONSENSUS
                    </div>

                    {/* Optimistic Outlier */}
                    <div
                      className="absolute top-0 w-3 h-3 bg-green-500 rounded-full border-2 border-white shadow-md"
                      style={{
                        left: `${((domain.optimisticOutlier.year - 2024) / (2055 - 2024)) * 100}%`,
                        transform: "translateX(-50%)",
                      }}
                      title={domain.optimisticOutlier.label}
                    />

                    {/* Pessimistic Outlier */}
                    <div
                      className="absolute bottom-0 w-3 h-3 bg-red-500 rounded-full border-2 border-white shadow-md"
                      style={{
                        left: `${((domain.pessimisticOutlier.year - 2024) / (2055 - 2024)) * 100}%`,
                        transform: "translateX(-50%)",
                      }}
                      title={domain.pessimisticOutlier.label}
                    />
                  </div>
                </div>

                {/* Expanded Details */}
                {isSelected && (
                  <div className="mt-6 pt-6 border-t border-gray-200 space-y-4">
                    <div className="grid md:grid-cols-2 gap-4">
                      <div className="space-y-3">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 bg-green-500 rounded-full" />
                          <span className="font-semibold text-sm">
                            Optimistic Outlier ({domain.optimisticOutlier.year})
                          </span>
                        </div>
                        <p className="text-sm text-gray-700 ml-5">{domain.optimisticOutlier.label}</p>
                        <div className="ml-5">
                          <Badge variant="secondary" className="text-xs">
                            {domain.optimisticOutlier.confidence}% of sources
                          </Badge>
                        </div>
                      </div>

                      <div className="space-y-3">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 bg-red-500 rounded-full" />
                          <span className="font-semibold text-sm">
                            Pessimistic Outlier ({domain.pessimisticOutlier.year})
                          </span>
                        </div>
                        <p className="text-sm text-gray-700 ml-5">{domain.pessimisticOutlier.label}</p>
                        <div className="ml-5">
                          <Badge variant="secondary" className="text-xs">
                            {domain.pessimisticOutlier.confidence}% of sources
                          </Badge>
                        </div>
                      </div>
                    </div>

                    <div className="bg-blue-50 p-4 rounded-lg">
                      <h4 className="font-semibold text-sm text-blue-800 mb-2">Strategic Implication</h4>
                      <p className="text-sm text-blue-700">{domain.keyInsight}</p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Key Insights Summary */}
      <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
        <CardContent className="p-6">
          <h3 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-600" />
            Key Insights from Evidence Synthesis
          </h3>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0" />
                <p className="text-sm text-gray-700">
                  <strong>Consensus bands</strong> show agreed timing and sentiment from 300+ research sources
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 bg-green-500 rounded-full mt-2 flex-shrink-0" />
                <p className="text-sm text-gray-700">
                  <strong>Optimistic outliers</strong> represent credible dissenting views and potential black swan
                  events
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 bg-red-500 rounded-full mt-2 flex-shrink-0" />
                <p className="text-sm text-gray-700">
                  <strong>Pessimistic outliers</strong> highlight potential barriers and delayed timelines
                </p>
              </div>
            </div>
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 bg-purple-500 rounded-full mt-2 flex-shrink-0" />
                <p className="text-sm text-gray-700">
                  <strong>Strategic planning</strong> should prepare for both consensus scenarios and outlier
                  possibilities
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 bg-orange-500 rounded-full mt-2 flex-shrink-0" />
                <p className="text-sm text-gray-700">
                  <strong>Most credible forecasts</strong> reject 2025-2030 AGI claims; focus on gradual evolution
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="text-xs text-gray-500 bg-gray-50 p-4 rounded-lg">
        <strong>Methodology:</strong> Structured synthesis, thematic aggregation, milestone detection, outlier
        identification from peer-reviewed research, industry reports, and expert surveys (2024-2025)
      </div>
    </div>
  )
}

const FuturesCone = () => (
  <div className="relative">
    <div className="relative h-[1080px] overflow-visible bg-gradient-to-br from-slate-900 to-blue-900 rounded-2xl p-8">
      {/* Cone background - more visible */}
      <div className="absolute inset-0 rounded-2xl overflow-hidden">
        <div
          className="absolute inset-0 opacity-20"
          style={{
            background: `conic-gradient(from 180deg at 0% 50%, 
              #3182ce 0deg,
              #805ad5 72deg,
              #d53f8c 144deg,
              #f56565 216deg,
              #ed8936 288deg,
              #3182ce 360deg)`,
            clipPath: "polygon(0% 50%, 100% 0%, 100% 100%)",
          }}
        />

        {/* Additional cone outline */}
        <div
          className="absolute inset-0 border-2 border-white/20"
          style={{
            clipPath: "polygon(0% 50%, 100% 0%, 100% 100%)",
          }}
        />
      </div>

      {/* Grid overlay - more visible */}
      <div
        className="absolute inset-0 opacity-10 rounded-2xl"
        style={{
          backgroundImage:
            "linear-gradient(90deg, rgba(255,255,255,0.3) 1px, transparent 1px), linear-gradient(0deg, rgba(255,255,255,0.3) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
          clipPath: "polygon(0% 50%, 100% 0%, 100% 100%)",
        }}
      />

      {/* Cone expansion lines */}
      <div className="absolute inset-0">
        <div className="absolute top-0 left-0 w-full h-0.5 bg-white/30 origin-left transform rotate-[26.57deg]" />
        <div className="absolute bottom-0 left-0 w-full h-0.5 bg-white/30 origin-left transform -rotate-[26.57deg]" />
      </div>

      {/* Timeline axis */}
      <div className="absolute bottom-20 left-8 right-8 h-0.5 bg-gradient-to-r from-gray-400 to-white" />

      {/* Time labels */}
      <div className="absolute bottom-12 left-8 right-8 flex justify-between">
        {["Present", "2025-2027", "2028-2032", "2033+"].map((label) => (
          <Badge key={label} variant="secondary" className="bg-white/20 text-white border-white/30">
            {label}
          </Badge>
        ))}
      </div>

      {/* Scenario groups - repositioned for better cone visibility */}
      <div className="absolute left-4 top-1/2 transform -translate-y-1/2 w-52">
        <Badge className="bg-blue-600 text-white mb-4 block text-center">Probable</Badge>
        <div className="space-y-3">
          {futuresScenarios[0].scenarios.map((scenario, scenarioIndex) => (
            <Card
              key={scenarioIndex}
              className="bg-white/10 backdrop-blur-md border-blue-600/30 hover:bg-white/15 transition-all duration-300 hover:scale-105 cursor-pointer"
              title={scenario.tooltip}
            >
              <CardContent className="p-2">
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-bold text-xs text-white">{scenario.title}</h4>
                  <div className="flex gap-1 text-xs">
                    <span title="Sentiment">{scenario.sentiment}</span>
                    <span title="Signal">{scenario.signal}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-300 leading-relaxed">{scenario.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div className="absolute left-1/4 top-[40%] w-52">
        <Badge className="bg-purple-600 text-white mb-4 block text-center">Plausible</Badge>
        <div className="space-y-3">
          {futuresScenarios[1].scenarios.map((scenario, scenarioIndex) => (
            <Card
              key={scenarioIndex}
              className="bg-white/10 backdrop-blur-md border-purple-600/30 hover:bg-white/15 transition-all duration-300 hover:scale-105 cursor-pointer"
              title={scenario.tooltip}
            >
              <CardContent className="p-2">
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-bold text-xs text-white">{scenario.title}</h4>
                  <div className="flex gap-1 text-xs">
                    <span title="Sentiment">{scenario.sentiment}</span>
                    <span title="Signal">{scenario.signal}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-300 leading-relaxed">{scenario.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div className="absolute left-1/2 top-[30%] w-52">
        <Badge className="bg-pink-600 text-white mb-4 block text-center">Possible</Badge>
        <div className="space-y-3">
          {futuresScenarios[2].scenarios.map((scenario, scenarioIndex) => (
            <Card
              key={scenarioIndex}
              className="bg-white/10 backdrop-blur-md border-pink-600/30 hover:bg-white/15 transition-all duration-300 hover:scale-105 cursor-pointer"
              title={scenario.tooltip}
            >
              <CardContent className="p-2">
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-bold text-xs text-white">{scenario.title}</h4>
                  <div className="flex gap-1 text-xs">
                    <span title="Sentiment">{scenario.sentiment}</span>
                    <span title="Signal">{scenario.signal}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-300 leading-relaxed">{scenario.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div className="absolute right-20 top-[25%] w-52">
        <Badge className="bg-green-600 text-white mb-4 block text-center">Preferable</Badge>
        <div className="space-y-3">
          {futuresScenarios[3].scenarios.map((scenario, scenarioIndex) => (
            <Card
              key={scenarioIndex}
              className="bg-white/10 backdrop-blur-md border-green-600/30 hover:bg-white/15 transition-all duration-300 hover:scale-105 cursor-pointer"
              title={scenario.tooltip}
            >
              <CardContent className="p-2">
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-bold text-xs text-white">{scenario.title}</h4>
                  <div className="flex gap-1 text-xs">
                    <span title="Sentiment">{scenario.sentiment}</span>
                    <span title="Signal">{scenario.signal}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-300 leading-relaxed">{scenario.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div className="absolute right-20 bottom-[30%] w-52">
        <Badge className="bg-red-600 text-white mb-4 block text-center">Wildcard</Badge>
        <div className="space-y-3">
          {futuresScenarios[4].scenarios.map((scenario, scenarioIndex) => (
            <Card
              key={scenarioIndex}
              className="bg-white/10 backdrop-blur-md border-red-600/30 hover:bg-white/15 transition-all duration-300 hover:scale-105 cursor-pointer"
              title={scenario.tooltip}
            >
              <CardContent className="p-2">
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-bold text-xs text-white">{scenario.title}</h4>
                  <div className="flex gap-1 text-xs">
                    <span title="Sentiment">{scenario.sentiment}</span>
                    <span title="Signal">{scenario.signal}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-300 leading-relaxed">{scenario.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Cone center point indicator */}
      <div className="absolute left-0 top-1/2 transform -translate-y-1/2">
        <div className="w-4 h-4 bg-white rounded-full border-2 border-blue-500 shadow-lg"></div>
        <div className="absolute -bottom-6 left-1/2 transform -translate-x-1/2 text-white text-xs font-bold">NOW</div>
      </div>
    </div>

    {/* Legend */}
    <div className="mt-8 grid md:grid-cols-2 gap-6">
      <Card>
        <CardContent className="p-6">
          <h4 className="font-bold mb-4">Scenario Categories</h4>
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <div className="w-4 h-1 bg-blue-600 rounded" />
              <span className="text-sm">Probable - Most likely outcomes</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-4 h-1 bg-purple-600 rounded" />
              <span className="text-sm">Plausible - Reasonably possible</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-4 h-1 bg-pink-600 rounded" />
              <span className="text-sm">Possible - Less likely but feasible</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-4 h-1 bg-green-600 rounded" />
              <span className="text-sm">Preferable - Desired outcomes</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-4 h-1 bg-red-600 rounded" />
              <span className="text-sm">Wildcard - Disruptive/unexpected</span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          <h4 className="font-bold mb-4">Icons Legend</h4>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="flex items-center gap-2">
              <span>⚖️</span> Mixed/Neutral
            </div>
            <div className="flex items-center gap-2">
              <span>😐</span> Mixed/Positive
            </div>
            <div className="flex items-center gap-2">
              <span>⚠️</span> Critical/Neutral
            </div>
            <div className="flex items-center gap-2">
              <span>✅</span> Positive
            </div>
            <div className="flex items-center gap-2">
              <span>❌</span> Negative/Disruptive
            </div>
            <div className="flex items-center gap-2">
              <span>📈</span> Evolution/Trend
            </div>
            <div className="flex items-center gap-2">
              <span>📊</span> Trend/Evolution
            </div>
            <div className="flex items-center gap-2">
              <span>🔄</span> Disruption/Warning
            </div>
            <div className="flex items-center gap-2">
              <span>🚀</span> Breakthrough
            </div>
            <div className="flex items-center gap-2">
              <span>⚡</span> Warning/Disruption
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
)

export default function AIStrategyBriefing() {
  const [currentSlide, setCurrentSlide] = useState(0)
  const [selectedMilestone, setSelectedMilestone] = useState<number | null>(null)

  const nextSlide = () => setCurrentSlide((prev) => (prev + 1) % 5)
  const prevSlide = () => setCurrentSlide((prev) => (prev - 1 + 5) % 5)

  const EnhancedTimeline = () => (
    <div className="relative py-8">
      <div className="space-y-6">
        {/* Timeline header with years */}
        <div className="relative mx-8 mb-8">
          <div className="flex justify-between text-sm font-semibold text-gray-600 mb-2">
            <span>2025</span>
            <span>2030</span>
            <span>2035</span>
            <span>2040</span>
            <span>2045</span>
            <span>2050+</span>
          </div>
          <div className="h-1 bg-gradient-to-r from-gray-300 to-gray-500 rounded-full"></div>
        </div>

        {/* Swimlanes */}
        {swimlaneData.map((lane, laneIndex) => (
          <div key={laneIndex} className="relative">
            <Card className="overflow-hidden hover:shadow-lg transition-shadow duration-300">
              <CardContent className="p-0">
                <div className="flex">
                  {/* Category Label */}
                  <div className={`${lane.color} text-white p-4 w-64 flex-shrink-0`}>
                    <h4 className="font-bold text-sm mb-1">{lane.category}</h4>
                    <p className="text-xs opacity-90 mb-2">{lane.timeframe}</p>
                    <p className="text-xs opacity-80 leading-tight">{lane.description}</p>
                  </div>

                  {/* Timeline Track */}
                  <div className="flex-1 relative p-4 bg-gray-50">
                    <div className="relative h-8">
                      {/* Background track */}
                      <div className="absolute top-1/2 left-0 right-0 h-2 bg-gray-200 rounded-full transform -translate-y-1/2"></div>

                      {/* Progress track */}
                      <div
                        className={`absolute top-1/2 left-0 h-2 ${lane.color} rounded-full transform -translate-y-1/2 opacity-30`}
                        style={{ width: `${Math.max(...lane.milestones.map((m) => m.position))}%` }}
                      ></div>

                      {/* Milestones */}
                      {lane.milestones.map((milestone, milestoneIndex) => (
                        <div
                          key={milestoneIndex}
                          className="absolute transform -translate-x-1/2 -translate-y-1/2 cursor-pointer group"
                          style={{ left: `${milestone.position}%`, top: "50%" }}
                        >
                          <div
                            className={`w-4 h-4 ${lane.color} rounded-full border-2 border-white shadow-md group-hover:scale-125 transition-transform duration-200`}
                          ></div>

                          {/* Milestone tooltip */}
                          <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                            <div className="bg-gray-800 text-white text-xs px-2 py-1 rounded whitespace-nowrap">
                              <div className="font-semibold">{milestone.year}</div>
                              <div>{milestone.event}</div>
                            </div>
                            <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-2 border-r-2 border-t-2 border-transparent border-t-gray-800"></div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-8 text-center">
        <p className="text-sm text-gray-600 mb-4">Hover over timeline points for detailed milestones</p>
        <div className="flex justify-center gap-6 flex-wrap">
          {swimlaneData.map((lane, index) => (
            <div key={index} className="flex items-center gap-2 text-xs">
              <div className={`w-3 h-3 ${lane.color} rounded-full`}></div>
              <span className="text-gray-700">{lane.category}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  const slides = [
    // Slide 1: Timeline
    <div key="slide1" className="space-y-8">
      <div className="text-center space-y-4">
        <Badge variant="outline" className="text-blue-600 border-blue-600">
          SLIDE 1 OF 5
        </Badge>
        <h1 className="text-4xl font-bold text-gray-800">AI Impact Timeline: Strategic Planning Horizons</h1>
        <p className="text-lg text-gray-600">Evidence-based forecast from 300+ research articles & industry analysis</p>
      </div>

      <EnhancedTimeline />

      <Card className="bg-gradient-to-r from-yellow-50 to-orange-50 border-yellow-200">
        <CardContent className="p-6">
          <h3 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
            <Target className="w-5 h-5 text-yellow-600" />
            Key Strategic Insights
          </h3>
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <div className="w-2 h-2 bg-yellow-500 rounded-full mt-2 flex-shrink-0" />
              <p className="text-gray-700">
                AI evolution will be gradual, not exponential—plan for steady progress over decades
              </p>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-2 h-2 bg-yellow-500 rounded-full mt-2 flex-shrink-0" />
              <p className="text-gray-700">
                Near-term focus should be on infrastructure and sustainable implementation
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>,

    // Slide 2: Consensus Analysis
    <div key="slide2" className="space-y-8">
      <div className="text-center space-y-4">
        <Badge variant="outline" className="text-blue-600 border-blue-600">
          SLIDE 2 OF 5
        </Badge>
      </div>
      <ConsensusAnalysis />
    </div>,

    // Slide 3: Market Signals
    <div key="slide3" className="space-y-8">
      <div className="text-center space-y-4">
        <Badge variant="outline" className="text-blue-600 border-blue-600">
          SLIDE 3 OF 5
        </Badge>
        <h1 className="text-4xl font-bold text-gray-800">Market Signals & Strategic Risks</h1>
        <p className="text-lg text-gray-600">Current indicators and potential disruption scenarios</p>
      </div>

      {/* Market Signals Matrix */}
      <Card>
        <CardContent className="p-6">
          <h3 className="text-xl font-bold mb-4">Market Signal Analysis</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b-2">
                  <th className="text-left py-3 font-semibold text-gray-700">Future Signal</th>
                  <th className="text-center py-3 font-semibold text-gray-700">Frequency</th>
                  <th className="text-center py-3 font-semibold text-gray-700">Time to Impact</th>
                </tr>
              </thead>
              <tbody>
                {marketSignals.map((signal, index) => (
                  <tr key={index} className="border-b">
                    <td className="py-3 text-gray-800">{signal.signal}</td>
                    <td className="py-3 text-center">
                      <Badge
                        variant={
                          signal.level === "high"
                            ? "destructive"
                            : signal.level === "moderate"
                              ? "default"
                              : "secondary"
                        }
                        className={signal.level === "moderate" ? "bg-orange-500 text-white" : ""}
                      >
                        {signal.frequency}
                      </Badge>
                    </td>
                    <td className="py-3 text-center text-sm text-gray-600">{signal.impact}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Risk Grid */}
      <div className="grid md:grid-cols-2 gap-6">
        {risks.map((risk, index) => {
          const Icon = risk.icon
          return (
            <Card
              key={index}
              className={`border-l-4 ${
                risk.type === "risk" ? "border-l-red-500 bg-red-50" : "border-l-green-500 bg-green-50"
              }`}
            >
              <CardContent className="p-6">
                <div className="flex items-start gap-3">
                  <Icon className={`w-5 h-5 mt-1 ${risk.type === "risk" ? "text-red-600" : "text-green-600"}`} />
                  <div>
                    <h4 className="font-bold text-gray-800 mb-2">{risk.title}</h4>
                    <p className="text-sm text-gray-700">{risk.description}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Quotes */}
      <div className="space-y-4">
        <Card className="border-l-4 border-l-blue-500 bg-blue-50">
          <CardContent className="p-6">
            <blockquote className="italic text-gray-800 mb-3">
              "The AI bubble may burst soon, followed by a period of reckoning, and then the emergence of productive
              AI-based business practices."
            </blockquote>
            <cite className="text-sm text-gray-600">— Industry Analysis: "Are We At Peak AI Bubble?"</cite>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-purple-500 bg-purple-50">
          <CardContent className="p-6">
            <blockquote className="italic text-gray-800 mb-3">
              "Investments in [AI superintelligence] are expected to require patience, as transformative outcomes are
              projected to emerge over a protracted period."
            </blockquote>
            <cite className="text-sm text-gray-600">— Financial Analysis: "Superintelligence Will Take Time"</cite>
          </CardContent>
        </Card>
      </div>
    </div>,

    // Slide 4: Recommendations
    <div key="slide4" className="space-y-8">
      <div className="text-center space-y-4">
        <Badge variant="outline" className="text-blue-600 border-blue-600">
          SLIDE 4 OF 5
        </Badge>
        <h1 className="text-4xl font-bold text-gray-800">Strategic Recommendations</h1>
        <p className="text-lg text-gray-600">Evidence-based action plan for executive leadership</p>
      </div>

      {/* Action Plans */}
      <div className="grid md:grid-cols-3 gap-6">
        {actionPlans.map((plan, index) => {
          const Icon = plan.icon
          return (
            <Card key={index} className="overflow-hidden">
              <div className={`bg-gradient-to-br ${plan.color} p-6 text-white`}>
                <div className="flex items-center gap-3 mb-4">
                  <Icon className="w-6 h-6" />
                  <h3 className="font-bold text-lg">{plan.period}</h3>
                </div>
                <div className="space-y-2">
                  {plan.actions.map((action, actionIndex) => (
                    <div key={actionIndex} className="flex items-start gap-2">
                      <div className="w-1.5 h-1.5 bg-white rounded-full mt-2 flex-shrink-0" />
                      <p className="text-sm">{action}</p>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )
        })}
      </div>

      {/* Executive Decision Framework */}
      <Card className="bg-gradient-to-r from-yellow-50 to-orange-50 border-yellow-200">
        <CardContent className="p-6">
          <h3 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5 text-yellow-600" />
            Executive Decision Framework
          </h3>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="space-y-3">
              <div className="bg-white p-4 rounded-lg shadow-sm">
                <h4 className="font-semibold text-gray-800 mb-2">Gradual Evolution</h4>
                <p className="text-sm text-gray-700">
                  Plan for steady AI progress over decades, not exponential breakthroughs
                </p>
              </div>
              <div className="bg-white p-4 rounded-lg shadow-sm">
                <h4 className="font-semibold text-gray-800 mb-2">Sustainable Investment</h4>
                <p className="text-sm text-gray-700">Avoid hype-driven spending; focus on proven AI applications</p>
              </div>
              <div className="bg-white p-4 rounded-lg shadow-sm">
                <h4 className="font-semibold text-gray-800 mb-2">Infrastructure First</h4>
                <p className="text-sm text-gray-700">Secure reliable data and energy infrastructure before scaling</p>
              </div>
            </div>
            <div className="space-y-3">
              <div className="bg-white p-4 rounded-lg shadow-sm">
                <h4 className="font-semibold text-gray-800 mb-2">Workforce Development</h4>
                <p className="text-sm text-gray-700">Start re-skilling programs now for long-term adaptation</p>
              </div>
              <div className="bg-white p-4 rounded-lg shadow-sm">
                <h4 className="font-semibold text-gray-800 mb-2">Risk Management</h4>
                <p className="text-sm text-gray-700">
                  Prepare for 2025-2030 market correction while maintaining strategic AI investments
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Next Steps */}
      <Card className="bg-gray-50 border-gray-200">
        <CardContent className="p-6">
          <h4 className="font-bold text-gray-800 mb-3">Next Steps:</h4>
          <div className="grid md:grid-cols-2 gap-4 text-sm text-gray-700">
            <div className="space-y-2">
              <p>1) Assess current AI investments against these timelines</p>
              <p>2) Develop infrastructure partnership strategy</p>
            </div>
            <div className="space-y-2">
              <p>3) Create workforce transition roadmap</p>
              <p>4) Establish market volatility contingency plans</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>,

    // Slide 5: Futures Cone
    <div key="slide5" className="space-y-8">
      <div className="text-center space-y-4">
        <Badge variant="outline" className="text-blue-600 border-blue-600">
          SLIDE 5 OF 5
        </Badge>
        <h1 className="text-4xl font-bold text-gray-800">AI Copyright & IP Rights: Futures Cone</h1>
        <p className="text-lg text-gray-600">
          Exploring potential scenarios for intellectual property in the age of artificial intelligence
        </p>
      </div>

      <FuturesCone />

      <Card className="bg-gradient-to-r from-blue-50 to-purple-50 border-blue-200">
        <CardContent className="p-6">
          <h3 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
            <Lightbulb className="w-5 h-5 text-blue-600" />
            Strategic Insight
          </h3>
          <p className="text-gray-700 leading-relaxed">
            The future of AI copyright and intellectual property rights is highly uncertain, with considerable room for
            both positive and negative disruption. The most likely near-term outcome is incremental legal adaptation and
            increased litigation, but stakeholders should prepare for possible regulatory divergence and novel legal
            frameworks emerging. Proactive action towards harmonization, transparency, and fair compensation could
            mitigate risks and foster more sustainable innovation.
          </p>
        </CardContent>
      </Card>
    </div>,
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      <div className="max-w-6xl mx-auto p-6">
        {/* Navigation */}
        <div className="flex justify-between items-center mb-8">
          <Button
            variant="outline"
            onClick={prevSlide}
            disabled={currentSlide === 0}
            className="bg-white text-gray-700"
          >
            <ChevronLeft className="w-4 h-4 mr-2" />
            Previous
          </Button>

          <div className="flex gap-2">
            {[0, 1, 2, 3, 4].map((index) => (
              <button
                key={index}
                onClick={() => setCurrentSlide(index)}
                className={`w-3 h-3 rounded-full transition-colors ${
                  currentSlide === index ? "bg-blue-600" : "bg-gray-300"
                }`}
              />
            ))}
          </div>

          <Button
            variant="outline"
            onClick={nextSlide}
            disabled={currentSlide === 4}
            className="bg-white text-gray-700"
          >
            Next
            <ChevronRight className="w-4 h-4 ml-2" />
          </Button>
        </div>

        {/* Slide Content */}
        <Card className="min-h-[800px] shadow-2xl">
          <CardContent className="p-12">{slides[currentSlide]}</CardContent>
        </Card>
      </div>
    </div>
  )
}
