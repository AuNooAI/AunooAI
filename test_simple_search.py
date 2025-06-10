#!/usr/bin/env python3
"""
Simple test to check vector database performance and accessibility.
"""

import time
import logging
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_vector_access():
    """Test basic vector database access."""
    print("🧪 Testing vector database access...")
    
    try:
        # Test basic import
        from app.routes.vector_routes import _fetch_vectors
        print("✅ Successfully imported _fetch_vectors")
        
        # Test vector collection
        start_time = time.time()
        vecs, metas, ids = _fetch_vectors(limit=100)
        fetch_time = time.time() - start_time
        
        print(f"📦 Fetched {len(vecs)} vectors in {fetch_time:.3f}s")
        print(f"📊 Vector shape: {vecs.shape if vecs.size > 0 else 'No vectors'}")
        print(f"🏷️  Metadata count: {len(metas)}")
        print(f"🆔 ID count: {len(ids)}")
        
        if len(vecs) > 0:
            print(f"💾 Memory usage: {vecs.nbytes / 1024 / 1024:.1f} MB")
        
        # Test larger fetch
        if len(vecs) > 0:
            start_time = time.time()
            vecs2, metas2, ids2 = _fetch_vectors(limit=500)
            fetch_time2 = time.time() - start_time
            print(f"📦 Fetched {len(vecs2)} vectors (500 limit) in {fetch_time2:.3f}s")
        
        return len(vecs) > 0
        
    except Exception as e:
        print(f"❌ Error accessing vector database: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_umap_performance():
    """Test UMAP performance with different configurations."""
    print("\n🧪 Testing UMAP performance...")
    
    try:
        import umap
        import numpy as np
        from sklearn.datasets import make_blobs
        
        # Generate test data
        n_samples = 500
        X, _ = make_blobs(n_samples=n_samples, centers=5, n_features=100, random_state=42)
        X = X.astype(np.float32)
        
        print(f"📊 Generated test data: {X.shape}")
        
        # Test different UMAP configurations
        configs = [
            {"name": "Original", "params": {"n_neighbors": 15, "min_dist": 0.1, "n_epochs": 500, "n_jobs": 1}},
            {"name": "Optimized", "params": {"n_neighbors": 10, "min_dist": 0.15, "n_epochs": 100, "n_jobs": -1, "low_memory": False}},
            {"name": "Fast", "params": {"n_neighbors": 8, "min_dist": 0.2, "n_epochs": 50, "n_jobs": -1, "low_memory": False, "angular_rp_forest": True}},
        ]
        
        for config in configs:
            print(f"\n🔄 Testing {config['name']} configuration...")
            try:
                start_time = time.time()
                reducer = umap.UMAP(n_components=2, metric="cosine", random_state=42, **config["params"])
                coords = reducer.fit_transform(X)
                end_time = time.time()
                
                print(f"✅ {config['name']}: {end_time - start_time:.2f}s")
                print(f"📊 Output shape: {coords.shape}")
                
            except Exception as e:
                print(f"❌ {config['name']} failed: {e}")
        
    except ImportError:
        print("❌ UMAP not available")
    except Exception as e:
        print(f"❌ UMAP test failed: {e}")
        import traceback
        traceback.print_exc()

def test_embedding_projection():
    """Test the actual embedding projection endpoint logic."""
    print("\n🧪 Testing embedding projection logic...")
    
    try:
        from app.routes.vector_routes import _fetch_vectors
        import numpy as np
        import time
        
        # Fetch some real vectors
        start_time = time.time()
        vecs, metas, ids = _fetch_vectors(limit=100)
        fetch_time = time.time() - start_time
        
        if vecs.size == 0:
            print("❌ No vectors found in database")
            return
            
        print(f"📦 Fetched {len(vecs)} vectors in {fetch_time:.3f}s")
        
        # Test UMAP projection
        try:
            import umap
            
            # Use fast configuration
            umap_params = {
                "n_neighbors": 8,
                "min_dist": 0.2,
                "n_epochs": 50,
                "n_jobs": -1,
                "low_memory": False,
                "angular_rp_forest": True,
            }
            
            print(f"⚡ Testing UMAP with config: {umap_params}")
            
            start_time = time.time()
            reducer = umap.UMAP(
                n_components=2,
                metric="cosine",
                random_state=42,
                **umap_params
            )
            coords = reducer.fit_transform(vecs.astype(np.float32))
            projection_time = time.time() - start_time
            
            print(f"✅ UMAP projection completed in {projection_time:.2f}s")
            print(f"📊 Output shape: {coords.shape}")
            
        except Exception as e:
            print(f"❌ UMAP projection failed: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"❌ Embedding projection test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Vector Database Performance Test")
    print("=" * 50)
    
    # Test vector database access
    has_vectors = test_vector_access()
    
    if has_vectors:
        # Test UMAP performance with synthetic data
        test_umap_performance()
        
        # Test with real data
        test_embedding_projection()
    else:
        print("⚠️ Skipping UMAP tests - no vectors available")
    
    print("\n🎉 Testing completed!") 