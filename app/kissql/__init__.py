"""KISSQL - Keep It Simple, Stupid Query Language.

A lightweight query language for semantic vector search with ChromaDB.
"""

from app.kissql.parser import parse_query
from app.kissql.executor import execute_query

__all__ = ["parse_query", "execute_query"] 