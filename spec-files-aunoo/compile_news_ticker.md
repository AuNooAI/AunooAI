# News Ticker Implementation Guide

## Overview
This guide provides step-by-step instructions for implementing the news ticker feature as specified in `news_ticker_spec.md`.

## Implementation Steps

### Step 1: Backend API Implementation

#### 1.1 Create News Ticker Service
Create `app/services/news_ticker_service.py`:

```python
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from app.database import Database
from app.database_query_facade import DatabaseQueryFacade

logger = logging.getLogger(__name__)

class NewsTickerService:
    def __init__(self, db: Database):
        self.db = db
        self.facade = DatabaseQueryFacade(db, logger)
    
    async def get_ticker_articles(self, limit: int = 25, hours: int = 48) -> List[Dict[str, Any]]:
        """Get recent articles for news ticker"""
        # Implementation details in spec
        pass
```

#### 1.2 Add API Endpoint
Add to `app/routes/news_feed_routes.py`:

```python
@router.get("/news-ticker")
async def get_news_ticker(
    limit: int = Query(25, ge=1, le=50),
    hours: int = Query(48, ge=1, le=168),
    db: Database = Depends(get_database_instance)
):
    """Get recent articles for news ticker"""
    # Implementation details in spec
    pass
```

#### 1.3 Implement Caching
Use Redis or in-memory caching for 5-10 minute intervals.

### Step 2: Frontend Component

#### 2.1 Add HTML Structure
Add to `templates/index.html` after the navigation bar:

```html
<!-- News Ticker -->
<div id="news-ticker" class="news-ticker">
    <div class="ticker-content">
        <div class="ticker-items" id="ticker-items">
            <!-- Articles will be loaded here -->
        </div>
    </div>
</div>
```

#### 2.2 Add CSS Styling
Add to `templates/index.html` in the `{% block extra_css %}` section:

```css
/* News Ticker Styles */
.news-ticker {
    position: fixed;
    top: 60px; /* Below navigation */
    left: 0;
    right: 0;
    height: 40px;
    background: #f8f9fa;
    border-bottom: 1px solid #e9ecef;
    overflow: hidden;
    z-index: 1000;
}

.ticker-content {
    height: 100%;
    display: flex;
    align-items: center;
}

.ticker-items {
    display: flex;
    animation: scroll-left 60s linear infinite;
    white-space: nowrap;
}

.ticker-item {
    display: inline-flex;
    align-items: center;
    margin-right: 30px;
    color: #333;
    text-decoration: none;
    font-size: 14px;
    transition: color 0.2s ease;
}

.ticker-item:hover {
    color: var(--primary-color);
}

.ticker-separator {
    margin: 0 15px;
    color: #6c757d;
}

@keyframes scroll-left {
    0% { transform: translateX(100%); }
    100% { transform: translateX(-100%); }
}

.news-ticker:hover .ticker-items {
    animation-play-state: paused;
}
```

#### 2.3 Add JavaScript Functionality
Add to `templates/index.html` in the `{% block extra_js %}` section:

```javascript
class NewsTicker {
    constructor() {
        this.tickerElement = document.getElementById('news-ticker');
        this.tickerItems = document.getElementById('ticker-items');
        this.articles = [];
        this.init();
    }
    
    async init() {
        await this.loadArticles();
        this.renderTicker();
        this.setupEventListeners();
    }
    
    async loadArticles() {
        try {
            const response = await fetch('/api/news-feed/news-ticker');
            const data = await response.json();
            this.articles = data.articles || [];
        } catch (error) {
            console.error('Error loading ticker articles:', error);
            this.articles = [];
        }
    }
    
    renderTicker() {
        if (this.articles.length === 0) {
            this.tickerItems.innerHTML = '<span class="ticker-item">No recent news available</span>';
            return;
        }
        
        const items = this.articles.map(article => {
            const timeAgo = this.getTimeAgo(article.publication_date);
            return `
                <a href="${article.url}" class="ticker-item" 
                   data-summary="${this.escapeHtml(article.summary)}"
                   data-source="${this.escapeHtml(article.source)}"
                   data-topic="${this.escapeHtml(article.topic)}"
                   target="_blank">
                    ${this.escapeHtml(article.title)}
                    <span class="ticker-separator">•</span>
                    ${this.escapeHtml(article.source)}
                    <span class="ticker-separator">•</span>
                    ${timeAgo}
                </a>
            `;
        }).join('');
        
        this.tickerItems.innerHTML = items;
    }
    
    setupEventListeners() {
        // Add tooltip functionality
        this.tickerItems.addEventListener('mouseenter', (e) => {
            if (e.target.classList.contains('ticker-item')) {
                this.showTooltip(e.target, e);
            }
        }, true);
        
        this.tickerItems.addEventListener('mouseleave', (e) => {
            if (e.target.classList.contains('ticker-item')) {
                this.hideTooltip();
            }
        }, true);
    }
    
    showTooltip(element, event) {
        // Tooltip implementation
    }
    
    hideTooltip() {
        // Hide tooltip
    }
    
    getTimeAgo(dateString) {
        // Time ago calculation
    }
    
    escapeHtml(text) {
        // HTML escaping
    }
}

// Initialize ticker when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new NewsTicker();
});
```

### Step 3: Integration and Testing

#### 3.1 Update Home Page Layout
Adjust the main content container to account for the fixed ticker:

```css
.container {
    margin-top: 40px; /* Space for ticker */
}
```

#### 3.2 Add Error Handling
Implement graceful fallbacks for API failures and empty results.

#### 3.3 Performance Optimization
- Implement lazy loading
- Add request debouncing
- Optimize animations for 60fps

### Step 4: Testing

#### 4.1 Unit Tests
Create `tests/test_news_ticker.py`:

```python
import pytest
from app.services.news_ticker_service import NewsTickerService

def test_get_ticker_articles():
    # Test implementation
    pass
```

#### 4.2 Integration Tests
Test the complete flow from API to frontend display.

#### 4.3 UI Tests
Verify scrolling animation, hover interactions, and responsive design.

## Key Implementation Notes

1. **Database Queries**: Use existing `DatabaseQueryFacade` methods
2. **Filtering**: Apply same spam filters as news feed service
3. **Caching**: Implement 5-10 minute cache for API responses
4. **Performance**: Optimize for smooth 60fps animations
5. **Accessibility**: Ensure keyboard navigation and screen reader support
6. **Responsive**: Test on mobile devices and different screen sizes

## Dependencies

- Existing news feed service
- Database query facade
- Bootstrap CSS framework
- Font Awesome icons
- Current authentication system

## Success Criteria

- ✅ Ticker displays recent articles from active topics
- ✅ Smooth horizontal scrolling animation
- ✅ Hover interactions work correctly
- ✅ Responsive design on all devices
- ✅ API performance meets requirements
- ✅ Error handling provides graceful fallbacks
- ✅ Integration with existing design system
- ✅ All tests pass
- ✅ Documentation updated

## Troubleshooting

### Common Issues

1. **Scrolling Animation Not Smooth**
   - Check CSS animation properties
   - Ensure hardware acceleration is enabled
   - Optimize DOM updates

2. **API Performance Issues**
   - Implement proper caching
   - Optimize database queries
   - Add request debouncing

3. **Mobile Responsiveness**
   - Test on various screen sizes
   - Adjust font sizes and spacing
   - Ensure touch interactions work

4. **Tooltip Positioning**
   - Handle edge cases (screen boundaries)
   - Ensure proper z-index stacking
   - Test on different browsers

## Future Enhancements

- Real-time updates via WebSocket
- User personalization options
- Topic-based color coding
- Breaking news alerts
- Social sharing integration
