# Evidence-Based Forecast Chart Generation for Auspex

## Overview

This module adds advanced forecast chart generation capabilities to Auspex, creating visual representations of consensus bands and outlier scenarios based on analyzed articles and their categories/clusters.

## Features

### 📊 Chart Components

- **Consensus Bands**: Visual representations of agreed timing and sentiment across analyzed articles
- **Outlier Markers**: Highlighting dissenting views and potential black swan scenarios
- **Category Analysis**: Based on actual article clustering and categorization
- **Timeline Visualization**: Forecast horizon from 2024 to 2035+

### 🎨 Chart Types

- **Consensus Bands** show different types of agreement:
  - Positive Growth Consensus (Green)
  - Mixed/AGI Consensus (Yellow)
  - Regulatory/Critical Consensus (Light Red)
  - Safety/Security Consensus (Red)
  - Warfare/Defense Consensus (Coral)
  - Geopolitical Consensus (Blue)
  - Business Automation (Light Yellow)
  - Societal Impact (Orange)

- **Outlier Markers** highlight:
  - Optimistic Outliers (Red circles above consensus)
  - Pessimistic Outliers (Blue circles below consensus)

## Files Created

### Core Service
- `app/services/forecast_chart_service.py` - Main chart generation service
- `app/schemas/forecast_chart.py` - Pydantic schemas for data validation
- `app/routes/forecast_chart_routes.py` - API routes and web interface
- `templates/forecast_chart.html` - Web interface for chart generation

### Integration
- Updated `app/core/routers.py` to register new routes

## API Endpoints

### Generate Chart
```
GET /api/forecast-charts/generate/{topic}
```

**Parameters:**
- `topic` (required): Topic to analyze
- `timeframe` (optional): Days of data to analyze (default: 365)
- `title_prefix` (optional): Chart title prefix (default: "AI & Machine Learning")

**Response:**
```json
{
  "success": true,
  "chart_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "topic": "artificial_intelligence",
  "timeframe": "365",
  "message": "Forecast chart generated successfully"
}
```

### Available Topics
```
GET /api/forecast-charts/topics
```

Returns list of available topics for analysis.

### Web Interface
```
GET /forecast-chart
```

Serves the interactive web interface for chart generation.

## Usage

### Web Interface
1. Navigate to `/forecast-chart` in your browser
2. Select a topic from the dropdown
3. Choose timeframe and title prefix
4. Click "Generate Forecast Chart"
5. Download the generated chart if needed

### API Usage
```python
import requests

# Generate a chart
response = requests.get(
    "/api/forecast-charts/generate/artificial_intelligence",
    params={
        "timeframe": "365",
        "title_prefix": "AI & Machine Learning"
    }
)

chart_data = response.json()
if chart_data["success"]:
    # chart_data["chart_data"] contains base64 encoded PNG
    print(f"Chart generated for {chart_data['topic']}")
```

### Programmatic Usage
```python
from app.services.forecast_chart_service import get_forecast_chart_service

service = get_forecast_chart_service()
chart_base64 = await service.generate_evidence_based_forecast_chart(
    topic="artificial_intelligence",
    timeframe="365",
    title_prefix="AI & Machine Learning"
)
```

## How It Works

### Data Analysis Process

1. **Category Extraction**: Retrieves categories for the specified topic from the database
2. **Sentiment Analysis**: Analyzes sentiment distribution across articles in each category
3. **Time Impact Analysis**: Evaluates time-to-impact predictions for each category
4. **Consensus Detection**: Identifies consensus timing and sentiment patterns
5. **Outlier Identification**: Detects extreme viewpoints and potential scenarios

### Chart Generation

1. **Timeline Mapping**: Maps time-to-impact data to year indices (2024-2035+)
2. **Consensus Band Creation**: Generates colored bands showing consensus timing
3. **Outlier Placement**: Positions outlier markers based on extreme sentiments
4. **Styling**: Applies colors, legends, and annotations based on category analysis

### Color Coding Logic

- **Regulatory/Policy Categories**: Light red (regulatory response)
- **Safety/Security Categories**: Red (safety/security consensus)
- **Business/Industry Categories**: Light yellow (business automation)
- **Geopolitical Categories**: Blue (geopolitical competition)
- **High Positive Sentiment**: Green (positive growth consensus)
- **High Negative Sentiment**: Light red (critical consensus)
- **Mixed/Default**: Yellow (mixed consensus)

## Dependencies

- `matplotlib` - Chart generation
- `numpy` - Numerical operations
- `fastapi` - API framework
- `pydantic` - Data validation
- `jinja2` - Template rendering

## Integration with Auspex

The forecast chart service integrates with:
- **AnalyzeDB**: For retrieving sentiment, category, and time-to-impact data
- **Database**: For accessing analyzed articles and their metadata
- **Existing Router System**: For seamless integration with current routes

## Customization

### Adding New Consensus Types
Edit `consensus_colors` in `ForecastChartService` to add new consensus types:

```python
self.consensus_colors = {
    'new_consensus_type': '#hex_color',
    # ... existing colors
}
```

### Modifying Outlier Detection
Update `_identify_outliers()` method to change outlier detection logic:

```python
def _identify_outliers(self, theme_index, category, sentiment_data):
    # Custom outlier detection logic
    outliers = []
    # ... your logic here
    return outliers
```

### Chart Styling
Modify `_create_forecast_chart()` to adjust:
- Figure size and layout
- Color schemes
- Font sizes and styles
- Legend positioning
- Grid and axis styling

## Error Handling

The service includes comprehensive error handling:
- Empty data scenarios
- Invalid topics
- Database connection issues
- Chart generation failures

Charts gracefully degrade to show placeholder content when data is unavailable.

## Performance Considerations

- Chart generation is optimized for topics with up to 8 categories
- Image generation uses efficient PNG encoding
- Database queries are optimized for performance
- Memory usage is managed through proper matplotlib cleanup

## Future Enhancements

Potential improvements:
- Interactive charts using Plotly
- Additional chart types (scatter plots, heatmaps)
- Export to multiple formats (SVG, PDF)
- Caching for frequently requested charts
- Real-time updates based on new article analysis 