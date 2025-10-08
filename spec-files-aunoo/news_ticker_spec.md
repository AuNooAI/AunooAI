# News Ticker Specification

## Overview
Add a news ticker component to the top of the Home page that displays recent news headlines from active topics in a scrolling format. On hover, show article summaries in a tooltip/popup.

## Requirements

### Functional Requirements

1. **News Ticker Display**
   - Position at the top of the Home page, below the navigation bar
   - Display recent news headlines from active topics
   - Continuous horizontal scrolling animation
   - Pause scrolling on hover
   - Resume scrolling when mouse leaves

2. **Data Source**
   - Fetch articles from active topics (same as current home page logic)
   - Prioritize articles from the last 24-48 hours
   - Limit to 20-30 most recent articles
   - Filter out spam/low-quality content (same filters as news feed)

3. **Hover Interaction**
   - Show article summary in a tooltip/popup on hover
   - Include article metadata (source, publication date, topic)
   - Click to open full article or navigate to news feed

4. **Responsive Design**
   - Adapt to different screen sizes
   - Maintain readability on mobile devices
   - Graceful degradation if JavaScript is disabled

### Technical Requirements

1. **Backend API**
   - Create new endpoint: `GET /api/news-ticker`
   - Return recent articles with minimal data (title, summary, url, source, date, topic)
   - Cache results for 5-10 minutes to reduce database load
   - Use existing article filtering logic from news feed service

2. **Frontend Implementation**
   - Add ticker component to `templates/index.html`
   - Use CSS animations for smooth scrolling
   - JavaScript for hover interactions and API calls
   - Integrate with existing design system (colors, fonts, spacing)

3. **Performance**
   - Lazy load ticker content after page load
   - Optimize for fast rendering
   - Minimize API calls with caching
   - Progressive enhancement approach

## Implementation Plan

### Phase 1: Backend API
1. Create news ticker service
2. Add API endpoint
3. Implement caching mechanism
4. Add error handling

### Phase 2: Frontend Component
1. Create ticker HTML structure
2. Add CSS animations and styling
3. Implement JavaScript interactions
4. Add responsive design

### Phase 3: Integration
1. Integrate with home page
2. Test across devices
3. Performance optimization
4. User experience refinement

## API Specification

### Endpoint: `GET /api/news-ticker`

**Query Parameters:**
- `limit` (optional): Number of articles to return (default: 25, max: 50)
- `hours` (optional): Days back to look for articles (default: 2, max: 30)

**Response Format:**
```json
{
  "articles": [
    {
      "title": "Article headline",
      "summary": "Brief article summary",
      "url": "https://example.com/article",
      "source": "News Source Name",
      "publication_date": "2024-01-15T10:30:00Z",
      "topic": "Topic Name",
      "sentiment": "positive|negative|neutral"
    }
  ],
  "total_count": 25,
  "last_updated": "2024-01-15T12:00:00Z"
}
```

## UI/UX Design

### Visual Design
- **Position**: Fixed at top of page, below navigation
- **Height**: 40-50px
- **Background**: Light gray (#f8f9fa) with subtle border
- **Text**: Electric Pink with primary color accents
- **Animation**: Smooth left-to-right scrolling at 30-50px/second

### Interaction Design
- **Hover**: Pause animation, show tooltip with summary
- **Click**: Navigate to full article or news feed
- **Mobile**: Touch-friendly with swipe gestures
- **Accessibility**: Keyboard navigation support

### Content Display
- **Format**: "Headline | Source | Time ago"
- **Separator**: Use bullet points or vertical bars
- **Truncation**: Limit headline length to prevent overflow
- **Updates**: Refresh content every 5-10 minutes

## Error Handling

1. **API Failures**
   - Show fallback message if API unavailable
   - Retry mechanism with exponential backoff
   - Graceful degradation to static content

2. **Empty Results**
   - Display "No recent news available" message
   - Provide link to news feed or topic creation

3. **Network Issues**
   - Cache last successful response
   - Show cached content with "last updated" timestamp
   - Indicate when content is stale

## Security Considerations

1. **Input Validation**
   - Sanitize article titles and summaries
   - Validate URLs before display
   - Prevent XSS attacks in tooltips

2. **Rate Limiting**
   - Implement API rate limiting
   - Prevent abuse of ticker endpoint
   - Monitor for unusual request patterns

## Testing Requirements

1. **Unit Tests**
   - API endpoint functionality
   - Data filtering and formatting
   - Error handling scenarios

2. **Integration Tests**
   - End-to-end ticker functionality
   - API integration with frontend
   - Caching behavior

3. **UI Tests**
   - Scrolling animation performance
   - Hover interactions
   - Responsive design
   - Cross-browser compatibility


## Dependencies

- Existing news feed service and database
- Current home page template structure
- Bootstrap CSS framework
- Font Awesome icons
- Existing authentication system


## Implementation Notes

- Use existing `DatabaseQueryFacade` for article queries
- Leverage current spam filtering logic from news feed
- Follow established patterns for API endpoints
- Maintain consistency with existing UI components
- Consider using WebSocket for real-time updates in future
- Implement progressive enhancement for better performance
