#!/usr/bin/env python3
"""Quick script to check ChromaDB article count."""
import chromadb
import os

# Get the absolute path to chromadb directory
chromadb_path = "/home/orochford/tenants/skunkworkx.aunoo.ai/chromadb"

try:
    # Connect to ChromaDB
    client = chromadb.PersistentClient(path=chromadb_path)

    # Get the articles collection
    collection = client.get_collection("articles")

    # Get count
    count = collection.count()
    print(f"ChromaDB articles collection count: {count}")

except Exception as e:
    print(f"Error: {e}")
    print("Collection may not exist yet or is being reindexed")
