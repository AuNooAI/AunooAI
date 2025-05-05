"""Tests for the KISSQL pipe operators module."""

import unittest
from app.kissql.pipe_operators import (
    apply_head_operation,
    apply_tail_operation,
    apply_sample_operation,
    apply_pipe_operations,
)


class TestKissqlPipeOperators(unittest.TestCase):
    """Test cases for the KISSQL pipe operators."""

    def setUp(self):
        """Set up test data."""
        self.test_results = [
            {"id": f"item{i}", "metadata": {"value": i}} 
            for i in range(1, 21)
        ]

    def test_head_operation(self):
        """Test HEAD operation."""
        # Default count (10)
        result = apply_head_operation(self.test_results)
        self.assertEqual(10, len(result))
        self.assertEqual("item1", result[0]["id"])
        self.assertEqual("item10", result[9]["id"])
        
        # Specified count
        result = apply_head_operation(self.test_results, 5)
        self.assertEqual(5, len(result))
        self.assertEqual("item1", result[0]["id"])
        self.assertEqual("item5", result[4]["id"])
        
        # Count larger than results
        result = apply_head_operation(self.test_results, 30)
        self.assertEqual(20, len(result))

    def test_tail_operation(self):
        """Test TAIL operation."""
        # Default count (10)
        result = apply_tail_operation(self.test_results)
        self.assertEqual(10, len(result))
        self.assertEqual("item11", result[0]["id"])
        self.assertEqual("item20", result[9]["id"])
        
        # Specified count
        result = apply_tail_operation(self.test_results, 5)
        self.assertEqual(5, len(result))
        self.assertEqual("item16", result[0]["id"])
        self.assertEqual("item20", result[4]["id"])
        
        # Count larger than results
        result = apply_tail_operation(self.test_results, 30)
        self.assertEqual(20, len(result))

    def test_sample_operation(self):
        """Test SAMPLE operation."""
        # Default count (10)
        result = apply_sample_operation(self.test_results)
        self.assertEqual(10, len(result))
        
        # Check that all results are from original set
        for item in result:
            self.assertIn(item, self.test_results)
        
        # Specified count
        result = apply_sample_operation(self.test_results, 5)
        self.assertEqual(5, len(result))
        
        # Count larger than results
        result = apply_sample_operation(self.test_results, 30)
        self.assertEqual(20, len(result))

    def test_pipe_operations_chain(self):
        """Test chaining multiple pipe operations."""
        pipe_ops = [
            {"operation": "HEAD", "count": 15},  # First 15 items
            {"operation": "TAIL", "count": 5},   # Last 5 of those 15
        ]
        
        result = apply_pipe_operations(self.test_results, pipe_ops)
        self.assertEqual(5, len(result))
        self.assertEqual("item11", result[0]["id"])
        self.assertEqual("item15", result[4]["id"])
        
        # Test HEAD -> SAMPLE -> TAIL chain
        pipe_ops = [
            {"operation": "HEAD", "count": 15},    # First 15 items
            {"operation": "SAMPLE", "count": 10},  # Random 10 from those 15
            {"operation": "TAIL", "count": 3},     # Last 3 of those 10
        ]
        
        result = apply_pipe_operations(self.test_results, pipe_ops)
        self.assertEqual(3, len(result))


if __name__ == "__main__":
    unittest.main() 