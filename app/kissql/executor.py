"""KISSQL Query Executor.

This module handles the execution of parsed queries against ChromaDB.
"""

import logging
from typing import Dict, Any, List, Optional

from app.kissql.parser import Query, Constraint
from app.kissql.pipe_operators import apply_pipe_operations
from app.vector_store import search_articles, similar_articles

logger = logging.getLogger(__name__)


def execute_query(query: Query, top_k: int = 100) -> Dict[str, Any]:
    """Execute a parsed query and return the results.
    
    Args:
        query: The parsed Query object
        top_k: Maximum number of results to return
        
    Returns:
        A dict with search results, facets, and timeline
    """
    # Extract pipe operations for later use
    pipe_ops = []
    for op in query.pipe_operations:
        pipe_op = {
            'operation': op.operation,
        }
        if op.params and len(op.params) > 0:
            try:
                pipe_op['count'] = int(op.params[0])
            except (ValueError, TypeError):
                pass
        pipe_ops.append(pipe_op)
    
    # Check for special meta controls
    limit = top_k
    cluster_id = None
    similar_to = None
    sort_field = None
    sort_direction = 'asc'
    
    # Process meta controls
    for meta in query.meta_controls:
        if meta.name == 'limit':
            try:
                limit = int(meta.value)
            except ValueError:
                pass
        elif meta.name == 'similar':
            similar_to = meta.value
        elif meta.name == 'cluster':
            try:
                cluster_id = int(meta.value)
            except ValueError:
                pass
        elif meta.name == 'sort':
            sort_field = meta.value
            # Get sort direction from params if available
            if meta.params and meta.params[0] in ['asc', 'desc']:
                sort_direction = meta.params[0]
            logger.info(
                "Sort control detected: field=%s, direction=%s",
                sort_field, sort_direction
            )
    
    # Handle similar-to queries
    if similar_to:
        similar_results = similar_articles(similar_to, top_k=limit)
        
        # Apply pipe operations even for similar results
        if pipe_ops:
            logger.info(
                "Applying %d pipe operations to similar results", 
                len(pipe_ops)
            )
            similar_results = apply_pipe_operations(
                similar_results, 
                pipe_ops
            )
            
        return {
            "results": similar_results,
            "facets": {},  # Could compute facets from results if needed
            "timeline": {},
        }
    
    # Extract equality constraints for ChromaDB native filtering
    metadata_filter = {}
    for constraint in query.constraints:
        if constraint.operator == '=':
            # Get field and value for filtering
            field = constraint.field
            value = constraint.value
            
            # For categorical fields, normalize for exact DB matching
            if field.lower() in [
                "sentiment", "topic", "category", "news_source"
            ]:
                if isinstance(value, str):
                    # Remove any quote marks to ensure clean values
                    value = value.strip('"\'')
                    logger.info(
                        "Processing filter value for %s: %s",
                        field, value
                    )
                    
                    # NOTE: Don't convert case - keep original value
                    # This preserves exact match with DB values
            
            # Capture the constraint without case changes
            metadata_filter[field] = value
            logger.debug(
                "Adding constraint: %s = %s", 
                field, 
                value
            )
    
    # First, execute the search without filters to get complete facets
    # Use a very high limit to effectively get all results
    full_results = search_articles(
        query.text,
        top_k=100000,  # Effectively unlimited
        metadata_filter={},  # No filtering for facet generation
    )
    
    # Log the search parameters and number of results before filtering
    logger.info(
        "Searching with query: %s, metadata_filter: %s", 
        query.text,
        metadata_filter
    )
    
    # Build query kwargs dynamically to avoid passing an *empty* ``where``
    # dict – newer Chroma versions treat an empty filter as invalid and
    # raise "Expected where to have exactly one operator".
    query_kwargs: dict[str, Any] = {
        "n_results": limit,
        "include": ["metadatas", "distances"],
    }
    if metadata_filter:
        query_kwargs["where"] = (
            metadata_filter
            if len(metadata_filter) == 1
            else {"$and": [{k: v} for k, v in metadata_filter.items()]}
        )
        
        # Debug log the actual where filter being sent to Chroma
        logger.info(
            "Chroma where filter: %s", 
            query_kwargs.get("where")
        )
    
    # Then do the actual search with filters applied
    try:
        results = search_articles(
            query.text,
            top_k=limit,
            metadata_filter=metadata_filter,
        )
        # Log the number of results after filtering
        logger.info(
            "Found %d results after applying metadata filters", 
            len(results)
        )
    except Exception as exc:
        logger.error("Error executing search: %s", exc)
        results = []
    
    # Post-process for advanced filtering
    filtered_results = []
    for result in results:
        # Apply constraints that ChromaDB doesn't support natively
        if _passes_advanced_constraints(result, query.constraints):
            filtered_results.append(result)
    
    # Log the number of results after advanced filtering
    logger.info(
        "Found %d results after applying advanced constraints", 
        len(filtered_results)
    )
    
    # Apply pipe operations immediately after filtering but before clustering or other processing
    if pipe_ops:
        logger.info(
            "Applying %d pipe operations", 
            len(pipe_ops)
        )
        filtered_results = apply_pipe_operations(
            filtered_results, 
            pipe_ops
        )
        logger.info(
            "After pipe operations: %d results", 
            len(filtered_results)
        )
    
    # Apply clustering filter if requested
    # IMPORTANT: Clustering should run on the already pipe-filtered results
    if cluster_id is not None:
        try:
            from sklearn.cluster import MiniBatchKMeans
            
            # Extract vectors from the results - may return None
            vectors = _extract_vectors_from_results(filtered_results)
            
            # Only proceed if we got actual vectors back
            if vectors is not None and len(vectors) > 0:
                # Cluster the vectors
                n_clusters = max(2, min(10, len(vectors)))
                km = MiniBatchKMeans(n_clusters=n_clusters, random_state=42)
                clusters = km.fit_predict(vectors)
                
                # Filter by cluster
                cluster_results = []
                for i, result in enumerate(filtered_results):
                    if i < len(clusters) and clusters[i] == cluster_id:
                        cluster_results.append(result)
                
                filtered_results = cluster_results
                
                # Log the number of results after clustering
                logger.info(
                    "Found %d results after clustering filter", 
                    len(filtered_results)
                )
        except Exception as exc:
            logger.error("Clustering failed: %s", exc)
    
    # Compute facets for both unfiltered and filtered results
    unfiltered_facets = _compute_facets(full_results)
    filtered_facets = _compute_facets(filtered_results)
    _, timeline = _compute_facets_and_timeline(filtered_results)
    
    # Apply sorting if requested
    if sort_field:
        logger.info("Sorting results by %s (%s)", sort_field, sort_direction)
        try:
            # Special case for score which is at top level of result object
            if sort_field.lower() == 'score':
                logger.info("Using score-specific sorting")
                # Sort by score value (float conversion handles None with default 0)
                filtered_results.sort(
                    key=lambda r: float(r.get("score", 0)),
                    reverse=(sort_direction.lower() == 'desc')
                )
                # Log result
                logger.info("Sorted %d results by score", len(filtered_results))
            # Special handling for date fields
            elif sort_field.lower() in [
                'publication_date', 'date', 
                'created_at', 'updated_at'
            ]:
                from datetime import datetime
                import re
                from dateutil import parser as date_parser
                
                logger.info(
                    "Using date-specific sorting for field: %s", 
                    sort_field
                )
                
                # Custom sort key function for dates with enhanced parsing
                def date_sort_key(result):
                    # Get the date field value
                    metadata = result.get("metadata", {})
                    date_str = metadata.get(sort_field, "")
                    
                    if not date_str:
                        # Return extreme date for empty values
                        return (
                            datetime.min if sort_direction == 'asc' 
                            else datetime.max
                        )
                    
                    # Normalize date string
                    date_str = str(date_str).strip()
                    
                    try:
                        # Try various date parsing methods
                        
                        # Method 1: ISO format (most common)
                        try:
                            # Handle 'Z' UTC indicator 
                            if date_str.endswith('Z'):
                                date_str = date_str[:-1] + '+00:00'
                            return datetime.fromisoformat(date_str)
                        except (ValueError, TypeError):
                            pass
                            
                        # Method 2: Try dateutil parser (flexible format)
                        try:
                            return date_parser.parse(date_str)
                        except (ValueError, TypeError):
                            pass
                            
                        # Method 3: Extract year from string (fallback)
                        year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
                        if year_match:
                            year = int(year_match.group(0))
                            # Set a default month/day in the middle of the year
                            # for a reasonable sort
                            return datetime(year, 6, 15)
                            
                        # If all parsing methods fail
                        logger.warning(
                            "Could not parse date: %s for sorting", 
                            date_str
                        )
                        return (
                            datetime.min if sort_direction == 'asc' 
                            else datetime.max
                        )
                    
                    except Exception as exc:
                        logger.warning(
                            "Date parsing error for '%s': %s", 
                            date_str, exc
                        )
                        return (
                            datetime.min if sort_direction == 'asc' 
                            else datetime.max
                        )
                
                # Sort by date with the enhanced date parser
                filtered_results.sort(
                    key=date_sort_key, 
                    reverse=(sort_direction.lower() == 'desc')
                )
                
                # Log some sample dates for debugging
                if filtered_results and len(filtered_results) > 0:
                    sample_size = min(5, len(filtered_results))
                    sort_dir_text = (
                        "desc" if sort_direction.lower() == "desc" else "asc"
                    )
                    sample_dates = [
                        r.get("metadata", {}).get(sort_field, "?") 
                        for r in filtered_results[:sample_size]
                    ]
                    logger.info(
                        "Sample of sorted dates (%s): %s", 
                        sort_dir_text,
                        sample_dates
                    )
            else:
                # First check if the field exists in the results
                field_exists = False
                for result in filtered_results:
                    meta = result.get("metadata", {})
                    if meta.get(sort_field) is not None:
                        field_exists = True
                        break
                        
                if field_exists:
                    # Regular string sort for non-date fields
                    filtered_results.sort(
                        key=lambda r: r.get("metadata", {}).get(
                            sort_field, ""
                        ),
                        reverse=(sort_direction.lower() == 'desc')
                    )
                    logger.info(
                        "Results sorted successfully by %s", 
                        sort_field
                    )
                else:
                    warning_msg = (
                        "Cannot sort by field '{}' - not found in results"
                    )
                    logger.warning(warning_msg.format(sort_field))
        except Exception as exc:
            logger.error("Error sorting results: %s", exc)
    
    # Calculate impact statistics to show the effect of filters
    comparison = {
        "total_before": len(full_results),
        "total_after": len(filtered_results),
        "facet_impact": {}
    }
    
    # Calculate the impact for each facet, ensure we have facet impact data
    # even when filtered_results is empty
    for field in unfiltered_facets:
        comparison["facet_impact"][field] = {}
        for value, count in unfiltered_facets[field].items():
            filtered_count = filtered_facets.get(field, {}).get(value, 0)
            comparison["facet_impact"][field][value] = {
                "before": count,
                "after": filtered_count,
                "diff": filtered_count - count,
                "pct": round((filtered_count / count * 100) if count else 0, 1)
            }
    
    return {
        "results": filtered_results,
        # Keep showing all available facets
        "facets": unfiltered_facets,  
        # Add filtered facets
        "filtered_facets": filtered_facets,  
        "timeline": timeline,
        # Add impact data
        "comparison": comparison  
    }


def _passes_advanced_constraints(
    result: Dict[str, Any], 
    constraints: List[Constraint]
) -> bool:
    """Check if a result passes advanced constraints not handled by ChromaDB.
    
    Args:
        result: The search result to check
        constraints: The list of constraints to apply
        
    Returns:
        True if the result passes all constraints, False otherwise
    """
    metadata = result.get("metadata", {})
    
    for constraint in constraints:
        field_value = metadata.get(constraint.field)
        
        # Skip constraints that were already handled by ChromaDB
        if constraint.operator == '=':
            continue
        
        # Handle existence check (has:field) operator
        if constraint.operator == 'exists':
            # Log for debugging
            logger.info(
                "Existence check for field %s: exists=%s, value=%s", 
                constraint.field, 
                field_value is not None, 
                field_value
            )
            
            # True means field must exist; False means field must not exist
            if constraint.value:
                # Field must exist and have a non-empty value
                if field_value is None or field_value == '':
                    return False
            else:
                # Field must not exist
                if field_value is not None and field_value != '':
                    return False
            continue
        
        # Skip if field doesn't exist in the result
        if field_value is None:
            continue
        
        # Handle comparison operators
        if constraint.operator == '!=':
            if field_value == constraint.value:
                return False
        elif constraint.operator == '>':
            try:
                if not float(field_value) > float(constraint.value):
                    return False
            except (ValueError, TypeError):
                return False
        elif constraint.operator == '>=':
            try:
                if not float(field_value) >= float(constraint.value):
                    return False
            except (ValueError, TypeError):
                return False
        elif constraint.operator == '<':
            try:
                if not float(field_value) < float(constraint.value):
                    return False
            except (ValueError, TypeError):
                return False
        elif constraint.operator == '<=':
            try:
                if not float(field_value) <= float(constraint.value):
                    return False
            except (ValueError, TypeError):
                return False
        elif constraint.operator == 'range':
            try:
                value = float(field_value)
                min_val = float(constraint.value.get("min", 0))
                max_val = float(constraint.value.get("max", float('inf')))
                if not (min_val <= value <= max_val):
                    return False
            except (ValueError, TypeError, AttributeError):
                return False
        elif constraint.operator == 'in':
            if field_value not in constraint.value:
                return False
    
    return True


def _compute_facets(
    results: List[Dict[str, Any]]
) -> Dict[str, Dict[str, int]]:
    """Compute facets from search results.
    
    Args:
        results: The search results
        
    Returns:
        A dict of facets
    """
    from collections import Counter, defaultdict
    
    facets = defaultdict(Counter)
    
    for result in results:
        metadata = result.get("metadata", {})
        
        # Compute facets - always include these fields
        for field in (
            "topic", "category", "news_source", "driver_type", "sentiment"
        ):
            val = metadata.get(field)
            if val:
                facets[field][str(val)] += 1
    
    return dict(facets)


def _compute_facets_and_timeline(
    results: List[Dict[str, Any]]
) -> tuple:
    """Compute facets and timeline from search results.
    
    Args:
        results: The search results
        
    Returns:
        A tuple of (facets, timeline)
    """
    from collections import Counter, defaultdict
    from datetime import datetime
    
    facets = defaultdict(Counter)
    timeline = defaultdict(Counter)
    
    for result in results:
        metadata = result.get("metadata", {})
        
        # Compute facets - always include these fields even if filtered
        for field in (
            "topic", "category", "news_source", "driver_type", "sentiment"
        ):
            val = metadata.get(field)
            if val:
                facets[field][str(val)] += 1
        
        # Compute timeline
        pub_date = metadata.get("publication_date")
        if pub_date:
            try:
                date_obj = datetime.fromisoformat(str(pub_date))
                date_bucket = date_obj.date().isoformat()
                category = metadata.get("category", "Uncategorized")
                timeline[category][date_bucket] += 1
            except Exception:
                pass
    
    return dict(facets), dict(timeline)


def _extract_vectors_from_results(
    results: List[Dict[str, Any]]
) -> Optional[List[List[float]]]:
    """Extract embedding vectors from search results.
    
    Gets the actual embeddings from ChromaDB for the result IDs.
    
    Args:
        results: The search results
        
    Returns:
        A list of embedding vectors or None if not available
    """
    # No results means no vectors
    if not results:
        return None
    
    try:
        from app.vector_store import _get_collection
        
        # Extract IDs from results
        ids = [result["id"] for result in results]
        
        # Fetch embeddings from ChromaDB
        collection = _get_collection()
        response = collection.get(
            ids=ids,
            include=["embeddings"]
        )
        
        if response and "embeddings" in response and response["embeddings"]:
            return response["embeddings"]
    
    except Exception as exc:
        logger.error("Failed to extract vectors: %s", exc)
    
    return None 