import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict, Counter
from datetime import datetime

# BERTopic imports
from bertopic import BERTopic
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
from bertopic.representation import KeyBERTInspired

# Import vector store functions to leverage OpenAI embeddings
from app.vector_store import _embed_texts, get_vectors_by_metadata

logger = logging.getLogger(__name__)


class TopicMapService:
    """Service for hierarchical topic modeling using BERTopic with OpenAI embeddings."""
    
    def __init__(self, db, vector_store):
        self.db = db
        self.vector_store = vector_store
        
        # Use OpenAI embeddings instead of SentenceTransformers
        self.embedding_model = None  # Will use OpenAI via _embed_texts
        self.topic_model = None
        self.hierarchical_topics = None
        
        # Custom stopwords to filter out metadata terms
        self.custom_stopwords = self._build_custom_stopwords()
        
        logger.info("TopicMapService initialized with OpenAI embeddings")

    def _embed_documents_with_openai(self, documents: List[str]):
        """Use OpenAI embeddings from vector store for consistent semantic analysis."""
        try:
            logger.info(f"Generating OpenAI embeddings for {len(documents)} documents")
            embeddings = _embed_texts(documents)
            logger.info(f"Generated {len(embeddings)} OpenAI embeddings")
            # Convert to numpy array for BERTopic compatibility
            import numpy as np
            return np.array(embeddings, dtype=np.float32)
        except Exception as e:
            logger.error(f"Failed to generate OpenAI embeddings: {e}")
            # Fallback to SentenceTransformers if OpenAI fails
            logger.info("Falling back to SentenceTransformers")
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer('all-MiniLM-L6-v2')
                return model.encode(documents, convert_to_numpy=True)
            except ImportError:
                logger.error("SentenceTransformers not available")
                # Return random embeddings as last resort
                import numpy as np
                return np.random.rand(len(documents), 1536).astype(np.float32)
    
    def _leverage_existing_vectors(self, article_uris: List[str]) -> Optional[List[List[float]]]:
        """Leverage existing OpenAI embeddings from ChromaDB if available."""
        try:
            # Get vectors for the specific articles from ChromaDB
            vectors, metadatas, ids = get_vectors_by_metadata(
                where={"uri": {"$in": article_uris}}
            )
            
            if vectors.size > 0:
                logger.info(f"Retrieved {len(vectors)} existing OpenAI embeddings from ChromaDB")
                # Return as numpy array for BERTopic compatibility
                import numpy as np
                return np.array(vectors, dtype=np.float32)
                
        except Exception as e:
            logger.warning(f"Could not retrieve existing vectors: {e}")
            
        return None

    def _build_custom_stopwords(self) -> set:
        """Build comprehensive stopwords including metadata terms."""
        
        # Start with sklearn's English stopwords
        stopwords = set(ENGLISH_STOP_WORDS)
        
        # Add sentiment-related terms that shouldn't be topics
        sentiment_terms = {
            'positive', 'negative', 'neutral', 'sentiment'
            # Removed: 'good', 'bad', 'excellent', 'poor', 'great', 'terrible', 'amazing', 'awful'
            # These might be meaningful for content analysis
        }
        
        # Add driver type terms
        driver_terms = {
            'driver', 'type', 'economic', 'social', 'technological', 'environmental',
            'political', 'legal', 'regulatory'
            # Removed: 'demographic' - might be meaningful
        }
        
        # Add generic metadata terms
        metadata_terms = {
            'category', 'topic', 'tag', 'tags', 'article', 'title', 'summary',
            'uri', 'url', 'link', 'source', 'date', 'time', 'unknown', 'general'
        }
        
        # Reduced filler terms - kept only the most problematic ones
        filler_terms = {
            'said', 'says', 'according', 'report', 'reports',
            'new', 'news', 'today', 'recently', 'latest'
            # Removed: 'study', 'studies', 'yesterday', 'current' - might be meaningful
        }
        
        # Combine all stopwords
        stopwords.update(sentiment_terms)
        stopwords.update(driver_terms) 
        stopwords.update(metadata_terms)
        stopwords.update(filler_terms)
        
        return stopwords
    
    def extract_topics_from_articles(self, 
                                   limit: Optional[int] = None, 
                                   topic_filter: Optional[str] = None,
                                   category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract articles with their content for hierarchical topic analysis."""
        
        query = """
            SELECT uri, title, summary, topic, category, tags, 
                   sentiment, future_signal, driver_type, time_to_impact,
                   submission_date
            FROM articles 
            WHERE analyzed = 1 
            AND summary IS NOT NULL
            AND summary != ''
            AND LENGTH(summary) > 50
        """
        params = []
        
        if topic_filter:
            query += " AND topic = ?"
            params.append(topic_filter)
            
        if category_filter:
            query += " AND category = ?"
            params.append(category_filter)
            
        query += " ORDER BY submission_date DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
            
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            
        articles = []
        for row in results:
            # Create rich document text for better topic modeling
            text_content = f"{row[1] or ''} {row[2] or ''}".strip()
            
            # Don't add metadata context as it confuses BERTopic - keep text pure
            # Only use the actual article content for semantic modeling
            
            if len(text_content) > 20:  # Only include articles with sufficient content
                articles.append({
                    'uri': row[0],
                    'title': row[1],
                    'summary': row[2],
                    'topic': row[3],
                    'category': row[4],
                    'tags': row[5],
                    'sentiment': row[6],
                    'future_signal': row[7],
                    'driver_type': row[8],
                    'time_to_impact': row[9],
                    'submission_date': row[10],
                    'text': text_content,
                    'enhanced_text': text_content  # Use pure content, not metadata
                })
            
        logger.info(f"Extracted {len(articles)} articles for hierarchical topic analysis")
        return articles

    def build_hierarchical_topic_map(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build 3-layer hierarchical topic map using BERTopic with OpenAI embeddings."""
        
        if len(articles) < 10:
            logger.warning(f"Too few articles ({len(articles)}) for hierarchical modeling")
            return self._create_category_based_hierarchy(articles)
        
        # Extract documents for BERTopic
        documents = [article['enhanced_text'] for article in articles]
        article_uris = [article['uri'] for article in articles]
        
        logger.info(f"Running BERTopic hierarchical modeling on {len(documents)} documents with OpenAI embeddings...")
        
        try:
            # Try to leverage existing OpenAI embeddings from ChromaDB first
            embeddings = self._leverage_existing_vectors(article_uris)
            
            if embeddings is None or len(embeddings) != len(documents):
                logger.info("Existing embeddings not available, generating new OpenAI embeddings")
                embeddings = self._embed_documents_with_openai(documents)
            else:
                logger.info("Using existing OpenAI embeddings from ChromaDB")
            
            # Configure HDBSCAN for hierarchical clustering
            hdbscan_model = HDBSCAN(
                min_cluster_size=max(2, len(documents) // 50),  # More liberal - was // 25
                min_samples=1,  # Reduced from 2
                metric='euclidean',
                cluster_selection_method='eom',
                prediction_data=True
            )
            
            # Use KeyBERTInspired for better topic representations
            representation_model = KeyBERTInspired()
            
            # Configure vectorizer for meaningful phrases
            vectorizer_model = CountVectorizer(
                ngram_range=(1, 2),  # Reduced from (1,3) for more focused topics
                stop_words=list(self.custom_stopwords),  # Convert set to list
                max_features=800,    # Increased from 500 for more vocabulary
                min_df=2,           # Decreased from 3 to include more terms
                max_df=0.8          # Increased from 0.7 to include more common terms
            )
            
            # Create a SentenceTransformer model for BERTopic's internal operations
            # This allows KeyBERTInspired to work, but we'll still use OpenAI embeddings for clustering
            try:
                from sentence_transformers import SentenceTransformer
                internal_embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Using SentenceTransformer for BERTopic internal operations")
            except ImportError:
                logger.warning("SentenceTransformers not available, using simpler representation")
                representation_model = None  # Fall back to default representation
                internal_embedding_model = None
            
            # Initialize BERTopic with embedding model for internal use but use OpenAI embeddings for clustering
            topic_model = BERTopic(
                embedding_model=internal_embedding_model,  # For internal BERTopic operations
                hdbscan_model=hdbscan_model,
                vectorizer_model=vectorizer_model,
                representation_model=representation_model,
                nr_topics="auto",
                verbose=True  # Enable verbose logging to see what's happening
            )
            
            logger.info("Fitting BERTopic model with OpenAI embeddings...")
            # Fit the model using pre-computed OpenAI embeddings (this overrides the internal model)
            topics, probabilities = topic_model.fit_transform(documents, embeddings)
            
            logger.info(f"BERTopic completed. Topics found: {len(set(topics))}")
            logger.info(f"Topic distribution: {Counter(topics)}")
            
            # Check if BERTopic actually found meaningful topics
            unique_topics = [t for t in set(topics) if t != -1]
            if len(unique_topics) < 2:
                logger.warning("BERTopic found too few topics, falling back to category-based hierarchy")
                return self._create_category_based_hierarchy(articles)
            
            # Generate hierarchical topics - this is the key for 3-layer structure!
            logger.info("Generating hierarchical topic structure...")
            hierarchical_topics = topic_model.hierarchical_topics(documents)
            
            logger.info(f"Generated {len(unique_topics)} base topics and hierarchical structure")
            
            # Build 3-layer visualization structure
            result = self._build_three_layer_structure(
                articles, topic_model, topics, hierarchical_topics
            )
            
            # Add metadata about using OpenAI embeddings
            result['metadata']['embedding_model'] = 'OpenAI text-embedding-3-small'
            result['metadata']['embedding_dimensions'] = 1536
            result['metadata']['internal_model'] = 'SentenceTransformer all-MiniLM-L6-v2'
            
            # Log the results for debugging
            logger.info(f"Final structure: {len(result.get('nodes', []))} nodes, {len(result.get('edges', []))} edges")
            node_types = Counter([n.get('type') for n in result.get('nodes', [])])
            logger.info(f"Node types: {dict(node_types)}")
            
            return result
            
        except Exception as e:
            logger.error(f"BERTopic hierarchical modeling failed: {e}", exc_info=True)
            logger.info("Falling back to category-based hierarchy")
            return self._create_category_based_hierarchy(articles)
    
    def _build_three_layer_structure(self, articles: List[Dict[str, Any]], 
                                   topic_model: BERTopic, topics: List[int], 
                                   hierarchical_topics) -> Dict[str, Any]:
        """Build the 3-layer structure: Categories -> Topics -> Subtopics."""
        
        nodes = []
        edges = []
        clusters = []
        
        # Layer 1: Create main category nodes (like "Setting", "Characters", etc.)
        category_groups = defaultdict(list)
        for i, article in enumerate(articles):
            category = article.get('category', 'General')
            category_groups[category].append(i)
        
        category_nodes = {}
        category_id = 0
        
        # Create main category nodes (Layer 1)
        for category, article_indices in category_groups.items():
            if len(article_indices) >= 3:  # Only substantial categories
                category_node_id = f"category_{category_id}"
                category_nodes[category] = category_node_id
                
                nodes.append({
                    'id': category_node_id,
                    'label': category,
                    'type': 'category',
                    'layer': 1,
                    'size': int(min(80, 40 + len(article_indices) * 2)),
                    'color': self._get_category_color(category_id),
                    'article_count': int(len(article_indices)),
                    'articles': article_indices
                })
                category_id += 1
        
        # Layer 2: Create topic nodes within each category
        topic_info = topic_model.get_topic_info()
        topic_id = 0
        topic_to_category = {}
        
        for _, row in topic_info.iterrows():
            bertopic_topic_id = int(row['Topic'])
            if bertopic_topic_id == -1:  # Skip outliers
                continue
                
            # Get articles assigned to this topic
            topic_articles = [i for i, t in enumerate(topics) if t == bertopic_topic_id]
            if len(topic_articles) < 2:
                continue
            
            # Determine which category this topic belongs to
            category_votes = defaultdict(int)
            for idx in topic_articles:
                article_category = articles[idx].get('category', 'General')
                category_votes[article_category] += 1
            
            # Assign to the most common category
            primary_category = max(category_votes.items(), key=lambda x: x[1])[0]
            topic_to_category[bertopic_topic_id] = primary_category
            
            if primary_category in category_nodes:
                # Get topic representation
                topic_words = topic_model.get_topic(bertopic_topic_id)
                if topic_words:
                    top_words = [word for word, score in topic_words[:3]]
                    topic_label = self._create_semantic_topic_label(top_words, topic_articles, articles)
                    
                    topic_node_id = f"topic_{topic_id}"
                    
                    # Create topic node (Layer 2)
                    nodes.append({
                        'id': topic_node_id,
                        'label': topic_label,
                        'type': 'topic',
                        'layer': 2,
                        'size': int(min(60, 25 + len(topic_articles) * 2)),
                        'color': self._lighten_color(self._get_category_color(
                            list(category_nodes.keys()).index(primary_category)
                        )),
                        'article_count': int(len(topic_articles)),
                        'parent_category': primary_category,
                        'topic_words': top_words,
                        'articles': topic_articles
                    })
                    
                    # Connect topic to its category
                    edges.append({
                        'source': category_nodes[primary_category],
                        'target': topic_node_id,
                        'weight': float(len(topic_articles)),
                        'type': 'category_to_topic'
                    })
                    
                    # Layer 3: Create subtopic nodes based on hierarchical structure
                    self._create_subtopic_nodes(
                        nodes, edges, topic_node_id, topic_words, 
                        topic_articles, articles, topic_id
                    )
                    
                    topic_id += 1
        
        # Create cross-category connections for related topics
        self._create_cross_category_connections(nodes, edges, topic_model, topics)
        
        logger.info(f"Built 3-layer hierarchy with {len(nodes)} nodes and {len(edges)} edges")
        
        return {
            'nodes': nodes,
            'edges': edges,
            'clusters': clusters,
            'metadata': {
                'total_articles': int(len(articles)),
                'total_categories': int(len(category_nodes)),
                'total_topics': int(len([n for n in nodes if n['type'] == 'topic'])),
                'total_subtopics': int(len([n for n in nodes if n['type'] == 'subtopic'])),
                'generated_at': datetime.now().isoformat(),
                'method': 'BERTopic Hierarchical'
            }
        }
    
    def _create_subtopic_nodes(self, nodes: List[Dict], edges: List[Dict],
                             parent_topic_id: str, topic_words: List[tuple],
                             topic_articles: List[int], articles: List[Dict[str, Any]],
                             topic_id: int):
        """Create Layer 3: Subtopic nodes for deeper drilldown."""
        
        # Create subtopics based on different aspects
        subtopic_id = 0
        
        # 1. Subtopics based on key concepts from topic words (PRIMARY)
        concept_subtopics = 0
        for i, (word, score) in enumerate(topic_words[:4]):  # Use top 4 words for subtopics
            if len(word) > 3 and score > 0.02 and concept_subtopics < 3:
                # Find articles that prominently feature this word
                word_articles = []
                for idx in topic_articles:
                    article_text = articles[idx]['text'].lower()
                    if word.lower() in article_text:
                        word_articles.append(idx)
                
                if len(word_articles) >= 2:
                    nodes.append({
                        'id': f"subtopic_{topic_id}_{subtopic_id}",
                        'label': f"{word.title()}",
                        'type': 'subtopic',
                        'layer': 3,
                        'size': int(min(35, 12 + len(word_articles) * 1.5)),
                        'color': self._get_subtopic_color(),
                        'article_count': int(len(word_articles)),
                        'parent_topic': parent_topic_id,
                        'articles': word_articles,
                        'concept': word
                    })
                    
                    edges.append({
                        'source': parent_topic_id,
                        'target': f"subtopic_{topic_id}_{subtopic_id}",
                        'weight': float(score * 10),
                        'type': 'topic_to_subtopic'
                    })
                    subtopic_id += 1
                    concept_subtopics += 1
        
        # 2. Only create sentiment subtopics if we have enough articles and diverse sentiments
        if len(topic_articles) > 5:  # Only for larger topics
            sentiment_groups = defaultdict(list)
            for idx in topic_articles:
                sentiment = articles[idx].get('sentiment')
                if sentiment and sentiment not in ['neutral', 'Neutral', 'unknown', None]:
                    sentiment_groups[sentiment].append(idx)
            
            # Only create sentiment subtopics if we have meaningful diversity
            if len(sentiment_groups) >= 2:
                for sentiment, indices in sentiment_groups.items():
                    if len(indices) >= 3:  # Higher threshold for sentiment subtopics
                        nodes.append({
                            'id': f"subtopic_{topic_id}_{subtopic_id}",
                            'label': f"{sentiment.title()} Sentiment",
                            'type': 'subtopic',
                            'layer': 3,
                            'size': int(min(30, 10 + len(indices) * 1.2)),
                            'color': self._get_subtopic_color(),
                            'article_count': int(len(indices)),
                            'parent_topic': parent_topic_id,
                            'articles': indices,
                            'subtype': 'sentiment'
                        })
                        
                        edges.append({
                            'source': parent_topic_id,
                            'target': f"subtopic_{topic_id}_{subtopic_id}",
                            'weight': float(len(indices)),
                            'type': 'topic_to_subtopic'
                        })
                        subtopic_id += 1
    
    def _create_semantic_topic_label(self, top_words: List[str], 
                                   topic_articles: List[int], 
                                   articles: List[Dict[str, Any]]) -> str:
        """Create meaningful semantic labels for topics."""
        if not top_words:
            return "Unnamed Topic"
        
        # Analyze the articles to understand the semantic theme
        themes = {
            'technology': ['ai', 'artificial', 'intelligence', 'machine', 'learning', 
                          'digital', 'algorithm', 'automation', 'robot', 'software', 'data'],
            'business': ['market', 'company', 'industry', 'business', 'economic', 
                        'financial', 'investment', 'corporate', 'revenue', 'profit'],
            'social': ['social', 'society', 'people', 'community', 'culture', 
                      'human', 'public', 'policy', 'government', 'politics'],
            'research': ['research', 'study', 'analysis', 'science', 'scientific', 
                        'academic', 'paper', 'data', 'findings', 'evidence'],
            'health': ['health', 'medical', 'healthcare', 'disease', 'treatment', 
                      'patient', 'clinical', 'medicine', 'therapy', 'hospital'],
            'environment': ['environment', 'climate', 'energy', 'sustainability', 
                           'green', 'carbon', 'renewable', 'pollution', 'conservation'],
            'security': ['security', 'cyber', 'privacy', 'protection', 'threat', 
                        'risk', 'safety', 'defense', 'attack', 'vulnerability'],
            'education': ['education', 'learning', 'student', 'school', 'university', 
                         'teaching', 'academic', 'knowledge', 'training', 'course']
        }
        
        # Count theme words in the articles (sample to avoid processing too much)
        theme_scores = defaultdict(int)
        sample_articles = topic_articles[:10]  # Sample for performance
        article_texts = ' '.join([articles[i]['text'].lower() for i in sample_articles])
        
        for theme, words in themes.items():
            for word in words:
                # Count exact word matches, not substrings
                word_count = len([w for w in article_texts.split() if w == word])
                theme_scores[theme] += word_count
        
        # Filter out sentiment words from top_words to avoid sentiment topics
        sentiment_words = {'positive', 'negative', 'neutral', 'good', 'bad', 'sentiment'}
        filtered_words = [w for w in top_words if w.lower() not in sentiment_words]
        
        if not filtered_words:
            filtered_words = top_words  # Fallback if all words filtered
        
        # Determine primary theme and create label
        if theme_scores:
            primary_theme = max(theme_scores.items(), key=lambda x: x[1])[0]
            if theme_scores[primary_theme] > 0:  # Only if theme actually appears
                return f"{primary_theme.title()}: {filtered_words[0].title()}"
        
        # Fallback to descriptive combination
        if len(filtered_words) >= 2:
            return f"{filtered_words[0].title()} & {filtered_words[1].title()}"
        
        return filtered_words[0].title()
    
    def _create_cross_category_connections(self, nodes: List[Dict], edges: List[Dict],
                                         topic_model: BERTopic, topics: List[int]):
        """Create connections between related topics across categories."""
        
        # Get topic embeddings for similarity calculation
        try:
            topic_embeddings = topic_model.topic_embeddings_
            if topic_embeddings is not None and len(topic_embeddings) > 1:
                from sklearn.metrics.pairwise import cosine_similarity
                
                similarities = cosine_similarity(topic_embeddings)
                topic_nodes = [n for n in nodes if n['type'] == 'topic']
                
                for i, node1 in enumerate(topic_nodes):
                    for j, node2 in enumerate(topic_nodes[i+1:], i+1):
                        if i < len(similarities) and j < len(similarities):
                            similarity = similarities[i][j]
                            if similarity > 0.4:  # Higher threshold for cross-category connections
                                edges.append({
                                    'source': node1['id'],
                                    'target': node2['id'],
                                    'weight': float(similarity * 3),
                                    'type': 'cross_topic_relation'
                                })
        except Exception as e:
            logger.warning(f"Could not create cross-category connections: {e}")
    
    def _create_category_based_hierarchy(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fallback: Create hierarchy based on existing categories when BERTopic fails."""
        
        nodes = []
        edges = []
        
        # Group by category and topic
        category_groups = defaultdict(list)
        for i, article in enumerate(articles):
            category = article.get('category', 'General')
            category_groups[category].append(i)
        
        category_id = 0
        for category, article_indices in category_groups.items():
            if len(article_indices) >= 2:
                # Create category node
                category_node_id = f"category_{category_id}"
                nodes.append({
                    'id': category_node_id,
                    'label': category,
                    'type': 'category',
                    'layer': 1,
                    'size': int(min(70, 30 + len(article_indices) * 2)),
                    'color': self._get_category_color(category_id),
                    'article_count': int(len(article_indices)),
                    'articles': article_indices
                })
                
                # Create topic nodes within category
                topic_groups = defaultdict(list)
                for idx in article_indices:
                    topic = articles[idx].get('topic', 'General')
                    topic_groups[topic].append(idx)
                
                topic_id = 0
                for topic, topic_article_indices in topic_groups.items():
                    if len(topic_article_indices) >= 2:
                        topic_node_id = f"topic_{category_id}_{topic_id}"
                        nodes.append({
                            'id': topic_node_id,
                            'label': topic,
                            'type': 'topic',
                            'layer': 2,
                            'size': int(min(50, 20 + len(topic_article_indices) * 2)),
                            'color': self._lighten_color(self._get_category_color(category_id)),
                            'article_count': int(len(topic_article_indices)),
                            'parent_category': category,
                            'articles': topic_article_indices
                        })
                        
                        edges.append({
                            'source': category_node_id,
                            'target': topic_node_id,
                            'weight': float(len(topic_article_indices)),
                            'type': 'category_to_topic'
                        })
                        topic_id += 1
                
                category_id += 1
        
        return {
            'nodes': nodes,
            'edges': edges,
            'clusters': [],
            'metadata': {
                'total_articles': int(len(articles)),
                'total_categories': int(len(category_groups)),
                'generated_at': datetime.now().isoformat(),
                'method': 'Category-based Hierarchy'
            }
        }
    
    def _get_category_color(self, category_id: int) -> str:
        """Get distinct colors for main categories."""
        colors = [
            '#FF69B4', '#32CD32', '#4169E1', '#FF6347', '#20B2AA', 
            '#DDA0DD', '#F0E68C', '#87CEEB', '#DEB887', '#98FB98'
        ]
        return colors[category_id % len(colors)]
    
    def _get_subtopic_color(self) -> str:
        """Get lighter colors for subtopics."""
        return '#E6E6FA'  # Light purple for all subtopics
    
    def _lighten_color(self, hex_color: str, factor: float = 0.4) -> str:
        """Lighten a hex color for topic nodes."""
        try:
            hex_color = hex_color.lstrip('#')
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            
            r = min(255, int(r + (255 - r) * factor))
            g = min(255, int(g + (255 - g) * factor))
            b = min(255, int(b + (255 - b) * factor))
            
            return f'#{r:02x}{g:02x}{b:02x}'
        except Exception:
            return '#D3D3D3'
    
    def get_topic_map_data(self, 
                          topic_filter: Optional[str] = None,
                          category_filter: Optional[str] = None,
                          limit: int = 500,
                          use_guided: bool = False,
                          seed_topics: Optional[List[List[str]]] = None) -> Dict[str, Any]:
        """Generate hierarchical topic map data for 3-layer visualization."""
        
        # Extract articles
        articles = self.extract_topics_from_articles(
            limit=limit,
            topic_filter=topic_filter,
            category_filter=category_filter
        )
        
        if not articles:
            return {"nodes": [], "edges": [], "clusters": [], "error": "No articles found"}
        
        # Build hierarchical structure using BERTopic with OpenAI embeddings
        try:
            if use_guided and seed_topics:
                logger.info("Using guided BERTopic with OpenAI embeddings")
                hierarchy = self.build_guided_topic_map(articles, seed_topics)
            else:
                logger.info("Using hierarchical BERTopic with OpenAI embeddings")
                hierarchy = self.build_hierarchical_topic_map(articles)
        except Exception as e:
            logger.warning(f"BERTopic modeling failed: {e}, falling back to improved hierarchy")
            hierarchy = self._create_improved_fallback_hierarchy(articles)
        
        # Add statistics
        hierarchy['statistics'] = self._calculate_topic_statistics(articles)
        
        return hierarchy
    
    def _calculate_topic_statistics(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics about the hierarchical topics."""
        
        topic_counter = Counter()
        category_counter = Counter()
        sentiment_counter = Counter()
        
        for article in articles:
            if article.get('topic'):
                topic_counter[article['topic']] += 1
            if article.get('category'):
                category_counter[article['category']] += 1
            if article.get('sentiment'):
                sentiment_counter[article['sentiment']] += 1
        
        return {
            'total_articles': int(len(articles)),
            'by_topic': {k: int(v) for k, v in topic_counter.items()},
            'by_category': {k: int(v) for k, v in category_counter.items()},
            'by_sentiment': {k: int(v) for k, v in sentiment_counter.items()},
            'layers': {
                'categories': len(category_counter),
                'topics': len(topic_counter),
                'estimated_subtopics': sum(1 for v in topic_counter.values() if v >= 3) * 2
            }
        }

    def build_guided_topic_map(self, articles: List[Dict[str, Any]], 
                              seed_topics: List[List[str]]) -> Dict[str, Any]:
        """Build topic map using Guided BERTopic with OpenAI embeddings and predefined seed topics."""
        
        if len(articles) < 10:
            logger.warning(f"Too few articles ({len(articles)}) for guided modeling")
            return self._create_improved_fallback_hierarchy(articles)
        
        # Extract documents for BERTopic
        documents = [article['enhanced_text'] for article in articles]
        article_uris = [article['uri'] for article in articles]
        
        logger.info(f"Running Guided BERTopic with {len(seed_topics)} seed topics on {len(documents)} documents using OpenAI embeddings...")
        
        try:
            # Try to leverage existing OpenAI embeddings from ChromaDB first
            embeddings = self._leverage_existing_vectors(article_uris)
            
            if embeddings is None or len(embeddings) != len(documents):
                logger.info("Existing embeddings not available for guided modeling, generating new OpenAI embeddings")
                embeddings = self._embed_documents_with_openai(documents)
            else:
                logger.info("Using existing OpenAI embeddings from ChromaDB for guided modeling")
            
            # Configure HDBSCAN for guided clustering
            hdbscan_model = HDBSCAN(
                min_cluster_size=max(3, len(documents) // 20),
                min_samples=2,
                metric='euclidean',
                cluster_selection_method='eom',
                prediction_data=True
            )
            
            # Use KeyBERTInspired for better topic representations
            representation_model = KeyBERTInspired()
            
            # Configure vectorizer with custom stopwords
            vectorizer_model = CountVectorizer(
                ngram_range=(1, 2),
                stop_words=list(self.custom_stopwords),  # Convert set to list
                max_features=500,
                min_df=3,
                max_df=0.7
            )
            
            # Create a SentenceTransformer model for BERTopic's internal operations
            try:
                from sentence_transformers import SentenceTransformer
                internal_embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Using SentenceTransformer for guided BERTopic internal operations")
            except ImportError:
                logger.warning("SentenceTransformers not available for guided modeling, using simpler representation")
                representation_model = None
                internal_embedding_model = None
            
            # Initialize Guided BERTopic with embedding model for internal use
            topic_model = BERTopic(
                embedding_model=internal_embedding_model,  # For internal BERTopic operations
                hdbscan_model=hdbscan_model,
                vectorizer_model=vectorizer_model,
                representation_model=representation_model,
                seed_topic_list=seed_topics,  # This enables guided modeling
                nr_topics="auto",
                verbose=True
            )
            
            logger.info("Fitting Guided BERTopic model with OpenAI embeddings...")
            topics, probabilities = topic_model.fit_transform(documents, embeddings)
            
            logger.info(f"Guided BERTopic completed. Topics found: {len(set(topics))}")
            logger.info(f"Seed topics provided: {seed_topics}")
            
            # Check if guided modeling worked
            unique_topics = [t for t in set(topics) if t != -1]
            if len(unique_topics) < 2:
                logger.warning("Guided BERTopic found too few topics, falling back")
                return self._create_improved_fallback_hierarchy(articles)
            
            # Generate hierarchical topics
            hierarchical_topics = topic_model.hierarchical_topics(documents)
            
            logger.info(f"Generated {len(unique_topics)} guided topics with hierarchical structure")
            
            # Build 3-layer visualization structure
            result = self._build_three_layer_structure(
                articles, topic_model, topics, hierarchical_topics
            )
            
            # Add guided modeling metadata
            result['metadata']['method'] = 'Guided BERTopic with OpenAI Embeddings'
            result['metadata']['seed_topics'] = seed_topics
            result['metadata']['embedding_model'] = 'OpenAI text-embedding-3-small'
            result['metadata']['embedding_dimensions'] = 1536
            result['metadata']['internal_model'] = 'SentenceTransformer all-MiniLM-L6-v2'
            
            return result
            
        except Exception as e:
            logger.error(f"Guided BERTopic modeling failed: {e}", exc_info=True)
            logger.info("Falling back to improved fallback hierarchy")
            return self._create_improved_fallback_hierarchy(articles)

    def _create_improved_fallback_hierarchy(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Improved fallback: Layer 1: Topic, Layer 2: Category, Layer 3: Tags."""
        
        nodes = []
        edges = []
        
        # Layer 1: Group by topic (main topics from article.topic)
        topic_groups = defaultdict(list)
        for i, article in enumerate(articles):
            topic = article.get('topic', 'General Topic')
            topic_groups[topic].append(i)
        
        topic_node_map = {}
        topic_id = 0
        
        # Create Layer 1: Topic nodes
        for topic, article_indices in topic_groups.items():
            if len(article_indices) >= 2:
                topic_node_id = f"topic_{topic_id}"
                topic_node_map[topic] = topic_node_id
                
                nodes.append({
                    'id': topic_node_id,
                    'label': topic,
                    'type': 'topic',
                    'layer': 1,
                    'size': int(min(80, 40 + len(article_indices) * 2)),
                    'color': self._get_category_color(topic_id),
                    'article_count': int(len(article_indices)),
                    'articles': article_indices
                })
                
                # Layer 2: Create category nodes within each topic
                category_groups = defaultdict(list)
                for idx in article_indices:
                    category = articles[idx].get('category', 'General Category')
                    category_groups[category].append(idx)
                
                category_id = 0
                for category, cat_indices in category_groups.items():
                    if len(cat_indices) >= 2:
                        category_node_id = f"category_{topic_id}_{category_id}"
                        
                        nodes.append({
                            'id': category_node_id,
                            'label': category,
                            'type': 'category',
                            'layer': 2,
                            'size': int(min(60, 25 + len(cat_indices) * 2)),
                            'color': self._lighten_color(self._get_category_color(topic_id)),
                            'article_count': int(len(cat_indices)),
                            'parent_topic': topic,
                            'articles': cat_indices
                        })
                        
                        # Connect category to topic
                        edges.append({
                            'source': topic_node_id,
                            'target': category_node_id,
                            'weight': float(len(cat_indices)),
                            'type': 'topic_to_category'
                        })
                        
                        # Layer 3: Create tag-based subtopic nodes
                        self._create_tag_based_subtopics(
                            nodes, edges, category_node_id, cat_indices, 
                            articles, topic_id, category_id
                        )
                        
                        category_id += 1
                
                topic_id += 1
        
        logger.info(f"Created improved fallback hierarchy with {len(nodes)} nodes and {len(edges)} edges")
        
        return {
            'nodes': nodes,
            'edges': edges,
            'clusters': [],
            'metadata': {
                'total_articles': int(len(articles)),
                'total_topics': int(len(topic_groups)),
                'generated_at': datetime.now().isoformat(),
                'method': 'Improved Fallback (Topic-Category-Tags)'
            }
        }
    
    def _create_tag_based_subtopics(self, nodes: List[Dict], edges: List[Dict],
                                   parent_category_id: str, article_indices: List[int],
                                   articles: List[Dict[str, Any]], topic_id: int, category_id: int):
        """Create Layer 3 subtopics based on article tags."""
        
        # Extract and process tags
        tag_groups = defaultdict(list)
        for idx in article_indices:
            tags_str = articles[idx].get('tags', '')
            if tags_str:
                # Split tags by common delimiters
                import re
                tags = re.split(r'[,;|]', tags_str)
                tags = [tag.strip().lower() for tag in tags if tag.strip()]
                
                for tag in tags:
                    if len(tag) > 2 and tag not in self.custom_stopwords:
                        tag_groups[tag].append(idx)
        
        # Create subtopic nodes for significant tags
        subtopic_id = 0
        for tag, tag_indices in tag_groups.items():
            if len(tag_indices) >= 2:  # Only tags with multiple articles
                nodes.append({
                    'id': f"subtopic_{topic_id}_{category_id}_{subtopic_id}",
                    'label': tag.title(),
                    'type': 'subtopic',
                    'layer': 3,
                    'size': int(min(40, 15 + len(tag_indices) * 1.5)),
                    'color': self._get_subtopic_color(),
                    'article_count': int(len(tag_indices)),
                    'parent_category': parent_category_id,
                    'articles': tag_indices,
                    'tag': tag
                })
                
                edges.append({
                    'source': parent_category_id,
                    'target': f"subtopic_{topic_id}_{category_id}_{subtopic_id}",
                    'weight': float(len(tag_indices)),
                    'type': 'category_to_subtopic'
                })
                subtopic_id += 1
    
    def generate_topic_visualizations(self, articles: List[Dict[str, Any]], 
                                     topic_model, topics: List[int]) -> Dict[str, Any]:
        """Generate debugging visualizations for topic analysis."""
        
        visualizations = {}
        documents = [article['enhanced_text'] for article in articles]
        
        try:
            # 1. Visualize Topics per Class (by category)
            categories = [article.get('category', 'Unknown') for article in articles]
            topics_per_class = topic_model.topics_per_class(documents, classes=categories)
            visualizations['topics_per_class'] = {
                'data': topics_per_class,
                'description': 'Topics distribution across article categories'
            }
            
            # 2. Visualize Topic Similarity (heatmap data)
            try:
                topic_embeddings = topic_model.topic_embeddings_
                if topic_embeddings is not None:
                    from sklearn.metrics.pairwise import cosine_similarity
                    similarity_matrix = cosine_similarity(topic_embeddings)
                    visualizations['topic_similarity'] = {
                        'matrix': similarity_matrix.tolist(),
                        'topic_labels': [f"Topic {i}" for i in range(len(similarity_matrix))],
                        'description': 'Cosine similarity between topics'
                    }
            except Exception as e:
                logger.warning(f"Could not generate topic similarity: {e}")
            
            # 3. Visualize Topic Terms (top words per topic)
            topic_terms = {}
            for topic_id in set(topics):
                if topic_id != -1:  # Skip outliers
                    topic_words = topic_model.get_topic(topic_id)
                    if topic_words:
                        topic_terms[f"Topic {topic_id}"] = [
                            {'word': word, 'score': float(score)} 
                            for word, score in topic_words[:10]
                        ]
            
            visualizations['topic_terms'] = {
                'data': topic_terms,
                'description': 'Top words and scores for each topic'
            }
            
            # 4. Visualize Topic Hierarchy
            try:
                hierarchical_topics = topic_model.hierarchical_topics(documents)
                hierarchy_data = []
                for _, row in hierarchical_topics.iterrows():
                    hierarchy_data.append({
                        'parent_id': int(row['Parent_ID']),
                        'child_left': int(row['Child_Left_ID']),
                        'child_right': int(row['Child_Right_ID']),
                        'distance': float(row['Distance']),
                        'parent_name': row['Parent_Name'][:50] if row['Parent_Name'] else 'Unknown',
                        'topics': row['Topics'] if 'Topics' in row else []
                    })
                
                visualizations['topic_hierarchy'] = {
                    'data': hierarchy_data,
                    'description': 'Hierarchical clustering of topics'
                }
            except Exception as e:
                logger.warning(f"Could not generate topic hierarchy visualization: {e}")
            
            # 5. Topic Tree (simplified hierarchy)
            try:
                topic_info = topic_model.get_topic_info()
                tree_data = []
                for _, row in topic_info.iterrows():
                    topic_id = int(row['Topic'])
                    if topic_id != -1:
                        topic_words = topic_model.get_topic(topic_id)
                        tree_data.append({
                            'id': topic_id,
                            'name': row['Name'][:30] if row['Name'] else f'Topic {topic_id}',
                            'count': int(row['Count']),
                            'words': [word for word, score in topic_words[:5]] if topic_words else [],
                            'representative_docs': topic_model.get_representative_docs(topic_id)[:2] if hasattr(topic_model, 'get_representative_docs') else []
                        })
                
                visualizations['topic_tree'] = {
                    'data': tree_data,
                    'description': 'Tree structure of topics with representative information'
                }
            except Exception as e:
                logger.warning(f"Could not generate topic tree: {e}")
            
            # 6. Document-Topic Distribution
            try:
                if hasattr(topic_model, 'approximate_distribution'):
                    # Sample a few documents for distribution analysis
                    sample_docs = documents[:min(10, len(documents))]
                    distributions = topic_model.approximate_distribution(sample_docs)
                    
                    distribution_data = []
                    for i, dist in enumerate(distributions):
                        doc_dist = [{'topic': j, 'probability': float(prob)} for j, prob in enumerate(dist) if prob > 0.1]
                        distribution_data.append({
                            'document_index': i,
                            'document_preview': sample_docs[i][:100] + '...',
                            'topic_distribution': doc_dist
                        })
                    
                    visualizations['document_topic_distribution'] = {
                        'data': distribution_data,
                        'description': 'Probability distribution of topics across sample documents'
                    }
            except Exception as e:
                logger.warning(f"Could not generate document-topic distribution: {e}")
            
            logger.info(f"Generated {len(visualizations)} visualization datasets")
            return visualizations
            
        except Exception as e:
            logger.error(f"Failed to generate topic visualizations: {e}")
            return {'error': str(e)}

    async def beautify_topic_label_with_llm(self, 
                                       top_words: List[str], 
                                       sample_titles: List[str],
                                       category_context: str = None) -> str:
        """Use LLM to create beautiful, human-readable topic labels from BERTopic keywords."""
        try:
            # Import here to avoid circular imports
            from app.services.llm_service import LLMService
            
            # Create context for the LLM
            words_str = ", ".join(top_words[:5])
            titles_str = " | ".join(sample_titles[:3])
            
            prompt = f"""
            Create a concise, descriptive 2-4 word topic label from these keywords and sample article titles.
            
            Keywords: {words_str}
            Sample titles: {titles_str}
            Category context: {category_context or 'General'}
            
            Requirements:
            - Use 2-4 words maximum
            - Make it human-readable and descriptive
            - Capture the main theme
            - Avoid generic terms like "topic" or "analysis"
            - Use title case
            
            Examples:
            - Keywords: "ai, artificial, intelligence" → "AI Technology"
            - Keywords: "market, business, growth" → "Market Growth"
            - Keywords: "climate, environment, change" → "Climate Change"
            
            Topic label:"""
            
            llm_service = LLMService()
            response = await llm_service.generate_completion(
                prompt=prompt,
                max_tokens=20,
                temperature=0.3
            )
            
            if response and response.strip():
                # Clean up the response
                label = response.strip().strip('"').strip("'")
                # Ensure it's not too long
                if len(label) <= 50:
                    return label
            
        except Exception as e:
            logger.warning(f"LLM topic label beautification failed: {e}")
        
        # Fallback to simple heuristic-based labeling
        return self._create_heuristic_topic_label(top_words)
    
    def _create_heuristic_topic_label(self, top_words: List[str]) -> str:
        """Create topic labels using simple heuristics."""
        if not top_words:
            return "Unnamed Topic"
        
        if len(top_words) >= 2:
            primary_word = top_words[0].title()
            secondary_word = top_words[1].title()
            
            # Domain-specific heuristics
            if any(word in top_words for word in ['ai', 'artificial', 'intelligence', 'machine', 'learning']):
                return f"AI & {secondary_word}"
            elif any(word in top_words for word in ['market', 'business', 'economic', 'financial']):
                return f"Market {secondary_word}"
            elif any(word in top_words for word in ['social', 'society', 'people', 'community']):
                return f"Social {secondary_word}"
            elif any(word in top_words for word in ['technology', 'tech', 'digital', 'software']):
                return f"Tech {secondary_word}"
            elif any(word in top_words for word in ['health', 'medical', 'healthcare', 'medicine']):
                return f"Health {secondary_word}"
            elif any(word in top_words for word in ['environment', 'climate', 'green', 'sustainability']):
                return f"Environmental {secondary_word}"
            elif any(word in top_words for word in ['policy', 'government', 'political', 'regulation']):
                return f"Policy {secondary_word}"
            else:
                return f"{primary_word} & {secondary_word}"
        else:
            return top_words[0].title()
    
    def get_topic_details(self, topic_id: str, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get detailed information about a specific topic node for drill-down."""
        try:
            # Parse topic ID to understand the hierarchy level
            if topic_id.startswith('cat_'):
                # Category node
                category_id = int(topic_id.split('_')[1])
                return self._get_category_details(category_id, articles)
            elif topic_id.startswith('topic_'):
                # Topic node
                parts = topic_id.split('_')
                if len(parts) >= 3:
                    category_id = int(parts[1])
                    topic_num = int(parts[2])
                    return self._get_topic_details(category_id, topic_num, articles)
            elif topic_id.startswith('art_'):
                # Article node
                parts = topic_id.split('_')
                if len(parts) >= 2:
                    article_idx = int(parts[-1])
                    if 0 <= article_idx < len(articles):
                        return self._get_article_details(articles[article_idx])
            
            return {"error": "Topic not found"}
            
        except Exception as e:
            logger.error(f"Error getting topic details for {topic_id}: {e}")
            return {"error": str(e)}
    
    def _get_category_details(self, category_id: int, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get details for a category node."""
        # Group articles by category
        category_groups = defaultdict(list)
        for i, article in enumerate(articles):
            category = article.get('category', 'General')
            category_groups[category].append(i)
        
        categories = list(category_groups.keys())
        if category_id < len(categories):
            category = categories[category_id]
            article_indices = category_groups[category]
            category_articles = [articles[i] for i in article_indices]
            
            # Calculate statistics
            sentiment_counts = Counter(article.get('sentiment', 'Unknown') for article in category_articles)
            topic_counts = Counter(article.get('topic', 'Unknown') for article in category_articles)
            
            return {
                "type": "category",
                "name": category,
                "article_count": len(category_articles),
                "articles": category_articles[:10],  # First 10 for preview
                "sentiment_distribution": dict(sentiment_counts),
                "topic_distribution": dict(topic_counts),
                "date_range": {
                    "earliest": min((a.get('submission_date', '') for a in category_articles), default=''),
                    "latest": max((a.get('submission_date', '') for a in category_articles), default='')
                }
            }
        
        return {"error": "Category not found"}
    
    def _get_topic_details(self, category_id: int, topic_num: int, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get details for a topic node."""
        # This would require storing the BERTopic model results
        # For now, return basic information
        return {
            "type": "topic",
            "category_id": category_id,
            "topic_number": topic_num,
            "message": "Topic details require BERTopic model context"
        }
    
    def _get_article_details(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Get details for an article node."""
        return {
            "type": "article",
            "title": article.get('title', 'Untitled'),
            "summary": article.get('summary', 'No summary available'),
            "category": article.get('category', 'Unknown'),
            "topic": article.get('topic', 'Unknown'),
            "sentiment": article.get('sentiment', 'Unknown'),
            "future_signal": article.get('future_signal'),
            "driver_type": article.get('driver_type'),
            "time_to_impact": article.get('time_to_impact'),
            "submission_date": article.get('submission_date'),
            "uri": article.get('uri'),
            "tags": article.get('tags')
        } 