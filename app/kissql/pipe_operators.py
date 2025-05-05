"""KISSQL Pipe Operators.

This module contains implementations of the pipe operators supported by the
KISSQL language (HEAD, TAIL, SAMPLE).
"""

import random
from typing import Any, Dict, List, Optional


def apply_head_operation(
    results: List[Dict[str, Any]], 
    count: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Apply the HEAD operation to get the first N items.
    
    Args:
        results: The list of results to process
        count: The number of items to return (default: 10)
        
    Returns:
        The first N items in the list
    """
    if not results:
        return []
    
    n = count if count is not None else 10
    return results[:n]


def apply_tail_operation(
    results: List[Dict[str, Any]], 
    count: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Apply the TAIL operation to get the last N items.
    
    Args:
        results: The list of results to process
        count: The number of items to return (default: 10)
        
    Returns:
        The last N items in the list
    """
    if not results:
        return []
    
    n = count if count is not None else 10
    return results[-n:]


def apply_sample_operation(
    results: List[Dict[str, Any]], 
    count: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Apply the SAMPLE operation to get a random sample of N items.
    
    Args:
        results: The list of results to process
        count: The number of items to return (default: 10)
        
    Returns:
        A random sample of N items from the list
    """
    if not results:
        return []
    
    n = count if count is not None else 10
    n = min(n, len(results))
    return random.sample(results, n)


def apply_pipe_operations(
    results: List[Dict[str, Any]],
    pipe_operations: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Apply a series of pipe operations to a result set.
    
    Args:
        results: The list of results to process
        pipe_operations: A list of pipe operations to apply
        
    Returns:
        The processed results after applying all pipe operations
    """
    if not results or not pipe_operations:
        return results
    
    processed_results = results
    
    for op in pipe_operations:
        operation = op.get('operation', '').upper()
        count = op.get('count')
        
        if operation == 'HEAD':
            processed_results = apply_head_operation(processed_results, count)
        elif operation == 'TAIL':
            processed_results = apply_tail_operation(processed_results, count)
        elif operation == 'SAMPLE':
            processed_results = apply_sample_operation(processed_results, count)
    
    return processed_results 