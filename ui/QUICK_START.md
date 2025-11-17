# Quick Start: Replace Old Template with React UI

## TL;DR - What You Have Now

✅ **React UI is built and deployed** to `/static/trend-convergence/`
✅ **FastAPI route updated** to serve React build
⚠️ **BUT: The UI shows hardcoded Figma data**, not live backend data

## Access Your React UI

```bash
# Start the FastAPI server
python app/run.py

# Visit in browser:
http://localhost:6005/trend-convergence
```

## Current State

| Feature | Old Template | New React UI |
|---------|-------------|--------------|
| Visual Design | ❌ Bootstrap | ✅ Modern Tailwind |
| Dynamic Data | ✅ Works | ❌ Hardcoded |
| API Integration | ✅ Full | ❌ None |
| Authentication | ✅ Works | ❌ Not integrated |
| Configuration Modal | ✅ Works | ❌ Static |
| PDF/PNG Export | ✅ Works | ❌ Missing |

## Three Paths Forward

### Path 1: Make React UI Dynamic (Recommended)
**Time: 2-4 hours AI time**

Add API calls to React components:

```typescript
// ui/src/hooks/useTrendConvergence.ts
export function useTrendConvergence(topic: string) {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch(`/api/trend-convergence/${topic}?model=gpt-4o`)
      .then(res => res.json())
      .then(setData);
  }, [topic]);

  return data;
}
```

**Next Steps:**
1. Read `ui/INTEGRATION_GUIDE.md` (detailed instructions)
2. Modify `ui/src/App.tsx` to fetch data
3. Replace hardcoded values with state
4. Redeploy: `./scripts/deploy_react_ui.sh`

### Path 2: Keep Old Template (Immediate Working Solution)
**Time: 2 minutes**

Revert to the old, working Jinja2 template:

```bash
# Restore backup
cp app/routes/trend_convergence_routes.py.backup app/routes/trend_convergence_routes.py

# Restart server
```

### Path 3: Run Both in Parallel (Best of Both Worlds)
**Time: 5 minutes**

Keep old template working while developing React UI:

```python
# In app/routes/trend_convergence_routes.py

# New React UI (in development)
@router.get("/trend-convergence-new", response_class=HTMLResponse)
async def trend_convergence_page_new(request: Request, session: dict = Depends(verify_session)):
    """Render the new React UI"""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "trend-convergence")
    return FileResponse(os.path.join(static_dir, "index.html"))

# Old working template
@router.get("/trend-convergence", response_class=HTMLResponse)
async def trend_convergence_page(request: Request, session: dict = Depends(verify_session)):
    """Render the old working template"""
    return templates.TemplateResponse("trend_convergence.html", {"request": request, "session": session})
```

Access:
- Old (working): `http://localhost:6005/trend-convergence`
- New (React): `http://localhost:6005/trend-convergence-new`

## Deployment Commands

```bash
# Build and deploy React UI
./scripts/deploy_react_ui.sh

# Restart FastAPI server (if needed)
# Your usual restart command here
```

## Key Files

| File | Purpose |
|------|---------|
| `ui/src/App.tsx` | Main React component |
| `ui/INTEGRATION_GUIDE.md` | Detailed integration docs |
| `app/routes/trend_convergence_routes.py` | FastAPI route |
| `templates/trend_convergence.html` | Old working template |
| `static/trend-convergence/` | React build output |
| `scripts/deploy_react_ui.sh` | Deployment script |

## Testing Checklist

- [ ] React UI loads at `/trend-convergence`
- [ ] Browser console shows no errors
- [ ] Static assets (CSS/JS) load correctly
- [ ] Network tab shows requests to correct URLs
- [ ] Authentication redirects work (if logged out)

## Common Issues

### Issue: White screen / Nothing loads
**Solution:** Check browser console for errors. Likely asset path issue.

### Issue: Shows hardcoded "Cloud Repatriation" data
**Expected:** This is normal. The Figma export has hardcoded data. You need to add API integration (see Path 1).

### Issue: 404 on assets
**Solution:** Check asset paths in `/static/trend-convergence/index.html` are prefixed with `/static/trend-convergence/`

### Issue: Authentication error
**Solution:** Session cookies not being sent. Add `credentials: 'include'` to fetch calls.

## Need Help?

Read the full integration guide:
```bash
cat ui/INTEGRATION_GUIDE.md
```

## Summary

You now have a **beautiful, modern React UI** deployed, but it needs to be **connected to your backend APIs**. The old template still works as a reference implementation.

**Recommended approach:** Use Path 3 (run both in parallel) while developing Path 1 (make React dynamic).
