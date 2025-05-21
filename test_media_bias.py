#!/usr/bin/env python3
"""Test script to verify media bias domain matching."""

import sys
import os
import logging
from app.database import get_database_instance
from app.models.media_bias import MediaBias, normalize_domain

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))


def test_domain_normalize():
    """Test domain normalization function."""
    test_cases = [
        ('www.cnn.com', 'cnn.com'),
        ('https://www.nytimes.com', 'nytimes.com'),
        ('http://sub.domain.example.com/path', 'sub.domain.example.com'),
        ('CNN.com/', 'cnn.com'),
        ('www.bbc.co.uk', 'bbc.co.uk'),
        ('edition.cnn.com', 'edition.cnn.com'),
    ]
    
    print("\n=== Testing Domain Normalization ===")
    for input_domain, expected_output in test_cases:
        actual_output = normalize_domain(input_domain)
        status = "✓" if actual_output == expected_output else "✗"
        print(f"{status} {input_domain:<30} -> {actual_output:<20} "
              f"(Expected: {expected_output})")


def test_domain_matching():
    """Test media bias source matching."""
    # Get database connection
    db = get_database_instance()
    
    # Create MediaBias instance
    media_bias = MediaBias(db)
    
    # Test domains to check
    test_domains = [
        'cnn.com',
        'www.cnn.com',
        'edition.cnn.com',
        'news.bbc.co.uk',
        'bbc.co.uk',
        'nytimes.com',
        'www.nytimes.com',
        'news.google.com',  # Likely won't match 
        'foxnews.com',
        'www.foxnews.com',
        'breitbart.com',
        'huffpost.com',
        'www.huffingtonpost.com',  # Domain variation
        'theguardian.com',
        'reuters.com',
        'apnews.com'
    ]
    
    print("\n=== Testing Media Bias Source Matching ===")
    for domain in test_domains:
        normalized = normalize_domain(domain)
        print(f"\nTesting domain: {domain} (normalized: {normalized})")
        
        bias_data = media_bias.get_bias_for_source(domain)
        
        if bias_data:
            print(f"✓ MATCHED: {bias_data['source']} - "
                  f"Bias: {bias_data.get('bias', 'Unknown')}, "
                  f"Factual: {bias_data.get('factual_reporting', 'Unknown')}")
        else:
            print(f"✗ NO MATCH for {domain}")


if __name__ == "__main__":
    print("=== Media Bias Domain Matching Test ===")
    
    # Test domain normalization
    test_domain_normalize()
    
    # Test media bias source matching
    test_domain_matching() 