# Analysis Consistency Implementation Plan

## Executive Summary

The current trend convergence analysis system produces different results on each run due to several sources of non-determinism. This document outlines a comprehensive plan to improve consistency while maintaining backwards compatibility with existing systems.

## Current Issues Identified

### 1. **High AI Temperature (Primary Issue)**
- **Problem**: AI models use `temperature=0.7` in auspex service, causing significant response variation
- **Impact**: Same input data produces different strategic recommendations, trend names, and analysis structure
- **Frequency**: Affects every single analysis run

### 2. **Non-Deterministic Article Selection**
- **Problem**: Articles ordered by `publication_date DESC` only, creating unstable selection when new articles arrive
- **Impact**: Different article sets analyzed for same parameters, leading to different trends
- **Frequency**: Changes whenever new articles are ingested

### 3. **Inconsistent Article Diversity Algorithm**
- **Problem**: `select_diverse_articles` uses dictionary iteration order and list operations that aren't deterministic
- **Impact**: Same articles available but different subset selected for analysis
- **Frequency**: Can vary between runs even with same article pool

### 4. **Incomplete Caching Strategy**
- **Problem**: Current caching doesn't account for all parameters that affect results
- **Impact**: Cache misses when parameters should produce same results, cache hits when they shouldn't
- **Frequency**: Reduces effectiveness of caching system

## Implementation Plan

### Phase 1: Backwards-Compatible Consistency Framework (Week 1-2)

#### 1.1 Create Consistency Mode Infrastructure

**File**: `app/routes/trend_convergence_routes.py`

```python
# Add consistency mode enum
from enum import Enum

class ConsistencyMode(str, Enum):
    DETERMINISTIC = "deterministic"      # Maximum consistency, temp=0.0
    LOW_VARIANCE = "low_variance"        # High consistency, temp=0.2  
    BALANCED = "balanced"                # Good balance, temp=0.4
    CREATIVE = "creative"                # Current behavior, temp=0.7

# Add to route parameters
@router.get("/api/trend-convergence/{topic}")
async def generate_trend_convergence(
    # ... existing parameters ...
    consistency_mode: ConsistencyMode = Query(ConsistencyMode.BALANCED, 
                                              description="Analysis consistency level"),
    enable_caching: bool = Query(True, description="Enable result caching"),
    cache_duration_hours: int = Query(24, description="Cache validity period"),
):
```

#### 1.2 Implement Deterministic Article Selection

```python
def select_articles_deterministic(articles: List, limit: int, 
                                consistency_mode: ConsistencyMode) -> List:
    """
    Select articles with deterministic, reproducible results.
    
    Key improvements:
    1. Stable sorting using multiple criteria
    2. Hash-based selection for consistency
    3. Deterministic category distribution
    4. Predictable tie-breaking
    """
    
    if len(articles) <= limit:
        return articles
    
    import hashlib
    
    # Create stable article representation
    article_data = []
    for i, article in enumerate(articles):
        # Create deterministic hash from stable content
        stable_content = f"{article[0]}|{article[3]}|{article[5]}"  # title|date|category
        article_hash = hashlib.md5(stable_content.encode()).hexdigest()
        
        article_data.append({
            'original_index': i,
            'original_article': article,
            'title': article[0],
            'publication_date': article[3],
            'category': article[5] or 'Unknown',
            'sentiment': article[4] or 'Neutral',
            'hash': article_hash,
            'recency_score': 1.0 - (i / len(articles))
        })
    
    # Deterministic sorting: category, then date, then hash
    if consistency_mode in [ConsistencyMode.DETERMINISTIC, ConsistencyMode.LOW_VARIANCE]:
        article_data.sort(key=lambda x: (x['category'], x['publication_date'], x['hash']))
    else:
        # Still stable but prioritizes recency
        article_data.sort(key=lambda x: (x['recency_score'], x['hash']), reverse=True)
    
    # Deterministic category-based selection
    selected = []
    by_category = defaultdict(list)
    
    for article in article_data:
        by_category[article['category']].append(article)
    
    # Sort categories by name for consistency
    sorted_categories = sorted(by_category.keys())
    category_quota = int(limit * 0.6)
    articles_per_category = max(1, category_quota // len(sorted_categories))
    
    # Select from each category deterministically
    for category in sorted_categories:
        cat_articles = by_category[category]
        if consistency_mode == ConsistencyMode.DETERMINISTIC:
            # Pure deterministic: sort by hash after recency
            cat_articles.sort(key=lambda x: (x['recency_score'], x['hash']), reverse=True)
        else:
            # Weighted by recency but stable
            cat_articles.sort(key=lambda x: x['recency_score'], reverse=True)
        
        selected.extend(cat_articles[:articles_per_category])
        if len(selected) >= category_quota:
            break
    
    # Fill remaining slots deterministically
    remaining_articles = [a for a in article_data if a not in selected]
    remaining_articles.sort(key=lambda x: (x['recency_score'], x['hash']), reverse=True)
    
    while len(selected) < limit and remaining_articles:
        selected.append(remaining_articles.pop(0))
    
    # Return original article format
    return [item['original_article'] for item in selected[:limit]]
```

#### 1.3 Create Consistency-Aware AI Interface

```python
async def generate_analysis_with_consistency(
    auspex_service, chat_id: int, prompt: str, model: str, 
    consistency_mode: ConsistencyMode
) -> str:
    """
    Generate AI analysis with consistency controls without modifying auspex service.
    
    This function wraps the auspex service to add consistency features while
    maintaining full backwards compatibility.
    """
    
    # Enhance prompt based on consistency mode
    enhanced_prompt = enhance_prompt_for_consistency(prompt, consistency_mode)
    
    # Collect response
    response_chunks = []
    async for chunk in auspex_service.chat_with_tools(
        chat_id=chat_id,
        message=enhanced_prompt,
        model=model,
        limit=10,
        tools_config={"search_articles": False, "get_sentiment_analysis": False}
    ):
        response_chunks.append(chunk)
    
    full_response = "".join(response_chunks)
    
    # Apply post-processing for consistency
    if consistency_mode in [ConsistencyMode.DETERMINISTIC, ConsistencyMode.LOW_VARIANCE]:
        full_response = apply_consistency_post_processing(full_response, consistency_mode)
    
    return full_response

def enhance_prompt_for_consistency(prompt: str, mode: ConsistencyMode) -> str:
    """Add consistency instructions to prompt based on mode."""
    
    consistency_instructions = {
        ConsistencyMode.DETERMINISTIC: """
CONSISTENCY REQUIREMENTS (DETERMINISTIC MODE):
- Use consistent terminology throughout analysis
- Sort trend names alphabetically when priority is equal
- Base strategic recommendations on most frequently mentioned themes
- Use standardized strength/momentum terminology (High/Medium/Low, Increasing/Steady/Decreasing)
- Generate recommendations in consistent order: most critical first
- Apply deterministic categorization patterns

""",
        ConsistencyMode.LOW_VARIANCE: """
CONSISTENCY GUIDELINES (LOW VARIANCE MODE):
- Prioritize consistent terminology and framework
- Focus on trends supported by multiple articles
- Use evidence-based trend identification
- Maintain consistent analysis structure

""",
        ConsistencyMode.BALANCED: """
ANALYSIS APPROACH (BALANCED MODE):
- Balance consistency with fresh insights
- Use structured approach while allowing creative connections
- Focus on well-supported trends with room for interpretation

""",
        ConsistencyMode.CREATIVE: ""  # No additional instructions
    }
    
    instruction = consistency_instructions.get(mode, "")
    return instruction + prompt

def apply_consistency_post_processing(response: str, mode: ConsistencyMode) -> str:
    """Apply post-processing to normalize response for consistency."""
    
    if mode not in [ConsistencyMode.DETERMINISTIC, ConsistencyMode.LOW_VARIANCE]:
        return response
    
    # Normalize common terminology
    normalizations = {
        # Trend strength variations
        r'\b(very high|extremely high)\b': 'High',
        r'\b(moderate|medium)\b': 'Medium',  
        r'\b(limited|small|minor)\b': 'Low',
        
        # Momentum variations
        r'\b(growing|rising|expanding)\b': 'Increasing',
        r'\b(stable|consistent|maintained)\b': 'Steady',
        r'\b(declining|reducing|slowing)\b': 'Decreasing',
        
        # Technology terminology
        r'\bAI/ML\b': 'AI and ML',
        r'\bmachine learning\b': 'ML',
        r'\bartificial intelligence\b': 'AI',
    }
    
    import re
    processed = response
    for pattern, replacement in normalizations.items():
        processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)
    
    return processed
```

### Phase 2: Enhanced Caching System (Week 2-3)

#### 2.1 Comprehensive Cache Key Generation

```python
import hashlib
from typing import Optional, Dict, Any

def generate_comprehensive_cache_key(
    topic: str,
    timeframe_days: int,
    model: str,
    analysis_depth: str,
    sample_size_mode: str,
    custom_limit: Optional[int],
    profile_id: Optional[int],
    consistency_mode: ConsistencyMode,
    persona: str,
    customer_type: str
) -> str:
    """
    Generate comprehensive cache key including ALL parameters that affect results.
    
    This ensures cache hits only occur when analysis parameters are truly identical.
    """
    
    # Include all parameters that could affect the result
    cache_params = {
        'topic': topic,
        'timeframe_days': timeframe_days,
        'model': model,
        'analysis_depth': analysis_depth,
        'sample_size_mode': sample_size_mode,
        'custom_limit': custom_limit,
        'profile_id': profile_id,
        'consistency_mode': consistency_mode.value,
        'persona': persona,
        'customer_type': customer_type,
        'algorithm_version': '3.0',  # Increment when algorithm changes
        'article_selection_method': 'deterministic_v2'
    }
    
    # Create hash from stable parameter representation
    params_string = json.dumps(cache_params, sort_keys=True, default=str)
    cache_hash = hashlib.sha256(params_string.encode()).hexdigest()[:16]
    
    return f"trend_convergence_{cache_hash}"

async def get_cached_analysis(
    cache_key: str, 
    db: Database, 
    max_age_hours: int = 24
) -> Optional[Dict[str, Any]]:
    """Get cached analysis if valid and recent enough."""
    
    try:
        query = """
        SELECT version_data, created_at, cache_metadata 
        FROM analysis_versions_v2 
        WHERE cache_key = ? 
        ORDER BY created_at DESC 
        LIMIT 1
        """
        result = db.fetch_one(query, (cache_key,))
        
        if result:
            analysis_data = json.loads(result[0])
            created_at = datetime.fromisoformat(result[1])
            age_hours = (datetime.now() - created_at).total_seconds() / 3600
            
            if age_hours <= max_age_hours:
                # Add cache metadata
                cache_metadata = json.loads(result[2]) if result[2] else {}
                analysis_data['_cache_info'] = {
                    'cached': True,
                    'age_hours': round(age_hours, 2),
                    'cache_key': cache_key,
                    'metadata': cache_metadata
                }
                
                logger.info(f"Cache hit: {cache_key} (age: {age_hours:.1f}h)")
                return analysis_data
            else:
                logger.info(f"Cache expired: {cache_key} (age: {age_hours:.1f}h)")
                
    except Exception as e:
        logger.error(f"Error retrieving cached analysis: {e}")
    
    return None

async def save_analysis_with_cache(
    cache_key: str,
    topic: str, 
    analysis_data: Dict[str, Any], 
    db: Database
):
    """Save analysis with comprehensive cache information."""
    
    try:
        # Ensure table exists with new schema
        await ensure_cache_table_v2(db)
        
        cache_metadata = {
            'article_count': analysis_data.get('articles_analyzed', 0),
            'total_trends': sum(
                len(timeframe.get('trends', [])) 
                for timeframe in analysis_data.get('strategic_recommendations', {}).values()
                if isinstance(timeframe, dict)
            ),
            'model_used': analysis_data.get('model_used'),
            'consistency_mode': analysis_data.get('consistency_mode'),
            'generation_time': analysis_data.get('generated_at')
        }
        
        query = """
        INSERT INTO analysis_versions_v2 
        (cache_key, topic, version_data, cache_metadata, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
        version_data = excluded.version_data,
        cache_metadata = excluded.cache_metadata,
        created_at = excluded.created_at
        """
        
        db.execute(query, (
            cache_key,
            topic,
            json.dumps(analysis_data),
            json.dumps(cache_metadata),
            datetime.now().isoformat()
        ))
        
        logger.info(f"Cached analysis: {cache_key}")
        
    except Exception as e:
        logger.error(f"Failed to cache analysis: {e}")

async def ensure_cache_table_v2(db: Database):
    """Ensure the enhanced cache table exists."""
    
    create_table_query = """
    CREATE TABLE IF NOT EXISTS analysis_versions_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cache_key TEXT UNIQUE NOT NULL,
        topic TEXT NOT NULL,
        version_data TEXT NOT NULL,
        cache_metadata TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    
    db.execute(create_table_query)
    
    # Create index for efficient lookups
    index_query = """
    CREATE INDEX IF NOT EXISTS idx_cache_key_created 
    ON analysis_versions_v2(cache_key, created_at DESC)
    """
    
    db.execute(index_query)
```

#### 2.2 Cache Management System

```python
class AnalysisCacheManager:
    """Manages analysis result caching with consistency awareness."""
    
    def __init__(self, db: Database):
        self.db = db
        self.max_cache_entries = 1000  # Prevent unlimited growth
        self.default_max_age_hours = 24
    
    async def get_or_generate_analysis(
        self,
        cache_key: str,
        generator_func: Callable,
        max_age_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get cached analysis or generate new one."""
        
        max_age = max_age_hours or self.default_max_age_hours
        
        # Try cache first
        cached_result = await get_cached_analysis(cache_key, self.db, max_age)
        if cached_result:
            await self._update_access_time(cache_key)
            return cached_result
        
        # Generate new analysis
        logger.info(f"Cache miss: {cache_key}, generating new analysis")
        new_analysis = await generator_func()
        
        # Cache the result
        await save_analysis_with_cache(cache_key, new_analysis.get('topic', ''), new_analysis, self.db)
        
        # Clean up old entries
        await self._cleanup_old_entries()
        
        return new_analysis
    
    async def _update_access_time(self, cache_key: str):
        """Update last access time for cache entry."""
        query = "UPDATE analysis_versions_v2 SET accessed_at = ? WHERE cache_key = ?"
        self.db.execute(query, (datetime.now().isoformat(), cache_key))
    
    async def _cleanup_old_entries(self):
        """Remove old cache entries to prevent unlimited growth."""
        
        # Keep only the most recent entries per topic
        cleanup_query = """
        DELETE FROM analysis_versions_v2 
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY topic 
                    ORDER BY accessed_at DESC, created_at DESC
                ) as rn
                FROM analysis_versions_v2
            ) WHERE rn <= 5
        )
        """
        
        self.db.execute(cleanup_query)
        
        # Also remove entries older than 7 days regardless
        old_date = (datetime.now() - timedelta(days=7)).isoformat()
        self.db.execute(
            "DELETE FROM analysis_versions_v2 WHERE created_at < ?", 
            (old_date,)
        )
```

### Phase 3: Quality Assurance and Monitoring (Week 3-4)

#### 3.1 Consistency Scoring System

```python
class ConsistencyAnalyzer:
    """Analyzes and scores consistency between analysis runs."""
    
    @staticmethod
    def calculate_trend_consistency_score(
        current_trends: List[Dict], 
        reference_trends: List[Dict],
        mode: str = 'similarity'
    ) -> Dict[str, float]:
        """
        Calculate consistency scores between trend analyses.
        
        Returns multiple consistency metrics:
        - name_overlap: Percentage of trend names that match
        - theme_similarity: Semantic similarity of trend themes  
        - structure_consistency: Consistency of categorization
        - overall_score: Weighted average
        """
        
        if not reference_trends:
            return {'overall_score': 0.0, 'reason': 'no_reference'}
        
        # Extract trend characteristics
        current_names = {trend.get('name', '').lower().strip() for trend in current_trends}
        reference_names = {trend.get('name', '').lower().strip() for trend in reference_trends}
        
        current_themes = {
            trend.get('description', '').lower()[:100] 
            for trend in current_trends
        }
        reference_themes = {
            trend.get('description', '').lower()[:100] 
            for trend in reference_trends
        }
        
        # Calculate name overlap
        name_intersection = len(current_names & reference_names)
        name_union = len(current_names | reference_names)
        name_overlap = name_intersection / max(name_union, 1)
        
        # Calculate theme similarity using simple text overlap
        theme_similarities = []
        for current_theme in current_themes:
            best_similarity = 0
            for ref_theme in reference_themes:
                similarity = len(set(current_theme.split()) & set(ref_theme.split())) / max(
                    len(set(current_theme.split()) | set(ref_theme.split())), 1
                )
                best_similarity = max(best_similarity, similarity)
            theme_similarities.append(best_similarity)
        
        theme_similarity = sum(theme_similarities) / max(len(theme_similarities), 1)
        
        # Structure consistency (trend count similarity)
        count_diff = abs(len(current_trends) - len(reference_trends))
        max_count = max(len(current_trends), len(reference_trends), 1)
        structure_consistency = 1.0 - (count_diff / max_count)
        
        # Overall weighted score
        overall_score = (
            name_overlap * 0.4 +           # Name matching is important
            theme_similarity * 0.4 +       # Theme similarity is important  
            structure_consistency * 0.2    # Structure is less critical
        )
        
        return {
            'overall_score': round(overall_score, 3),
            'name_overlap': round(name_overlap, 3),
            'theme_similarity': round(theme_similarity, 3),
            'structure_consistency': round(structure_consistency, 3),
            'trend_count_current': len(current_trends),
            'trend_count_reference': len(reference_trends)
        }
    
    @staticmethod
    async def monitor_analysis_consistency(
        topic: str,
        current_analysis: Dict[str, Any],
        db: Database,
        comparison_window_days: int = 7
    ) -> Dict[str, Any]:
        """Monitor consistency of analyses over time."""
        
        try:
            # Get recent analyses for comparison
            cutoff_date = (datetime.now() - timedelta(days=comparison_window_days)).isoformat()
            
            query = """
            SELECT version_data, created_at, cache_metadata
            FROM analysis_versions_v2 
            WHERE topic = ? AND created_at >= ?
            ORDER BY created_at DESC 
            LIMIT 10
            """
            
            historical_results = db.fetch_all(query, (topic, cutoff_date))
            
            if len(historical_results) < 2:
                return {'status': 'insufficient_data', 'message': 'Need at least 2 analyses for comparison'}
            
            # Extract trends from current analysis
            current_all_trends = []
            strategic_recs = current_analysis.get('strategic_recommendations', {})
            for timeframe in ['near_term', 'mid_term', 'long_term']:
                if timeframe in strategic_recs:
                    current_all_trends.extend(strategic_recs[timeframe].get('trends', []))
            
            # Compare with historical analyses
            consistency_scores = []
            for result in historical_results[1:]:  # Skip first (most recent)
                historical_data = json.loads(result[0])
                historical_trends = []
                
                hist_strategic_recs = historical_data.get('strategic_recommendations', {})
                for timeframe in ['near_term', 'mid_term', 'long_term']:
                    if timeframe in hist_strategic_recs:
                        historical_trends.extend(hist_strategic_recs[timeframe].get('trends', []))
                
                score = ConsistencyAnalyzer.calculate_trend_consistency_score(
                    current_all_trends, historical_trends
                )
                score['comparison_date'] = result[1]
                consistency_scores.append(score)
            
            # Calculate aggregate metrics
            if consistency_scores:
                avg_consistency = sum(score['overall_score'] for score in consistency_scores) / len(consistency_scores)
                
                # Store consistency metrics
                await ConsistencyAnalyzer._store_consistency_metrics(
                    topic, avg_consistency, consistency_scores, db
                )
                
                return {
                    'status': 'success',
                    'average_consistency': round(avg_consistency, 3),
                    'consistency_trend': 'improving' if len(consistency_scores) > 1 and 
                                       consistency_scores[0]['overall_score'] > consistency_scores[-1]['overall_score'] else 'stable',
                    'comparison_count': len(consistency_scores),
                    'detailed_scores': consistency_scores
                }
            else:
                return {'status': 'no_comparisons', 'message': 'No valid comparisons found'}
                
        except Exception as e:
            logger.error(f"Error monitoring consistency for {topic}: {e}")
            return {'status': 'error', 'message': str(e)}
    
    @staticmethod
    async def _store_consistency_metrics(
        topic: str, 
        avg_consistency: float, 
        detailed_scores: List[Dict],
        db: Database
    ):
        """Store consistency metrics for tracking over time."""
        
        # Ensure consistency metrics table exists
        create_table_query = """
        CREATE TABLE IF NOT EXISTS trend_consistency_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            consistency_score REAL NOT NULL,
            comparison_count INTEGER,
            detailed_metrics TEXT,
            analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        db.execute(create_table_query)
        
        # Insert metrics
        insert_query = """
        INSERT INTO trend_consistency_metrics 
        (topic, consistency_score, comparison_count, detailed_metrics)
        VALUES (?, ?, ?, ?)
        """
        
        db.execute(insert_query, (
            topic,
            avg_consistency,
            len(detailed_scores),
            json.dumps(detailed_scores)
        ))
```

#### 3.2 Testing Framework

```python
class ConsistencyTestSuite:
    """Test suite for validating analysis consistency improvements."""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def run_consistency_test(
        self,
        topic: str,
        test_parameters: Dict[str, Any],
        num_runs: int = 5
    ) -> Dict[str, Any]:
        """
        Run multiple analyses with identical parameters to test consistency.
        
        This test helps validate that our consistency improvements are working.
        """
        
        results = []
        consistency_scores = []
        
        logger.info(f"Starting consistency test for {topic} with {num_runs} runs")
        
        for run_num in range(num_runs):
            logger.info(f"Test run {run_num + 1}/{num_runs}")
            
            # Generate analysis with test parameters
            # Note: We disable caching for this test to ensure fresh generation
            test_params = test_parameters.copy()
            test_params['enable_caching'] = False
            test_params['_test_run'] = run_num
            
            try:
                # Here you would call your actual analysis function
                # analysis_result = await generate_trend_convergence(**test_params)
                # For now, we'll create a placeholder
                analysis_result = await self._simulate_analysis(test_params)
                results.append(analysis_result)
                
            except Exception as e:
                logger.error(f"Test run {run_num + 1} failed: {e}")
                results.append({'error': str(e), 'run': run_num})
        
        # Calculate consistency between all pairs
        successful_results = [r for r in results if 'error' not in r]
        
        if len(successful_results) < 2:
            return {
                'status': 'failed',
                'message': f'Only {len(successful_results)} successful runs out of {num_runs}',
                'results': results
            }
        
        # Compare each result with the first one as reference
        reference_result = successful_results[0]
        reference_trends = self._extract_all_trends(reference_result)
        
        for i, result in enumerate(successful_results[1:], 1):
            result_trends = self._extract_all_trends(result)
            score = ConsistencyAnalyzer.calculate_trend_consistency_score(
                result_trends, reference_trends
            )
            score['run_comparison'] = f"run_1_vs_run_{i+1}"
            consistency_scores.append(score)
        
        # Calculate overall metrics
        avg_consistency = sum(score['overall_score'] for score in consistency_scores) / len(consistency_scores)
        min_consistency = min(score['overall_score'] for score in consistency_scores)
        max_consistency = max(score['overall_score'] for score in consistency_scores)
        
        # Determine test outcome
        test_passed = avg_consistency >= 0.8  # 80% consistency threshold
        
        return {
            'status': 'passed' if test_passed else 'failed',
            'test_parameters': test_parameters,
            'num_runs': num_runs,
            'successful_runs': len(successful_results),
            'average_consistency': round(avg_consistency, 3),
            'min_consistency': round(min_consistency, 3),
            'max_consistency': round(max_consistency, 3),
            'consistency_variance': round(max_consistency - min_consistency, 3),
            'detailed_scores': consistency_scores,
            'recommendation': self._get_test_recommendation(avg_consistency, max_consistency - min_consistency)
        }
    
    def _extract_all_trends(self, analysis_result: Dict[str, Any]) -> List[Dict]:
        """Extract all trends from an analysis result."""
        all_trends = []
        strategic_recs = analysis_result.get('strategic_recommendations', {})
        
        for timeframe in ['near_term', 'mid_term', 'long_term']:
            if timeframe in strategic_recs:
                all_trends.extend(strategic_recs[timeframe].get('trends', []))
        
        return all_trends
    
    def _get_test_recommendation(self, avg_consistency: float, variance: float) -> str:
        """Get recommendation based on test results."""
        
        if avg_consistency >= 0.9 and variance <= 0.1:
            return "Excellent consistency. System is performing optimally."
        elif avg_consistency >= 0.8 and variance <= 0.2:
            return "Good consistency. Minor variations are acceptable."
        elif avg_consistency >= 0.7:
            return "Moderate consistency. Consider using DETERMINISTIC mode for critical analyses."
        elif avg_consistency >= 0.5:
            return "Low consistency. Review article selection and prompt engineering."
        else:
            return "Poor consistency. Significant improvements needed in algorithm."
    
    async def _simulate_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate analysis for testing purposes."""
        # This would be replaced with actual analysis call in implementation
        return {
            'topic': params.get('topic', 'test_topic'),
            'strategic_recommendations': {
                'near_term': {
                    'trends': [
                        {'name': 'Test Trend 1', 'description': 'Test description 1'},
                        {'name': 'Test Trend 2', 'description': 'Test description 2'},
                    ]
                }
            },
            'generated_at': datetime.now().isoformat(),
            'test_run': params.get('_test_run', 0)
        }
```

### Phase 4: User Interface Enhancements (Week 4)

#### 4.1 Frontend Consistency Controls

Add to `templates/trend_convergence.html`:

```html
<!-- Add to configuration modal -->
<div class="mb-3">
    <label for="consistencyMode" class="form-label">Analysis Consistency</label>
    <select class="form-select" id="consistencyMode">
        <option value="deterministic">🎯 Deterministic - Maximum consistency, identical results</option>
        <option value="low_variance">🎲 Low Variance - High consistency with minor variations</option>
        <option value="balanced" selected>⚖️ Balanced - Good mix of consistency and insights</option>
        <option value="creative">🌟 Creative - Maximum variation and fresh perspectives</option>
    </select>
    <div class="form-text">
        <small class="text-muted">
            Choose based on your needs: <strong>Deterministic</strong> for reports, 
            <strong>Creative</strong> for brainstorming, <strong>Balanced</strong> for general use.
        </small>
    </div>
</div>

<div class="mb-3">
    <div class="form-check form-switch">
        <input class="form-check-input" type="checkbox" id="enableCaching" checked>
        <label class="form-check-label" for="enableCaching">
            Enable Result Caching
        </label>
    </div>
    <div class="form-text">
        <small class="text-muted">
            Cache results to improve response time and ensure consistency for identical parameters.
        </small>
    </div>
</div>

<!-- Add consistency indicator -->
<div class="consistency-indicator" id="consistencyIndicator" style="display: none;">
    <div class="alert alert-info">
        <i class="fas fa-info-circle me-2"></i>
        <strong>Consistency Info:</strong>
        <span id="consistencyMessage"></span>
    </div>
</div>
```

Add JavaScript functions:

```javascript
// Update loadTrendConvergenceAnalysis function
async function loadTrendConvergenceAnalysis() {
    // ... existing code ...
    
    const consistencyMode = document.getElementById('consistencyMode').value;
    const enableCaching = document.getElementById('enableCaching').checked;
    
    // Build request parameters
    const params = new URLSearchParams({
        timeframe_days: actualTimeframe,
        model: model,
        analysis_depth: analysisDepth,
        sample_size_mode: sampleSizeMode,
        consistency_mode: consistencyMode,
        enable_caching: enableCaching,
        cache_duration_hours: 24
    });
    
    // Show consistency indicator
    showConsistencyInfo(consistencyMode, enableCaching);
    
    // ... rest of existing code ...
}

function showConsistencyInfo(mode, cachingEnabled) {
    const indicator = document.getElementById('consistencyIndicator');
    const message = document.getElementById('consistencyMessage');
    
    let infoText = '';
    switch(mode) {
        case 'deterministic':
            infoText = 'Using deterministic mode - results will be identical for same parameters.';
            break;
        case 'low_variance':
            infoText = 'Using low variance mode - results will be highly consistent with minor variations.';
            break;
        case 'balanced':
            infoText = 'Using balanced mode - good mix of consistency and fresh insights.';
            break;
        case 'creative':
            infoText = 'Using creative mode - results may vary significantly between runs.';
            break;
    }
    
    if (cachingEnabled) {
        infoText += ' Caching enabled for faster repeated queries.';
    }
    
    message.textContent = infoText;
    indicator.style.display = 'block';
    
    // Hide after 5 seconds
    setTimeout(() => {
        indicator.style.display = 'none';
    }, 5000);
}

// Add to configuration saving
function saveConfigurationAndClose() {
    // ... existing code ...
    const consistencyMode = document.getElementById('consistencyMode').value;
    const enableCaching = document.getElementById('enableCaching').checked;
    
    const config = {
        // ... existing config ...
        consistencyMode: consistencyMode,
        enableCaching: enableCaching,
        timestamp: new Date().toISOString()
    };
    
    // ... rest of existing code ...
}
```

### Phase 5: Deployment and Monitoring (Week 5)

#### 5.1 Database Migration Script

```python
# scripts/migrate_consistency_features.py

"""
Migration script to add consistency features to existing database.
"""

import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def migrate_database(db_path: str):
    """Run all necessary migrations for consistency features."""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Create new analysis versions table with cache support
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_versions_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key TEXT UNIQUE NOT NULL,
            topic TEXT NOT NULL,
            version_data TEXT NOT NULL,
            cache_metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create indexes
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cache_key_created 
        ON analysis_versions_v2(cache_key, created_at DESC)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_topic_created 
        ON analysis_versions_v2(topic, created_at DESC)
        """)
        
        # Create consistency metrics table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trend_consistency_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            consistency_score REAL NOT NULL,
            comparison_count INTEGER,
            detailed_metrics TEXT,
            analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create index for consistency metrics
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_consistency_topic_date 
        ON trend_consistency_metrics(topic, analysis_date DESC)
        """)
        
        # Migrate existing data if needed
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='analysis_versions'")
        if cursor.fetchone()[0] > 0:
            logger.info("Migrating existing analysis versions...")
            
            cursor.execute("""
            INSERT OR IGNORE INTO analysis_versions_v2 (cache_key, topic, version_data, created_at)
            SELECT 
                'legacy_' || SUBSTR(HEX(RANDOMBLOB(8)), 1, 16) as cache_key,
                topic,
                version_data,
                created_at
            FROM analysis_versions
            WHERE created_at >= date('now', '-30 days')
            """)
            
            migrated = cursor.rowcount
            logger.info(f"Migrated {migrated} existing analysis versions")
        
        conn.commit()
        logger.info("Database migration completed successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print("Usage: python migrate_consistency_features.py <database_path>")
        sys.exit(1)
    
    migrate_database(sys.argv[1])
```

#### 5.2 Monitoring Dashboard

```python
# app/routes/consistency_monitoring_routes.py

from fastapi import APIRouter, Depends, Query
from app.database import Database, get_database_instance
from app.security.session import verify_session
import json
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/api/consistency/metrics/{topic}")
async def get_consistency_metrics(
    topic: str,
    days_back: int = Query(30, description="Days of metrics to retrieve"),
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """Get consistency metrics for a topic over time."""
    
    cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
    
    query = """
    SELECT consistency_score, comparison_count, analysis_date, detailed_metrics
    FROM trend_consistency_metrics 
    WHERE topic = ? AND analysis_date >= ?
    ORDER BY analysis_date DESC
    """
    
    results = db.fetch_all(query, (topic, cutoff_date))
    
    metrics = []
    for result in results:
        metric = {
            'consistency_score': result[0],
            'comparison_count': result[1],
            'analysis_date': result[2],
            'detailed_metrics': json.loads(result[3]) if result[3] else {}
        }
        metrics.append(metric)
    
    # Calculate summary statistics
    if metrics:
        scores = [m['consistency_score'] for m in metrics]
        summary = {
            'average_consistency': sum(scores) / len(scores),
            'min_consistency': min(scores),
            'max_consistency': max(scores),
            'trend': 'improving' if len(scores) > 1 and scores[0] > scores[-1] else 'stable',
            'total_analyses': len(metrics)
        }
    else:
        summary = {
            'average_consistency': 0,
            'min_consistency': 0,
            'max_consistency': 0,
            'trend': 'no_data',
            'total_analyses': 0
        }
    
    return {
        'topic': topic,
        'period_days': days_back,
        'summary': summary,
        'metrics': metrics[:20]  # Limit to recent 20 entries
    }

@router.get("/api/consistency/cache-stats")
async def get_cache_statistics(
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """Get cache performance statistics."""
    
    # Cache hit rate over last 24 hours
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    
    query = """
    SELECT 
        COUNT(*) as total_entries,
        COUNT(CASE WHEN accessed_at > ? THEN 1 END) as recent_accesses,
        AVG(julianday('now') - julianday(created_at)) * 24 as avg_age_hours
    FROM analysis_versions_v2
    """
    
    result = db.fetch_one(query, (yesterday,))
    
    return {
        'total_cached_analyses': result[0] if result else 0,
        'recent_cache_hits': result[1] if result else 0,
        'average_cache_age_hours': round(result[2], 2) if result and result[2] else 0,
        'cache_efficiency': 'high' if result and result[1] > result[0] * 0.3 else 'normal'
    }
```

## Implementation Timeline

### Week 1: Foundation
- [ ] Implement ConsistencyMode enum and basic infrastructure
- [ ] Create deterministic article selection function
- [ ] Add consistency-aware AI interface wrapper
- [ ] Basic testing of deterministic mode

### Week 2: Caching System
- [ ] Implement comprehensive cache key generation
- [ ] Create enhanced caching system with metadata
- [ ] Database migration for new cache tables
- [ ] Test cache hit/miss behavior

### Week 3: Quality Assurance
- [ ] Implement ConsistencyAnalyzer class
- [ ] Create consistency scoring algorithms
- [ ] Build automated testing framework
- [ ] Run initial consistency tests

### Week 4: User Interface
- [ ] Add consistency controls to frontend
- [ ] Implement consistency indicators
- [ ] Create monitoring dashboard
- [ ] User documentation and help text

### Week 5: Deployment & Monitoring
- [ ] Deploy to production with feature flags
- [ ] Set up monitoring and alerting
- [ ] Run comprehensive tests
- [ ] Performance optimization

## Success Metrics

### Primary Metrics
- **Consistency Score**: Target ≥80% for balanced mode, ≥95% for deterministic mode
- **Cache Hit Rate**: Target ≥60% for repeated queries
- **Response Time**: No degradation from current performance
- **User Satisfaction**: Reduced complaints about inconsistent results

### Secondary Metrics
- **Algorithm Stability**: Less than 5% variance in trend identification
- **Cache Efficiency**: Reduced API calls to AI models by ≥40%
- **Error Rate**: No increase in analysis failures
- **Resource Usage**: Minimal impact on system resources

## Risk Mitigation

### Technical Risks
- **Performance Impact**: Implement caching and optimize algorithms
- **Storage Growth**: Automated cache cleanup and size limits
- **Backwards Compatibility**: Extensive testing with existing data

### User Experience Risks
- **Complexity**: Provide sensible defaults and clear explanations
- **Learning Curve**: Comprehensive documentation and examples
- **Feature Adoption**: Gradual rollout with user feedback

## Conclusion

This implementation plan provides a comprehensive approach to improving analysis consistency while maintaining backwards compatibility. The phased approach allows for gradual implementation and testing, reducing risk while delivering immediate value to users.

The key innovation is maintaining full backwards compatibility with the existing auspex service while adding consistency features through wrapper functions and enhanced caching. This ensures existing functionality continues to work while new consistency features are available for users who need them.