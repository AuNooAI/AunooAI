"""KISSQL Query Parser.

This module handles tokenizing and parsing of query strings into structured Query objects.
"""

import re
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field


@dataclass
class Token:
    """Represents a token in the query string."""
    
    type: str
    value: str
    position: int


@dataclass
class MetaControl:
    """Represents a meta control in the query."""
    
    name: str
    value: str
    params: List[str] = field(default_factory=list)


@dataclass
class Constraint:
    """Represents a constraint in the query."""
    
    field: str
    operator: str
    value: Any


@dataclass
class Query:
    """Represents a parsed query."""
    
    text: str = ""
    constraints: List[Constraint] = field(default_factory=list)
    meta_controls: List[MetaControl] = field(default_factory=list)
    logic_operators: List[Dict[str, Any]] = field(default_factory=list)
    

# Token patterns
TOKEN_PATTERNS = [
    # Meta controls - these come first now for clarity
    (r'sort:(\w+)(?::(\w+))?', 'META_SORT'),
    (r'limit:(\d+)', 'META_LIMIT'),
    (r'similar:([^\s]+)', 'META_SIMILAR'),
    (r'cluster[=:](\d+)', 'META_CLUSTER'),
    
    # Constraint operators
    (r'(\w+)\s*=\s*"([^"]+)"', 'CONSTRAINT_EQ_QUOTED'),
    (r'(\w+)\s*=\s*(\d+)\.\.(\d+)', 'CONSTRAINT_RANGE'),
    (r'(\w+)\s*=\s*([^\s]+)', 'CONSTRAINT_EQ'),
    (r'(\w+)\s*!=\s*"([^"]+)"', 'CONSTRAINT_NEQ_QUOTED'),
    (r'(\w+)\s*!=\s*([^\s]+)', 'CONSTRAINT_NEQ'),
    (r'(\w+)\s*>=\s*([^\s]+)', 'CONSTRAINT_GTE'),
    (r'(\w+)\s*<=\s*([^\s]+)', 'CONSTRAINT_LTE'),
    (r'(\w+)\s*>\s*([^\s]+)', 'CONSTRAINT_GT'),
    (r'(\w+)\s*<\s*([^\s]+)', 'CONSTRAINT_LT'),
    
    # Logic operators
    (r'\bAND\b', 'LOGIC_AND'),
    (r'\bOR\b', 'LOGIC_OR'), 
    (r'\bNOT\b', 'LOGIC_NOT'),
    
    # Set operations
    (r'in\(([^)]+)\)', 'OP_IN'),
    (r'has:(\w+)', 'OP_HAS'),
    
    # Enhancement
    (r'(\w+)\^(\d+)', 'ENHANCE_BOOST'),
    (r'"([^"]+)"', 'EXACT_PHRASE'),
    (r'"([^"]+)"~(\d+)', 'PROXIMITY_PHRASE'),
    
    # Words
    (r'\b\w+\b', 'WORD'),
    
    # Whitespace (ignored in tokenization)
    (r'\s+', 'WHITESPACE'),
]


def tokenize(query: str) -> List[Token]:
    """Tokenize a query string into individual tokens.
    
    Args:
        query: The query string to tokenize
        
    Returns:
        A list of Token objects
    """
    tokens = []
    position = 0
    
    while position < len(query):
        match = None
        for pattern, token_type in TOKEN_PATTERNS:
            regex = re.compile(pattern)
            match = regex.match(query, position)
            if match:
                if token_type != 'WHITESPACE':  # Skip whitespace
                    tokens.append(Token(
                        type=token_type,
                        value=match.group(0),
                        position=position
                    ))
                position = match.end()
                break
        
        if not match:
            # Skip unrecognized character
            position += 1
    
    return tokens


def parse_query(query_string: str) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """Parse a query string into structured components.
    
    This function is compatible with the old interface to minimize disruption
    during the transition period.
    
    Args:
        query_string: The query string to parse
        
    Returns:
        A tuple of (cleaned_text, metadata, extra_params)
    """
    tokens = tokenize(query_string)
    query = Query()
    cleaned_parts = []
    metadata = {}
    extra = {}
    
    for token in tokens:
        if token.type == 'WORD':
            cleaned_parts.append(token.value)
        elif token.type == 'EXACT_PHRASE':
            # Extract the phrase without quotes
            match = re.match(r'"([^"]+)"', token.value)
            if match:
                # Keep exact phrases in the cleaned text
                cleaned_parts.append(token.value)
        elif token.type == 'PROXIMITY_PHRASE':
            # Keep proximity phrases in the cleaned text
            cleaned_parts.append(token.value)
        elif token.type in ('LOGIC_AND', 'LOGIC_OR', 'LOGIC_NOT'):
            # Keep logic operators in the cleaned text
            cleaned_parts.append(token.value)
        elif token.type == 'ENHANCE_BOOST':
            # Keep boost operators in the cleaned text
            cleaned_parts.append(token.value)
            
        # Process constraints
        elif token.type == 'CONSTRAINT_EQ_QUOTED':
            match = re.match(r'(\w+)\s*=\s*"([^"]+)"', token.value)
            if match:
                field, value = match.groups()
                # For backward compatibility, store in metadata
                metadata[field] = value
                query.constraints.append(
                    Constraint(field=field, operator='=', value=value)
                )
        elif token.type == 'CONSTRAINT_EQ':
            match = re.match(r'(\w+)\s*=\s*([^\s]+)', token.value)
            if match:
                field, value = match.groups()
                # For backward compatibility, store in metadata
                metadata[field] = value
                query.constraints.append(
                    Constraint(field=field, operator='=', value=value)
                )
        elif token.type == 'CONSTRAINT_RANGE':
            match = re.match(r'(\w+)\s*=\s*(\d+)\.\.(\d+)', token.value)
            if match:
                field, min_val, max_val = match.groups()
                # Use 'range' as the operator type for range constraints
                query.constraints.append(
                    Constraint(
                        field=field, 
                        operator='range', 
                        value={"min": int(min_val), "max": int(max_val)}
                    )
                )
        
        # Process meta controls
        elif token.type == 'META_SORT':
            match = re.match(r'sort:(\w+)(?::(\w+))?', token.value)
            if match:
                field = match.group(1)
                direction = match.group(2) or 'asc'
                extra['sort'] = [field, direction]
                query.meta_controls.append(
                    MetaControl(name='sort', value=field, params=[direction])
                )
        elif token.type == 'META_LIMIT':
            match = re.match(r'limit:(\d+)', token.value)
            if match:
                limit = int(match.group(1))
                extra['limit'] = limit
                query.meta_controls.append(
                    MetaControl(name='limit', value=str(limit))
                )
        elif token.type == 'META_CLUSTER':
            match = re.match(r'cluster[=:](\d+)', token.value)
            if match:
                cluster_id = int(match.group(1))
                extra['cluster'] = cluster_id
                # Also add to metadata for backward compatibility
                metadata['cluster'] = match.group(1)
        elif token.type == 'OP_HAS':
            match = re.match(r'has:(\w+)', token.value)
            if match:
                field = match.group(1)
                # Create a constraint with 'exists' operator
                query.constraints.append(
                    Constraint(field=field, operator='exists', value=True)
                )
    
    # Convert cleaned parts back to a string
    cleaned_text = ' '.join(cleaned_parts)
    
    return cleaned_text, metadata, extra


def parse_full_query(query_string: str) -> Query:
    """Parse a query string into a Query object.
    
    Args:
        query_string: The query string to parse
        
    Returns:
        A Query object representing the parsed query
    """
    tokens = tokenize(query_string)
    query = Query(text="")
    text_parts = []
    
    for token in tokens:
        if token.type == 'WORD':
            text_parts.append(token.value)
        elif token.type == 'EXACT_PHRASE':
            # Extract the phrase without quotes
            match = re.match(r'"([^"]+)"', token.value)
            if match:
                # Add to text parts
                text_parts.append(token.value)
        elif token.type == 'PROXIMITY_PHRASE':
            # Add to text parts
            text_parts.append(token.value)
        elif token.type in ('LOGIC_AND', 'LOGIC_OR', 'LOGIC_NOT'):
            text_parts.append(token.value)
            query.logic_operators.append(
                {"type": token.type, "value": token.value}
            )
        elif token.type == 'ENHANCE_BOOST':
            text_parts.append(token.value)
            
        # Process constraints
        elif token.type == 'CONSTRAINT_EQ_QUOTED':
            match = re.match(r'(\w+)\s*=\s*"([^"]+)"', token.value)
            if match:
                field, value = match.groups()
                query.constraints.append(
                    Constraint(field=field, operator='=', value=value)
                )
        elif token.type == 'CONSTRAINT_EQ':
            match = re.match(r'(\w+)\s*=\s*([^\s]+)', token.value)
            if match:
                field, value = match.groups()
                query.constraints.append(
                    Constraint(field=field, operator='=', value=value)
                )
        elif token.type == 'CONSTRAINT_NEQ_QUOTED':
            match = re.match(r'(\w+)\s*!=\s*"([^"]+)"', token.value)
            if match:
                field, value = match.groups()
                query.constraints.append(
                    Constraint(field=field, operator='!=', value=value)
                )
        elif token.type == 'CONSTRAINT_NEQ':
            match = re.match(r'(\w+)\s*!=\s*([^\s]+)', token.value)
            if match:
                field, value = match.groups()
                query.constraints.append(
                    Constraint(field=field, operator='!=', value=value)
                )
        elif token.type == 'CONSTRAINT_GT':
            match = re.match(r'(\w+)\s*>\s*([^\s]+)', token.value)
            if match:
                field, value = match.groups()
                query.constraints.append(
                    Constraint(field=field, operator='>', value=value)
                )
        elif token.type == 'CONSTRAINT_GTE':
            match = re.match(r'(\w+)\s*>=\s*([^\s]+)', token.value)
            if match:
                field, value = match.groups()
                query.constraints.append(
                    Constraint(field=field, operator='>=', value=value)
                )
        elif token.type == 'CONSTRAINT_LT':
            match = re.match(r'(\w+)\s*<\s*([^\s]+)', token.value)
            if match:
                field, value = match.groups()
                query.constraints.append(
                    Constraint(field=field, operator='<', value=value)
                )
        elif token.type == 'CONSTRAINT_LTE':
            match = re.match(r'(\w+)\s*<=\s*([^\s]+)', token.value)
            if match:
                field, value = match.groups()
                query.constraints.append(
                    Constraint(field=field, operator='<=', value=value)
                )
        elif token.type == 'CONSTRAINT_RANGE':
            match = re.match(r'(\w+)\s*=\s*(\d+)\.\.(\d+)', token.value)
            if match:
                field, min_val, max_val = match.groups()
                # Always use 'range' as the operator type for range constraints
                query.constraints.append(
                    Constraint(
                        field=field, 
                        operator='range', 
                        value={"min": int(min_val), "max": int(max_val)}
                    )
                )
                    
        # Process set operations
        elif token.type == 'OP_IN':
            match = re.match(r'in\(([^)]+)\)', token.value)
            if match:
                values = [v.strip() for v in match.group(1).split(',')]
                # This gets attached to the previous constraint
                if query.constraints:
                    last_constraint = query.constraints[-1]
                    last_constraint.operator = 'in'
                    last_constraint.value = values
        
        elif token.type == 'OP_HAS':
            match = re.match(r'has:(\w+)', token.value)
            if match:
                field = match.group(1)
                # Create a constraint with 'exists' operator
                query.constraints.append(
                    Constraint(field=field, operator='exists', value=True)
                )
        
        # Process meta controls
        elif token.type == 'META_SORT':
            match = re.match(r'sort:(\w+)(?::(\w+))?', token.value)
            if match:
                field = match.group(1)
                direction = match.group(2) or 'asc'
                query.meta_controls.append(
                    MetaControl(name='sort', value=field, params=[direction])
                )
        
        elif token.type == 'META_LIMIT':
            match = re.match(r'limit:(\d+)', token.value)
            if match:
                limit = int(match.group(1))
                query.meta_controls.append(
                    MetaControl(name='limit', value=str(limit))
                )
                
        elif token.type == 'META_SIMILAR':
            match = re.match(r'similar:([^\s]+)', token.value)
            if match:
                doc_id = match.group(1)
                query.meta_controls.append(
                    MetaControl(name='similar', value=doc_id)
                )
                
        elif token.type == 'META_CLUSTER':
            match = re.match(r'cluster[=:](\d+)', token.value)
            if match:
                cluster_id = int(match.group(1))
                query.meta_controls.append(
                    MetaControl(name='cluster', value=str(cluster_id))
                )
    
    # Set the query text
    query.text = ' '.join(text_parts)
    
    return query 