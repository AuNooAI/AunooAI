import { Consensus } from './Consensus';
import { Changelog, Roadmap } from './Docs';
import { ExecutiveBriefing } from './ExecutiveBriefing';
import { ExtremeOutliers } from './ExtremeOutliers';
import { FocusGroup } from './FocusGroup';
import { Newsletter } from './Newsletter';
import { SituationAssessment } from './SituationAssessment';
import { ForecastTracker } from './ForecastTracker';
import { TopicReports } from './TopicReports';
import { Topics } from './Topics';
import { FutureHorizons } from './FutureHorizons';
import { ImpactTimeline } from './ImpactTimeline';
import { MarketSignals } from './MarketSignals';
import { NotRebuilt } from './NotRebuilt';
import { StrategicRecommendations } from './StrategicRecommendations';
import type { ViewProps } from './types';

/** Tab id → view. Tabs without one show NotRebuilt. */
export const VIEWS: Record<string, (props: ViewProps) => React.ReactNode> = {
  'strategic-recommendations': StrategicRecommendations,
  'market-signals': MarketSignals,
  consensus: Consensus,
  'impact-timeline': ImpactTimeline,
  'future-horizons': FutureHorizons,
  topics: Topics,
  'forecast-tracker': ForecastTracker,
  'topic-reports': TopicReports,
  'extreme-outliers': ExtremeOutliers,
  'focus-group': FocusGroup,
  'executive-briefing': ExecutiveBriefing,
  'situation-assessment': SituationAssessment,
  newsletter: Newsletter,
  changelog: Changelog,
  roadmap: Roadmap,
};

export function renderView(props: ViewProps) {
  const View = VIEWS[props.tab.id] ?? NotRebuilt;
  return <View {...props} />;
}
