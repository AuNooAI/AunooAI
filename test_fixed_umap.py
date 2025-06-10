#!/usr/bin/env python3
"""
Test the fixed UMAP implementation to verify multi-core processing works.
"""

import time
import numpy as np
import umap
from sklearn.datasets import make_blobs

def test_umap_multicore_fix():
    """Test that UMAP multi-core processing works correctly."""
    print("🧪 Testing UMAP Multi-Core Fix")
    print("=" * 40)
    
    # Generate test data
    n_samples = 1000
    X, _ = make_blobs(n_samples=n_samples, centers=5, n_features=100, random_state=42)
    X = X.astype(np.float32)
    
    print(f"📊 Generated test data: {X.shape}")
    
    # Test configurations
    configs = [
        {
            "name": "Single Core (with random_state)",
            "params": {
                "n_neighbors": 10,
                "min_dist": 0.2,
                "n_epochs": 50,
                "n_jobs": 1,
                "low_memory": False,
                "angular_rp_forest": True,
            },
            "use_random_state": True
        },
        {
            "name": "Multi Core (no random_state)",
            "params": {
                "n_neighbors": 10,
                "min_dist": 0.2,
                "n_epochs": 50,
                "n_jobs": -1,
                "low_memory": False,
                "angular_rp_forest": True,
            },
            "use_random_state": False
        },
        {
            "name": "Multi Core (with random_state - should show warning)",
            "params": {
                "n_neighbors": 10,
                "min_dist": 0.2,
                "n_epochs": 50,
                "n_jobs": -1,
                "low_memory": False,
                "angular_rp_forest": True,
            },
            "use_random_state": True
        }
    ]
    
    for config in configs:
        print(f"\n🔄 Testing {config['name']}...")
        try:
            start_time = time.time()
            
            if config["use_random_state"]:
                reducer = umap.UMAP(
                    n_components=2,
                    metric="cosine",
                    random_state=42,
                    **config["params"]
                )
            else:
                reducer = umap.UMAP(
                    n_components=2,
                    metric="cosine",
                    **config["params"]
                )
            
            coords = reducer.fit_transform(X)
            end_time = time.time()
            
            print(f"✅ {config['name']}: {end_time - start_time:.2f}s")
            print(f"📊 Output shape: {coords.shape}")
            
        except Exception as e:
            print(f"❌ {config['name']} failed: {e}")

def test_optimized_embedding_logic():
    """Test the optimized embedding logic similar to the fixed vector_routes."""
    print("\n🧪 Testing Optimized Embedding Logic")
    print("=" * 40)
    
    # Generate test data
    n_samples = 500
    X, _ = make_blobs(n_samples=n_samples, centers=5, n_features=1536, random_state=42)  # OpenAI embedding size
    X = X.astype(np.float32)
    
    print(f"📊 Generated test data: {X.shape}")
    print(f"💾 Memory usage: {X.nbytes / 1024 / 1024:.1f} MB")
    
    # Simulate the optimized logic from vector_routes
    vecs = X
    dims = 2
    
    # Aggressive UMAP optimization for all dataset sizes
    if len(vecs) < 500:
        # Small datasets: fast but decent quality
        umap_params = {
            "n_neighbors": 15,
            "min_dist": 0.1,
            "n_epochs": 200,
            "n_jobs": -1,
            "low_memory": False,
        }
    elif len(vecs) < 2000:
        # Medium datasets: aggressive speed optimization
        umap_params = {
            "n_neighbors": 10,
            "min_dist": 0.15,
            "n_epochs": 100,
            "n_jobs": -1,
            "low_memory": False,
            "angular_rp_forest": True,
        }
    else:
        # Large datasets: maximum speed
        umap_params = {
            "n_neighbors": 8,
            "min_dist": 0.2,
            "n_epochs": 50,
            "n_jobs": -1,
            "low_memory": False,
            "angular_rp_forest": True,
        }
    
    print(f"⚡ UMAP config for {len(vecs)} vectors: {umap_params}")
    
    # Apply the fixed random_state logic
    start_time = time.time()
    
    if umap_params.get("n_jobs", 1) == 1:
        reducer = umap.UMAP(
            n_components=dims,
            metric="cosine",
            random_state=42,
            **umap_params
        )
        print("🔧 Using single-core with random_state")
    else:
        # Remove random_state for multi-core processing
        reducer = umap.UMAP(
            n_components=dims,
            metric="cosine",
            **umap_params
        )
        print("🔧 Using multi-core without random_state")
    
    coords = reducer.fit_transform(vecs)
    projection_time = time.time() - start_time
    
    print(f"✅ UMAP projection completed in {projection_time:.2f}s")
    print(f"📊 Output shape: {coords.shape}")
    
    # Expected performance for your hardware
    expected_time = 2.0  # seconds
    if projection_time <= expected_time:
        print(f"🎉 Performance GOOD: {projection_time:.2f}s <= {expected_time}s")
    else:
        print(f"⚠️ Performance SLOW: {projection_time:.2f}s > {expected_time}s")

if __name__ == "__main__":
    test_umap_multicore_fix()
    test_optimized_embedding_logic()
    
    print("\n🎉 All tests completed!") 