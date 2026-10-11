"""Tests for the KISSQL parser module."""

import unittest
from app.kissql.parser import (
    tokenize, 
    parse_query, 
    parse_full_query,
)


class TestKissqlParser(unittest.TestCase):
    """Test cases for the KISSQL parser."""

    def test_tokenize(self):
        """Test the tokenize function."""
        query = 'AGI AND cluster=0'
        tokens = tokenize(query)
        
        self.assertEqual(3, len(tokens))
        self.assertEqual('WORD', tokens[0].type)
        self.assertEqual('AGI', tokens[0].value)
        self.assertEqual('LOGIC_AND', tokens[1].type)
        self.assertEqual('AND', tokens[1].value)
        self.assertEqual('META_CLUSTER', tokens[2].type)
        self.assertEqual('cluster=0', tokens[2].value)

    def test_parse_query(self):
        """Test the parse_query function for backward compatibility."""
        query = 'AGI AND cluster=0'
        cleaned, metadata, extra = parse_query(query)
        
        self.assertEqual('AGI AND', cleaned)
        self.assertEqual({'cluster': '0'}, metadata)
        self.assertEqual({'cluster': 0}, extra)

    def test_parse_query_with_quotes(self):
        """Test parsing with quoted values."""
        query = 'AGI AND category="AI Business"'
        cleaned, metadata, extra = parse_query(query)
        
        self.assertEqual('AGI AND', cleaned)
        self.assertEqual({'category': 'AI Business'}, metadata)

    def test_parse_query_with_meta_controls(self):
        """Test parsing with meta controls."""
        query = 'AGI sort:publication_date:desc limit:50'
        cleaned, metadata, extra = parse_query(query)
        
        self.assertEqual('AGI', cleaned)
        self.assertEqual({}, metadata)
        self.assertEqual({'sort': ['publication_date', 'desc'], 'limit': 50}, extra)

    def test_parse_full_query(self):
        """Test the parse_full_query function."""
        query = 'AGI AND category="AI Business" sentiment=positive'
        parsed = parse_full_query(query)
        
        self.assertEqual('AGI AND', parsed.text)
        self.assertEqual(2, len(parsed.constraints))
        self.assertEqual('category', parsed.constraints[0].field)
        self.assertEqual('=', parsed.constraints[0].operator)
        self.assertEqual('AI Business', parsed.constraints[0].value)
        self.assertEqual('sentiment', parsed.constraints[1].field)
        self.assertEqual('=', parsed.constraints[1].operator)
        self.assertEqual('positive', parsed.constraints[1].value)
        
        self.assertEqual(1, len(parsed.logic_operators))
        self.assertEqual('LOGIC_AND', parsed.logic_operators[0]['type'])
        self.assertEqual('AND', parsed.logic_operators[0]['value'])

    def test_comparison_operators(self):
        """Test parsing comparison operators."""
        query = 'score>0.5 AND price<=100'
        parsed = parse_full_query(query)
        
        self.assertEqual(2, len(parsed.constraints))
        self.assertEqual('score', parsed.constraints[0].field)
        self.assertEqual('>', parsed.constraints[0].operator)
        self.assertEqual('0.5', parsed.constraints[0].value)
        self.assertEqual('price', parsed.constraints[1].field)
        self.assertEqual('<=', parsed.constraints[1].operator)
        self.assertEqual('100', parsed.constraints[1].value)

    def test_set_operations(self):
        """Test parsing set operations."""
        query = 'has:price'
        parsed = parse_full_query(query)
        
        # Check if we have an 'exists' constraint
        self.assertTrue(any(c.operator == 'exists' for c in parsed.constraints))
        self.assertEqual('price', parsed.constraints[0].field)

    def test_range_operation(self):
        """Test parsing range operations."""
        query = 'price=10..50'
        parsed = parse_full_query(query)
        
        self.assertEqual(1, len(parsed.constraints))
        self.assertEqual('price', parsed.constraints[0].field)
        self.assertEqual('range', parsed.constraints[0].operator)
        self.assertEqual({'min': 10, 'max': 50}, parsed.constraints[0].value)

    def test_cluster_parameter(self):
        """Test parsing cluster parameter."""
        query = 'AGI AND cluster=0'
        _, _, extra = parse_query(query)
        
        self.assertEqual({'cluster': 0}, extra)
        
        # Also test the alternate format
        query = 'AGI AND cluster:0'
        _, _, extra = parse_query(query)
        
        self.assertEqual({'cluster': 0}, extra)
        
    def test_pipe_operator_tokenization(self):
        """Test tokenizing pipe operators."""
        query = 'AGI | HEAD'
        tokens = tokenize(query)
        
        self.assertEqual(2, len(tokens))
        self.assertEqual('WORD', tokens[0].type)
        self.assertEqual('AGI', tokens[0].value)
        self.assertEqual('PIPE_OP', tokens[1].type)
        self.assertEqual('| HEAD', tokens[1].value)
        
    def test_pipe_operator_with_count(self):
        """Test tokenizing pipe operators with count."""
        query = 'AGI | HEAD 20'
        tokens = tokenize(query)
        
        self.assertEqual(2, len(tokens))
        self.assertEqual('WORD', tokens[0].type)
        self.assertEqual('AGI', tokens[0].value)
        self.assertEqual('PIPE_OP', tokens[1].type)
        self.assertEqual('| HEAD 20', tokens[1].value)
        
    def test_parse_query_with_pipe(self):
        """Test parsing query with pipe operators."""
        query = 'AGI | HEAD 20 | TAIL 5'
        cleaned, metadata, extra = parse_query(query)
        
        self.assertEqual('AGI', cleaned)
        self.assertEqual({}, metadata)
        self.assertTrue('pipe' in extra)
        self.assertEqual(2, len(extra['pipe']))
        self.assertEqual('HEAD', extra['pipe'][0]['operation'])
        self.assertEqual(20, extra['pipe'][0]['count'])
        self.assertEqual('TAIL', extra['pipe'][1]['operation'])
        self.assertEqual(5, extra['pipe'][1]['count'])
        
    def test_parse_full_query_with_pipe(self):
        """Test parse_full_query with pipe operators."""
        query = 'AGI category="AI" | SAMPLE 10'
        parsed = parse_full_query(query)
        
        self.assertEqual('AGI', parsed.text)
        self.assertEqual(1, len(parsed.constraints))
        self.assertEqual('category', parsed.constraints[0].field)
        self.assertEqual('AI', parsed.constraints[0].value)
        self.assertEqual(1, len(parsed.pipe_operations))
        self.assertEqual('SAMPLE', parsed.pipe_operations[0].operation)
        self.assertEqual(['10'], parsed.pipe_operations[0].params)
        
    def test_multiple_pipe_operators(self):
        """Test parsing multiple pipe operators."""
        query = 'AGI | HEAD 50 | SAMPLE 20 | TAIL 10'
        parsed = parse_full_query(query)
        
        self.assertEqual('AGI', parsed.text)
        self.assertEqual(3, len(parsed.pipe_operations))
        self.assertEqual('HEAD', parsed.pipe_operations[0].operation)
        self.assertEqual(['50'], parsed.pipe_operations[0].params)
        self.assertEqual('SAMPLE', parsed.pipe_operations[1].operation)
        self.assertEqual(['20'], parsed.pipe_operations[1].params)
        self.assertEqual('TAIL', parsed.pipe_operations[2].operation)
        self.assertEqual(['10'], parsed.pipe_operations[2].params)


if __name__ == '__main__':
    unittest.main() 