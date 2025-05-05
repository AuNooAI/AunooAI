"""KISSQL Operators.

This module contains implementations of the various operators supported by the
KISSQL language, such as comparison operators, set operations, and more.
"""

from typing import Any, Dict, List, Optional


def apply_equality_constraint(field: str, value: Any, metadata: Dict[str, Any]) -> bool:
    """Apply equality constraint (field = value).
    
    Args:
        field: The field to check
        value: The expected value
        metadata: The document metadata
        
    Returns:
        True if the constraint is satisfied, False otherwise
    """
    if field not in metadata:
        return False
    return metadata[field] == value


def apply_inequality_constraint(field: str, value: Any, metadata: Dict[str, Any]) -> bool:
    """Apply inequality constraint (field != value).
    
    Args:
        field: The field to check
        value: The value to compare against
        metadata: The document metadata
        
    Returns:
        True if the constraint is satisfied, False otherwise
    """
    if field not in metadata:
        # If field doesn't exist, it's not equal to the value
        return True
    return metadata[field] != value


def apply_comparison_constraint(
    field: str, 
    value: Any, 
    operator: str, 
    metadata: Dict[str, Any]
) -> bool:
    """Apply comparison constraint (>, >=, <, <=).
    
    Args:
        field: The field to check
        value: The value to compare against
        operator: The comparison operator (>, >=, <, <=)
        metadata: The document metadata
        
    Returns:
        True if the constraint is satisfied, False otherwise
    """
    if field not in metadata:
        return False
    
    field_value = metadata[field]
    
    # Try numeric comparison first
    try:
        num_field = float(field_value)
        num_value = float(value)
        
        if operator == '>':
            return num_field > num_value
        elif operator == '>=':
            return num_field >= num_value
        elif operator == '<':
            return num_field < num_value
        elif operator == '<=':
            return num_field <= num_value
        else:
            return False
    except (ValueError, TypeError):
        # Fall back to string comparison if numeric conversion fails
        str_field = str(field_value)
        str_value = str(value)
        
        if operator == '>':
            return str_field > str_value
        elif operator == '>=':
            return str_field >= str_value
        elif operator == '<':
            return str_field < str_value
        elif operator == '<=':
            return str_field <= str_value
        else:
            return False


def apply_range_constraint(
    field: str, 
    min_value: Optional[float], 
    max_value: Optional[float], 
    metadata: Dict[str, Any]
) -> bool:
    """Apply range constraint (min <= field <= max).
    
    Args:
        field: The field to check
        min_value: The minimum value (inclusive)
        max_value: The maximum value (inclusive)
        metadata: The document metadata
        
    Returns:
        True if the constraint is satisfied, False otherwise
    """
    if field not in metadata:
        return False
    
    try:
        field_value = float(metadata[field])
        
        min_ok = True if min_value is None else field_value >= min_value
        max_ok = True if max_value is None else field_value <= max_value
        
        return min_ok and max_ok
    except (ValueError, TypeError):
        # If we can't convert to float, we can't apply range constraint
        return False


def apply_in_constraint(field: str, values: List[Any], metadata: Dict[str, Any]) -> bool:
    """Apply in constraint (field in [values]).
    
    Args:
        field: The field to check
        values: The list of acceptable values
        metadata: The document metadata
        
    Returns:
        True if the constraint is satisfied, False otherwise
    """
    if field not in metadata:
        return False
    
    return metadata[field] in values


def apply_existence_constraint(field: str, metadata: Dict[str, Any]) -> bool:
    """Apply existence constraint (has:field).
    
    Args:
        field: The field to check for existence
        metadata: The document metadata
        
    Returns:
        True if the field exists and is not None, False otherwise
    """
    return field in metadata and metadata[field] is not None


def apply_proximity_search(text: str, phrase: str, distance: int) -> bool:
    """Apply proximity search (phrase~distance).
    
    Checks if the words in the phrase appear within distance of each other.
    
    Args:
        text: The document text to search in
        phrase: The phrase to search for
        distance: The maximum distance between words
        
    Returns:
        True if the phrase is found within the distance, False otherwise
    """
    # This is a simplified implementation that would need to be
    # expanded for a production system
    words = phrase.lower().split()
    text_lower = text.lower()
    
    # Check if all words appear in the text
    if not all(word in text_lower for word in words):
        return False
    
    # Simple proximity check (naive implementation)
    text_words = text_lower.split()
    positions = {}
    
    for i, word in enumerate(text_words):
        if word in words:
            if word not in positions:
                positions[word] = []
            positions[word].append(i)
    
    # Check if all words have at least one occurrence
    if len(positions) != len(words):
        return False
    
    # Check if there are positions where all words appear within distance
    # This is a naive implementation - a proper one would be more complex
    min_positions = [min(positions[word]) for word in words]
    max_positions = [max(positions[word]) for word in words]
    
    return max(max_positions) - min(min_positions) <= distance 