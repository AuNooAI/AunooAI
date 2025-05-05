"""Tests for the KISSQL operators module."""

import unittest
from app.kissql.operators import (
    apply_equality_constraint,
    apply_inequality_constraint,
    apply_comparison_constraint,
    apply_range_constraint,
    apply_in_constraint,
    apply_existence_constraint,
    apply_proximity_search,
)


class TestKissqlOperators(unittest.TestCase):
    """Test cases for the KISSQL operators."""

    def test_equality_constraint(self):
        """Test equality constraint."""
        metadata = {"category": "AI", "score": 0.5}
        
        # Field exists and matches value
        self.assertTrue(apply_equality_constraint("category", "AI", metadata))
        
        # Field exists but doesn't match value
        self.assertFalse(apply_equality_constraint("category", "ML", metadata))
        
        # Field doesn't exist
        self.assertFalse(apply_equality_constraint("topic", "AI", metadata))

    def test_inequality_constraint(self):
        """Test inequality constraint."""
        metadata = {"category": "AI", "score": 0.5}
        
        # Field exists and doesn't match value
        self.assertTrue(apply_inequality_constraint("category", "ML", metadata))
        
        # Field exists and matches value
        self.assertFalse(apply_inequality_constraint("category", "AI", metadata))
        
        # Field doesn't exist
        self.assertTrue(apply_inequality_constraint("topic", "AI", metadata))

    def test_comparison_constraint(self):
        """Test comparison constraints."""
        metadata = {"score": 0.5, "price": 100, "name": "Test"}
        
        # Numeric comparisons
        self.assertTrue(apply_comparison_constraint("score", 0.4, ">", metadata))
        self.assertTrue(apply_comparison_constraint("score", 0.5, ">=", metadata))
        self.assertFalse(apply_comparison_constraint("score", 0.6, ">", metadata))
        self.assertTrue(apply_comparison_constraint("score", 0.6, "<", metadata))
        self.assertTrue(apply_comparison_constraint("score", 0.5, "<=", metadata))
        self.assertFalse(apply_comparison_constraint("score", 0.4, "<", metadata))
        
        # String comparisons - "Test" is actually > "Snap" in lexicographic order
        self.assertTrue(apply_comparison_constraint("name", "Snap", ">", metadata))
        self.assertFalse(apply_comparison_constraint("name", "Snap", "<", metadata))
        
        # Field doesn't exist
        self.assertFalse(apply_comparison_constraint("rating", 4, ">", metadata))

    def test_range_constraint(self):
        """Test range constraint."""
        metadata = {"score": 0.5, "price": 100}
        
        # Within range
        self.assertTrue(apply_range_constraint("score", 0.4, 0.6, metadata))
        
        # At range boundary
        self.assertTrue(apply_range_constraint("score", 0.5, 0.6, metadata))
        self.assertTrue(apply_range_constraint("score", 0.4, 0.5, metadata))
        
        # Outside range
        self.assertFalse(apply_range_constraint("score", 0.6, 0.7, metadata))
        
        # Only min specified
        self.assertTrue(apply_range_constraint("score", 0.4, None, metadata))
        self.assertFalse(apply_range_constraint("score", 0.6, None, metadata))
        
        # Only max specified
        self.assertTrue(apply_range_constraint("score", None, 0.6, metadata))
        self.assertFalse(apply_range_constraint("score", None, 0.4, metadata))
        
        # Field doesn't exist
        self.assertFalse(apply_range_constraint("rating", 0, 5, metadata))

    def test_in_constraint(self):
        """Test in constraint."""
        metadata = {"category": "AI", "tags": ["ML", "NLP"]}
        
        # Field value in list
        self.assertTrue(apply_in_constraint("category", ["ML", "AI", "CV"], metadata))
        
        # Field value not in list
        self.assertFalse(apply_in_constraint("category", ["ML", "CV"], metadata))
        
        # Field doesn't exist
        self.assertFalse(apply_in_constraint("topic", ["AI", "ML"], metadata))

    def test_existence_constraint(self):
        """Test existence constraint."""
        metadata = {"category": "AI", "score": 0.5, "tags": None}
        
        # Field exists and has value
        self.assertTrue(apply_existence_constraint("category", metadata))
        
        # Field exists but is None
        self.assertFalse(apply_existence_constraint("tags", metadata))
        
        # Field doesn't exist
        self.assertFalse(apply_existence_constraint("topic", metadata))

    def test_proximity_search(self):
        """Test proximity search."""
        text = "Artificial Intelligence is transforming how we work and live."
        
        # Exact phrase
        self.assertTrue(apply_proximity_search(text, "Artificial Intelligence", 1))
        
        # Words within distance
        self.assertTrue(apply_proximity_search(text, "Intelligence transforming", 2))
        
        # Words too far apart
        self.assertFalse(apply_proximity_search(text, "Artificial live", 4))
        
        # Words not in text
        self.assertFalse(apply_proximity_search(text, "machine learning", 5))


if __name__ == "__main__":
    unittest.main() 