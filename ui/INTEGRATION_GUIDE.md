# React UI Integration Guide

## Current Status

The Figma-exported React UI has been integrated with the FastAPI backend as a **static build**. However, it currently displays **hardcoded data** from the Figma design and does not dynamically fetch data from the FastAPI backend.

## What's Been Done

### 1. Build Setup ✅
- React/TypeScript app with Vite build system
- Tailwind CSS for styling
- shadcn/ui component library
- Build configured in `vite.config.ts`

### 2. FastAPI Integration ✅
- Build output copied to `/static/trend-convergence/`
- Route updated in `app/routes/trend_convergence_routes.py`:
  ```python
  @router.get("/trend-convergence", response_class=HTMLResponse)
  async def trend_convergence_page(request: Request, session: dict = Depends(verify_session)):
      """Render the trend convergence analysis page with React UI"""
      static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "trend-convergence")
      index_path = os.path.join(static_dir, "index.html")

      if os.path.exists(index_path):
          return FileResponse(index_path)
      else:
          # Fallback to old template if React build not found
          logger.warning("React build not found, falling back to Jinja2 template")
          return templates.TemplateResponse("trend_convergence.html", {"request": request, "session": session})
  ```

### 3. Deployment Script ✅
- Created `/scripts/deploy_react_ui.sh`
- Automates: build → copy → path fixing

## Access the UI

After starting your FastAPI server:
```bash
# Navigate to:
http://localhost:<your-port>/trend-convergence
```

## What Needs to Be Done

### Phase 1: Make UI Dynamic (Required for Production)

The current Figma export is **static HTML/JS with hardcoded data**. To make it functional:

#### Option A: Modify React Components (Recommended)
1. **Update React components** to fetch data from FastAPI:
   ```typescript
   // Example: src/components/TrendConvergence.tsx
   import { useEffect, useState } from 'react';

   interface AnalysisData {
     strategic_recommendations: {
       near_term: { trends: string[] };
       mid_term: { trends: string[] };
       long_term: { trends: string[] };
     };
     executive_decision_framework: any;
     next_steps: string[];
   }

   export function TrendConvergenceView() {
     const [data, setData] = useState<AnalysisData | null>(null);
     const [loading, setLoading] = useState(true);

     useEffect(() => {
       const fetchData = async () => {
         const topic = 'AI Adoption'; // Get from state/props
         const response = await fetch(`/api/trend-convergence/${topic}?model=gpt-4o`);
         const result = await response.json();
         setData(result);
         setLoading(false);
       };

       fetchData();
     }, []);

     if (loading) return <div>Loading...</div>;

     return (
       <div>
         {/* Render data.strategic_recommendations */}
       </div>
     );
   }
   ```

2. **Add state management** (React Context or Zustand)
3. **Connect to existing APIs**:
   - `/api/trend-convergence/{topic}` - Main analysis
   - `/api/organizational-profiles` - Profile management
   - `/api/topics` - Available topics

#### Option B: Hybrid Approach
Keep the Figma UI as a **static template** and inject data server-side:
1. Convert the React build back to a Jinja2 template
2. Use server-side rendering to populate data
3. Less interactive but simpler integration

### Phase 2: Authentication Integration

The old template uses `session=Depends(verify_session)`. Add this to React:

```typescript
// src/utils/api.ts
export async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const response = await fetch(url, {
    ...options,
    credentials: 'include', // Include session cookie
    headers: {
      ...options.headers,
      'Content-Type': 'application/json',
    },
  });

  if (response.status === 401) {
    // Redirect to login
    window.location.href = '/login';
  }

  return response;
}
```

### Phase 3: Feature Parity

The old template had these features that need to be replicated:

1. **Configuration Modal**
   - Topic selection
   - Timeframe selection
   - AI model selection
   - Analysis depth options
   - Organizational profile selection
   - Sample size configuration
   - Consistency mode

2. **Analysis Display**
   - Strategic recommendations (near/mid/long-term)
   - Executive decision framework
   - Next steps
   - Explainability tooltips

3. **Export Features**
   - Download as PDF
   - Download as PNG

4. **Profile Management**
   - Create/edit/delete profiles
   - Profile form with all fields

## Comparison: Old vs New

### Old Template (`templates/trend_convergence.html`)
**Pros:**
- ✅ Fully integrated with backend
- ✅ Dynamic data loading
- ✅ Authentication working
- ✅ All features implemented
- ✅ Server-side rendering

**Cons:**
- ❌ jQuery-based (older approach)
- ❌ Inline JavaScript (harder to maintain)
- ❌ Bootstrap styling (less modern)

### New React UI (`ui/`)
**Pros:**
- ✅ Modern React/TypeScript
- ✅ Component-based architecture
- ✅ Tailwind CSS (more flexible)
- ✅ shadcn/ui components
- ✅ Better developer experience

**Cons:**
- ❌ Static Figma export (no dynamic data)
- ❌ Hardcoded values
- ❌ No API integration
- ❌ No authentication
- ❌ Missing features

## Quick Start Development

### 1. Run in Development Mode
```bash
cd ui/
npm run dev
```
This starts Vite dev server at `http://localhost:5173`

### 2. Build for Production
```bash
cd ui/
npm run build
```
Output: `ui/build/`

### 3. Deploy to FastAPI
```bash
./scripts/deploy_react_ui.sh
```

### 4. Test
```bash
# Start FastAPI server
python app/run.py

# Visit:
# http://localhost:6005/trend-convergence
```

## Recommended Next Steps

### Immediate (1-2 hours AI time):
1. **Extract hardcoded data** from React components
2. **Create API service layer** (`src/services/api.ts`)
3. **Add fetch calls** to existing FastAPI endpoints
4. **Test with real backend data**

### Short-term (2-4 hours AI time):
1. **Rebuild configuration modal** with form state
2. **Add loading states** and error handling
3. **Implement authentication checks**
4. **Add PDF/PNG export** (use existing logic)

### Long-term (4-8 hours AI time):
1. **Profile management UI** (full CRUD)
2. **Real-time updates** (WebSocket/SSE)
3. **State management** (React Query/Zustand)
4. **Unit tests** for components
5. **E2E tests** with Playwright

## Alternative: Use Old Template

If you need a **working solution immediately**, consider:

1. **Keep using the old template** (`templates/trend_convergence.html`)
2. **Gradually migrate** features to React
3. **Run both in parallel** during transition:
   - `/trend-convergence` → React UI (new)
   - `/trend-convergence-legacy` → Jinja2 template (old, working)

## Files Modified

1. `/app/routes/trend_convergence_routes.py` - Added React route
2. `/static/trend-convergence/` - React build output
3. `/scripts/deploy_react_ui.sh` - Deployment automation
4. `/ui/` - React source code

## Rollback Instructions

If you need to revert to the old template:

```python
# In app/routes/trend_convergence_routes.py
@router.get("/trend-convergence", response_class=HTMLResponse)
async def trend_convergence_page(request: Request, session: dict = Depends(verify_session)):
    """Render the trend convergence analysis page"""
    return templates.TemplateResponse("trend_convergence.html", {"request": request, "session": session})
```

Or restore from backup:
```bash
cp app/routes/trend_convergence_routes.py.backup app/routes/trend_convergence_routes.py
```

## Questions?

- **"Why is the React UI showing hardcoded data?"**
  The Figma export generates static components. You need to add API calls.

- **"Can I use both templates?"**
  Yes! Add a new route for the legacy template.

- **"How do I debug?"**
  Use browser DevTools → Network tab to see if API calls are being made.

- **"Should I keep the old template?"**
  Yes, until the React UI has feature parity.
