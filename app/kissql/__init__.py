"""KISSQL - Keep It Simple, Stupid Query Language.

A lightweight query language for semantic vector search with ChromaDB.
"""

from app.kissql.parser import parse_query, parse_full_query
from app.kissql.executor import execute_query
from app.kissql.pipe_operators import (
    apply_head_operation,
    apply_tail_operation,
    apply_sample_operation,
    apply_pipe_operations,
)


def extract_and_apply_pipe_operations(query_string, results):
    """Parse a query string for pipe operations and apply them to results.
    
    This utility function can be used by any API endpoint to consistently
    handle pipe operators like HEAD, TAIL, and SAMPLE.
    
    Args:
        query_string: The raw query string that may contain pipe operators
        results: The list of results to filter using pipe operators
        
    Returns:
        The filtered results after applying all pipe operations
    """
    if not query_string or not results:
        return results
        
    # Parse the query to get pipe operations
    parsed_query = parse_full_query(query_string)
    
    # If no pipe operations, return original results
    if not parsed_query.pipe_operations:
        return results
        
    # Convert pipe operations to format expected by apply_pipe_operations
    pipe_ops = []
    for op in parsed_query.pipe_operations:
        pipe_op = {
            'operation': op.operation,
        }
        if op.params and len(op.params) > 0:
            try:
                pipe_op['count'] = int(op.params[0])
            except (ValueError, TypeError):
                pass
        pipe_ops.append(pipe_op)
    
    # Apply pipe operations to the results
    if pipe_ops:
        filtered_results = apply_pipe_operations(results, pipe_ops)
        return filtered_results
    
    return results


__all__ = [
    "parse_query", 
    "parse_full_query", 
    "execute_query",
    "apply_head_operation",
    "apply_tail_operation",
    "apply_sample_operation",
    "apply_pipe_operations",
    "extract_and_apply_pipe_operations",
] 