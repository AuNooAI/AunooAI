# Topic Map System

This document explains how to use the new Topic Map functionality that creates interactive knowledge graphs from your ingested articles.

## Overview

The Topic Map system analyzes your articles to extract key topics and their relationships, then visualizes them as an interactive network graph similar to mind maps. It uses:

- **TF-IDF analysis** to extract key phrases from articles
- **Hierarchical clustering** to group related topics
- **Network visualization** with D3.js for interactive exploration
- **Your existing SQLite and ChromaDB data**

## Features

### 🧠 Intelligent Topic Extraction
- Automatically extracts key phrases from article content
- Groups related topics using clustering algorithms
- Creates hierarchical relationships between main topics and sub-topics

### 🎨 Interactive Visualization
- Force-directed network graph with D3.js
- Hover for topic details and related terms
- Click and drag nodes to explore relationships
- Zoom and pan for better navigation
- Color-coded nodes by topic clusters

### 🔍 Filtering and Analysis
- Filter by topic or category
- Adjust article limits for analysis
- Real-time statistics and insights
- Export capabilities

## How to Use

### 1. Prerequisites

Make sure you have analyzed articles in your database:
- Run your article analysis pipeline
- Ensure articles have been processed with topics and categories
- Verify data exists in your SQLite `articles` table

### 2. Test the System

Run the test script to verify everything works:

```bash
python scripts/test_topic_map.py
```

This will:
- Check database connectivity
- Test article extraction
- Validate topic hierarchy generation
- Show sample statistics

### 3. Access the Topic Map

#### Via Web Interface
1. Start your FastAPI server
2. Navigate to `/topic-map` in your browser
3. Use the controls to filter and generate maps

#### Via API
Access the API endpoints directly:

```bash
# Generate a topic map
GET /api/topic-map/generate?limit=500&topic_filter=AI&category_filter=Technology

# Get topic statistics
GET /api/topic-map/statistics

# Get details about a specific topic
GET /api/topic-map/topic-details/cluster_0
```

### 4. Interpreting the Visualization

#### Node Types
- **Large colored circles**: Main topics (cluster centers)
- **Smaller lighter circles**: Sub-topics and related terms

#### Node Size
- Proportional to the number of articles containing that topic
- Larger nodes = more articles mention this topic

#### Connections
- Lines between nodes show relationships
- Thicker lines = stronger relationships
- Connected topics appear together in articles

#### Colors
- Each cluster has a consistent color scheme
- Main topics: Saturated colors
- Sub-topics: Lighter variants of the main color

## Technical Details

### Data Flow

1. **Article Extraction**: Queries analyzed articles from SQLite
2. **Text Processing**: Cleans and tokenizes article content
3. **Phrase Extraction**: Uses TF-IDF to find key terms
4. **Clustering**: Groups related phrases using hierarchical clustering
5. **Graph Building**: Creates nodes and edges for visualization
6. **Rendering**: D3.js renders interactive network graph

### Algorithms Used

- **TF-IDF Vectorization**: Extracts meaningful phrases
- **Jaccard Similarity**: Measures topic relationships
- **Agglomerative Clustering**: Groups similar topics
- **Force-directed Layout**: Positions nodes naturally

### Performance Considerations

- **Article Limits**: Start with 100-500 articles for faster processing
- **Clustering Size**: Automatically adjusts cluster count based on data
- **Memory Usage**: Large datasets may require higher limits
- **Processing Time**: Scales with article count and complexity

## Configuration

### Filter Options

```python
# Example API call with filters
{
    "topic_filter": "AI and Machine Learning",
    "category_filter": "Technology", 
    "limit": 500
}
```

### Clustering Parameters

Modify in `TopicMapService`:
- `min_cluster_size`: Minimum articles per cluster (default: 3)
- `max_clusters`: Maximum number of clusters (default: 50)
- `max_phrases`: Phrases extracted per article (default: 20)

## Troubleshooting

### Common Issues

1. **No articles found**
   - Ensure articles are analyzed (`analyzed = 1` in database)
   - Check that articles have content or summaries
   - Verify topic and category filters

2. **Empty topic map**
   - Increase article limit
   - Check that articles contain sufficient text
   - Remove restrictive filters

3. **Poor clustering**
   - Increase minimum cluster size
   - Add more articles to analysis
   - Check article diversity

4. **Performance issues**
   - Reduce article limit
   - Use more specific filters
   - Check server resources

### Debug Steps

1. Run the test script: `python scripts/test_topic_map.py`
2. Check server logs for error messages
3. Verify database connectivity
4. Test with smaller datasets first

## Integration with Existing Features

### Vector Database
- Uses your existing ChromaDB setup
- Leverages OpenAI embeddings if available
- Falls back to TF-IDF for similarity calculations

### Article Analysis
- Works with your current topic categorization
- Integrates with sentiment analysis
- Uses driver type and future signal data

### Dashboard Integration
- Can be embedded in existing dashboards
- Shares authentication and session management
- Uses consistent UI/UX patterns

## Example Use Cases

### Research Analysis
- Map research themes across papers
- Identify knowledge gaps and connections
- Track topic evolution over time

### News Monitoring
- Visualize news topic relationships
- Monitor trending themes
- Analyze sentiment patterns across topics

### Content Strategy
- Identify content clusters
- Find related topic opportunities
- Plan comprehensive coverage

## API Reference

### Generate Topic Map
```
GET /api/topic-map/generate
Parameters:
  - topic_filter (optional): Filter by specific topic
  - category_filter (optional): Filter by category
  - limit (int): Maximum articles to analyze (10-2000)
```

### Get Statistics
```
GET /api/topic-map/statistics
Parameters:
  - topic_filter (optional): Filter by specific topic
  - category_filter (optional): Filter by category
```

### Topic Details
```
GET /api/topic-map/topic-details/{topic_id}
Parameters:
  - topic_id (str): Node ID from the graph
```

## Future Enhancements

### Planned Features
- **Temporal Analysis**: Topic evolution over time
- **Interactive Filtering**: Real-time filter updates
- **Export Options**: Save maps as images/JSON
- **Advanced Clustering**: Multiple algorithm options
- **Semantic Similarity**: Enhanced with vector embeddings

### Customization Options
- **Color Schemes**: Custom cluster colors
- **Layout Algorithms**: Different force simulations
- **Node Styles**: Custom shapes and sizes
- **Interaction Modes**: Different click behaviors

## Support

For issues or questions:
1. Check this README for common solutions
2. Run the test script for debugging
3. Review server logs for detailed errors
4. Check the topic map service logs specifically

The topic map system is designed to provide valuable insights into your document corpus through visual exploration of topic relationships. 