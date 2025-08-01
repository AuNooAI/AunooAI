# Production Migration Guide: Trend Convergence Consistency Features

## Overview

This guide provides step-by-step instructions for migrating existing AuNoo AI installations to include the new trend convergence consistency features. The migration is designed to be **zero-downtime** and **fully backwards compatible**.

## 🔒 Pre-Migration Checklist

### 1. **System Requirements**
- [ ] Python 3.8+ installed
- [ ] SQLite database accessible
- [ ] Application has write permissions to database directory
- [ ] Backup storage available (minimum 2x current database size)

### 2. **Pre-Migration Backup**
```bash
# 1. Stop the application (if possible for maintenance window)
# 2. Create full database backup
cp app/data/fnaapp.db app/data/fnaapp.db.backup.$(date +%Y%m%d_%H%M%S)

# 3. Create configuration backup
cp -r app/config app/config.backup.$(date +%Y%m%d_%H%M%S)

# 4. Verify backup integrity
sqlite3 app/data/fnaapp.db.backup.* ".schema" > /dev/null
echo "Backup verification: $?"  # Should output 0
```

### 3. **Version Compatibility Check**
```bash
# Check current application version
cat version.txt

# Verify Python version
python --version  # Should be 3.8+

# Check database schema version
sqlite3 app/data/fnaapp.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='analysis_versions';"
```

## 🚀 Migration Procedure

### **Phase 1: Code Deployment**

#### Step 1: Deploy New Code Files
```bash
# 1. Deploy the modified backend file
# Copy: app/routes/trend_convergence_routes.py

# 2. Deploy the modified frontend file  
# Copy: templates/trend_convergence.html

# 3. Deploy the migration script
# Copy: scripts/migrate_consistency_features.py

# 4. Make migration script executable
chmod +x scripts/migrate_consistency_features.py
```

#### Step 2: Verify Code Deployment
```bash
# Check that new functions exist
grep -q "class ConsistencyMode" app/routes/trend_convergence_routes.py
echo "ConsistencyMode enum found: $?"

grep -q "select_articles_deterministic" app/routes/trend_convergence_routes.py  
echo "Deterministic selection found: $?"

grep -q "consistencyMode" templates/trend_convergence.html
echo "Frontend controls found: $?"
```

### **Phase 2: Database Migration**

#### Step 1: Test Migration (Dry Run)
```bash
# Create a test copy of the database
cp app/data/fnaapp.db app/data/fnaapp_test.db

# Run migration on test database
python scripts/migrate_consistency_features.py app/data/fnaapp_test.db

# Verify test migration success
if [ $? -eq 0 ]; then
    echo "✅ Test migration successful"
    rm app/data/fnaapp_test.db
else
    echo "❌ Test migration failed - DO NOT PROCEED"
    exit 1
fi
```

#### Step 2: Production Database Migration
```bash
# Run the actual migration
python scripts/migrate_consistency_features.py

# Expected output:
# ✅ MIGRATION COMPLETED SUCCESSFULLY!
# • Enhanced caching system with comprehensive cache keys
# • Deterministic article selection for consistent results  
# • Consistency scoring and monitoring
# • Four consistency modes: deterministic, low_variance, balanced, creative
```

#### Step 3: Verify Migration Success
```bash
# Check new tables exist
sqlite3 app/data/fnaapp.db "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('analysis_versions_v2', 'trend_consistency_metrics');"

# Expected output:
# analysis_versions_v2
# trend_consistency_metrics

# Check data migration
sqlite3 app/data/fnaapp.db "SELECT COUNT(*) FROM analysis_versions_v2;"
# Should show migrated analysis versions

# Verify indexes
sqlite3 app/data/fnaapp.db "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';"
# Should show: idx_cache_key_created, idx_topic_created, idx_consistency_topic_date
```

### **Phase 3: Application Restart**

#### Step 1: Graceful Application Restart
```bash
# If using systemd
sudo systemctl restart aunoo-ai

# If using pm2
pm2 restart aunoo-ai

# If running manually
# Kill existing process and restart
pkill -f "python.*main.py"
nohup python main.py > logs/app.log 2>&1 &
```

#### Step 2: Health Check
```bash
# Wait for application to start
sleep 10

# Check application health
curl -f http://localhost:8000/health || echo "Health check failed"

# Check trend convergence page loads
curl -f http://localhost:8000/trend-convergence || echo "Trend convergence page failed"

# Check API endpoints
curl -f http://localhost:8000/api/models || echo "Models API failed"
```

### **Phase 4: Feature Verification**

#### Step 1: Test New API Parameters
```bash
# Test with consistency mode parameter
curl -X GET "http://localhost:8000/api/trend-convergence/test_topic?model=gpt-4&consistency_mode=deterministic&enable_caching=true" \
  -H "Content-Type: application/json"

# Should return analysis with consistency metadata
```

#### Step 2: Frontend Testing
1. Navigate to `/trend-convergence` in browser
2. Click configuration gear icon
3. Verify new controls are present:
   - [ ] "Analysis Consistency" dropdown with 4 options  
   - [ ] "Enable Result Caching" toggle switch
4. Test configuration save/load functionality

#### Step 3: Consistency Testing
```bash
# Run the same analysis twice in deterministic mode
# Results should be identical (test this manually through UI)
```

## 🔄 Rollback Procedure

If issues occur, follow this rollback procedure:

### **Emergency Rollback (< 5 minutes)**
```bash
# 1. Restore previous code files
git checkout HEAD~1 app/routes/trend_convergence_routes.py
git checkout HEAD~1 templates/trend_convergence.html

# 2. Restart application
sudo systemctl restart aunoo-ai

# 3. Verify old functionality works
curl -f http://localhost:8000/trend-convergence
```

### **Full Database Rollback (if needed)**
```bash
# 1. Stop application
sudo systemctl stop aunoo-ai

# 2. Restore database backup
cp app/data/fnaapp.db.backup.* app/data/fnaapp.db

# 3. Remove new tables (optional, for clean state)
sqlite3 app/data/fnaapp.db "DROP TABLE IF EXISTS analysis_versions_v2;"
sqlite3 app/data/fnaapp.db "DROP TABLE IF EXISTS trend_consistency_metrics;"

# 4. Restart application
sudo systemctl start aunoo-ai
```

## 📊 Migration Monitoring

### **Key Metrics to Monitor**

#### Database Performance
```sql
-- Monitor cache table growth
SELECT COUNT(*) as cache_entries, 
       MAX(created_at) as latest_entry,
       MIN(created_at) as oldest_entry
FROM analysis_versions_v2;

-- Check cache hit efficiency
SELECT topic, COUNT(*) as cache_entries
FROM analysis_versions_v2 
GROUP BY topic 
ORDER BY cache_entries DESC;
```

#### Application Performance
- Response times for trend convergence analyses
- Cache hit rates (logged in application)
- Database query performance
- Memory usage patterns

#### User Experience
- Analysis consistency scores
- User adoption of new consistency modes
- Error rates and user feedback

### **Log Monitoring**
```bash
# Monitor application logs for consistency features
tail -f logs/app.log | grep -i "consistency\|cache\|deterministic"

# Key log messages to watch for:
# - "Using deterministic mode"
# - "Cache hit: [cache_key]"
# - "Cached analysis: [cache_key]"
# - "Selected X diverse articles using Y mode"
```

## 🛠️ Troubleshooting Common Issues

### **Issue 1: Migration Script Fails**
```bash
# Symptoms: Migration script exits with error code 1
# Solution: Check database permissions and disk space

# Check disk space
df -h | grep $(dirname app/data/fnaapp.db)

# Check database file permissions
ls -la app/data/fnaapp.db

# Check database integrity
sqlite3 app/data/fnaapp.db "PRAGMA integrity_check;"
```

### **Issue 2: New Tables Not Created**
```bash
# Symptoms: Tables missing after migration
# Solution: Re-run migration with verbose logging

python scripts/migrate_consistency_features.py 2>&1 | tee migration.log

# Check for specific error messages in migration.log
```

### **Issue 3: Frontend Controls Not Appearing**
```bash
# Symptoms: Configuration modal missing new controls
# Solution: Clear browser cache and verify template deployment

# Check template file was updated
grep -c "consistencyMode" templates/trend_convergence.html
# Should return > 0

# Force browser cache refresh
# Hard refresh: Ctrl+Shift+R (Chrome/Firefox)
```

### **Issue 4: API Parameters Not Recognized**
```bash
# Symptoms: API returns 422 validation errors for new parameters
# Solution: Verify backend code deployment

# Check if ConsistencyMode enum exists
python -c "
from app.routes.trend_convergence_routes import ConsistencyMode
print('ConsistencyMode available:', list(ConsistencyMode))
"
```

## 📋 Post-Migration Checklist

### **Immediate (Day 1)**
- [ ] All existing analyses still work
- [ ] New consistency controls visible in UI
- [ ] Cache tables populated with new analyses
- [ ] No error spikes in application logs
- [ ] Database performance stable

### **Short-term (Week 1)**
- [ ] Cache hit rate > 20% (as users repeat analyses)
- [ ] User feedback on consistency improvements
- [ ] No memory leaks or performance degradation
- [ ] Consistency modes working as expected

### **Long-term (Month 1)**
- [ ] Cache hit rate > 50% (steady state)
- [ ] Measurable consistency improvements
- [ ] User adoption of deterministic mode for reports
- [ ] Database growth within expected parameters

## 🚨 Critical Success Factors

### **Must-Have Outcomes**
1. ✅ **Zero Data Loss**: All existing analyses preserved
2. ✅ **Backwards Compatibility**: Existing functionality unchanged
3. ✅ **Performance Stable**: No degradation in response times
4. ✅ **User Experience**: New features accessible and working

### **Success Metrics**
- Migration completes in < 30 minutes
- Database backup/restore tested and verified
- All existing API endpoints return expected results
- New consistency features functional in production

## 📞 Support and Communication

### **User Communication Template**
```
Subject: New Feature: Analysis Consistency Controls

Dear Users,

We've deployed enhanced consistency controls for trend convergence analysis:

🎯 NEW FEATURES:
• Four consistency modes for predictable results
• Intelligent caching for faster repeated analyses  
• Enhanced configuration options

🔧 HOW TO USE:
1. Click the gear icon in trend convergence
2. Select your preferred consistency mode
3. Enable caching for better performance

No action required - all existing analyses continue to work normally.

Questions? Contact: [support email]
```

### **Escalation Contacts**
- **Database Issues**: DBA team
- **Application Errors**: Backend development team  
- **User Interface**: Frontend development team
- **Performance Issues**: DevOps/Infrastructure team

---

## 📝 Migration Checklist Summary

```
PRE-MIGRATION:
□ System requirements verified
□ Full backup created and tested
□ Version compatibility confirmed
□ Test migration successful

MIGRATION:
□ Code files deployed
□ Database migration completed  
□ Application restarted successfully
□ Health checks passed

POST-MIGRATION:
□ New features verified working
□ Existing functionality confirmed
□ Monitoring configured
□ User communication sent
□ Rollback procedure documented and tested

SIGN-OFF:
□ Technical lead approval
□ QA verification complete
□ Production deployment complete
□ Migration marked successful
```

---

*This migration guide ensures a smooth, safe deployment of consistency features to production environments while maintaining full backwards compatibility and providing clear rollback procedures.*