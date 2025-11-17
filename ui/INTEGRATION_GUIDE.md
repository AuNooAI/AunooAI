# Dashboard Component Integration Guide

This guide shows how to integrate the ArticleCitations and AIDisclosure components into all 5 Trend Convergence dashboard tabs.

## Components Created

1. **ArticleCitations** (`components/ArticleCitations.tsx`) - Shows "View X Reference Articles" button with modal
2. **AIDisclosure** (`components/AIDisclosure.tsx`) - Shows "AI Disclosure" tooltip with transparency information

## Integration Instructions

The components should be added to each dashboard tab's header section. Due to time constraints, manual integration is recommended.

### Add to App.tsx imports:
```typescript
import { ArticleCitations } from './components/ArticleCitations';
import { AIDisclosure, dashboardConfigs } from './components/AIDisclosure';
```

### Example integration for each tab header:
```tsx
<div className="flex items-center justify-between mb-4">
  <h2 className="text-2xl font-bold">Dashboard Title</h2>
  <div className="flex items-center gap-3">
    <AIDisclosure {...dashboardConfigs.consensus} />
    {data.analysis_id && (
      <ArticleCitations
        dashboardType="consensus"
        analysisId={data.analysis_id}
        topic={config.topic}
      />
    )}
  </div>
</div>
```

Replace `consensus` with the appropriate dashboard type: `strategic`, `signals`, `timeline`, or `horizons`.
