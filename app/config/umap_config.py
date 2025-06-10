"""
UMAP Configuration and Performance Optimization Settings.

This module contains optimized configurations for different use cases
and performance requirements.
"""

import os
from typing import Dict, Any

# Default optimized UMAP configuration
DEFAULT_UMAP_CONFIG = {
    "n_jobs": -1,  # Use all available CPU cores
    "low_memory": False,  # Use more memory for better performance
    "n_neighbors": 15,  # Optimal balance between speed and quality
    "min_dist": 0.1,  # Slightly larger for faster convergence
    "spread": 1.0,  # Standard spread
    "n_epochs": 200,  # Reduced from default 500 for faster training
    "angular_rp_forest": True,  # Faster random projection forest
    "verbose": False,  # Reduce logging overhead
    "learning_rate": 1.0,  # Optimal learning rate for most cases
    "repulsion_strength": 1.0,  # Standard repulsion
    "negative_sample_rate": 5,  # Reduced for faster training
    "transform_queue_size": 4.0,  # Optimize transform performance
}

# Speed-optimized configuration (aggressive optimizations)
SPEED_UMAP_CONFIG = {
    "n_jobs": -1,
    "low_memory": False,
    "n_neighbors": 10,  # Reduced for speed
    "min_dist": 0.2,  # Larger for faster convergence
    "spread": 1.0,
    "n_epochs": 100,  # Much reduced for speed
    "angular_rp_forest": True,
    "verbose": False,
    "learning_rate": 1.5,  # Higher for faster convergence
    "repulsion_strength": 1.0,
    "negative_sample_rate": 3,  # Reduced for speed
    "transform_queue_size": 8.0,
}

# Quality-optimized configuration (slower but better quality)
QUALITY_UMAP_CONFIG = {
    "n_jobs": -1,
    "low_memory": False,
    "n_neighbors": 30,  # Higher for better quality
    "min_dist": 0.05,  # Smaller for tighter clusters
    "spread": 1.0,
    "n_epochs": 500,  # Default for best quality
    "angular_rp_forest": True,
    "verbose": False,
    "learning_rate": 1.0,
    "repulsion_strength": 1.0,
    "negative_sample_rate": 5,
    "transform_queue_size": 4.0,
}

# Memory-optimized configuration (for large datasets)
MEMORY_UMAP_CONFIG = {
    "n_jobs": -1,
    "low_memory": True,  # Use less memory
    "n_neighbors": 15,
    "min_dist": 0.1,
    "spread": 1.0,
    "n_epochs": 200,
    "angular_rp_forest": True,
    "verbose": False,
    "learning_rate": 1.0,
    "repulsion_strength": 1.0,
    "negative_sample_rate": 5,
    "transform_queue_size": 2.0,  # Smaller queue for memory
}

# Optimized clustering configuration
OPTIMIZED_CLUSTERING_CONFIG = {
    "batch_size": 1000,  # Larger batch size for faster convergence
    "max_iter": 100,  # Reduced iterations for speed
    "n_init": 3,  # Reduced random initializations
    "reassignment_ratio": 0.01,  # Faster convergence
    "random_state": 42,
}

# PCA preprocessing configuration
PCA_CONFIG = {
    "n_components": 30,  # Reduced from 50 for faster clustering
    "random_state": 42,
    "copy": False,  # Avoid unnecessary copying
}

def get_umap_config(mode: str = "default") -> Dict[str, Any]:
    """Get UMAP configuration based on optimization mode.
    
    Args:
        mode: One of "default", "speed", "quality", "memory"
        
    Returns:
        Dictionary with UMAP configuration parameters
    """
    configs = {
        "default": DEFAULT_UMAP_CONFIG,
        "speed": SPEED_UMAP_CONFIG,
        "quality": QUALITY_UMAP_CONFIG,
        "memory": MEMORY_UMAP_CONFIG,
    }
    
    config = configs.get(mode, DEFAULT_UMAP_CONFIG).copy()
    
    # Override with environment variables if set
    if os.getenv("UMAP_N_JOBS"):
        config["n_jobs"] = int(os.getenv("UMAP_N_JOBS"))
    
    if os.getenv("UMAP_N_EPOCHS"):
        config["n_epochs"] = int(os.getenv("UMAP_N_EPOCHS"))
        
    if os.getenv("UMAP_N_NEIGHBORS"):
        config["n_neighbors"] = int(os.getenv("UMAP_N_NEIGHBORS"))
    
    return config

def get_clustering_config() -> Dict[str, Any]:
    """Get optimized clustering configuration."""
    config = OPTIMIZED_CLUSTERING_CONFIG.copy()
    
    # Override with environment variables if set
    if os.getenv("CLUSTERING_BATCH_SIZE"):
        config["batch_size"] = int(os.getenv("CLUSTERING_BATCH_SIZE"))
        
    if os.getenv("CLUSTERING_MAX_ITER"):
        config["max_iter"] = int(os.getenv("CLUSTERING_MAX_ITER"))
    
    return config

def get_pca_config() -> Dict[str, Any]:
    """Get PCA preprocessing configuration."""
    config = PCA_CONFIG.copy()
    
    # Override with environment variables if set
    if os.getenv("PCA_N_COMPONENTS"):
        config["n_components"] = int(os.getenv("PCA_N_COMPONENTS"))
    
    return config

def get_optimal_mode_for_data_size(n_samples: int) -> str:
    """Recommend optimal UMAP mode based on data size.
    
    Args:
        n_samples: Number of data points
        
    Returns:
        Recommended optimization mode
    """
    if n_samples < 500:
        return "quality"  # Small dataset, prioritize quality
    elif n_samples < 2000:
        return "default"  # Medium dataset, balanced approach
    elif n_samples < 5000:
        return "speed"  # Large dataset, prioritize speed
    else:
        return "memory"  # Very large dataset, prioritize memory efficiency

def log_performance_recommendation(n_samples: int, n_features: int) -> str:
    """Generate performance recommendations based on data characteristics.
    
    Args:
        n_samples: Number of data points
        n_features: Number of features/dimensions
        
    Returns:
        Performance recommendation string
    """
    recommendations = []
    
    # Data size recommendations
    if n_samples > 5000:
        recommendations.append("Large dataset detected - consider using 'memory' mode")
    elif n_samples > 2000:
        recommendations.append("Medium-large dataset - 'speed' mode recommended")
    
    # High dimensionality recommendations
    if n_features > 1000:
        recommendations.append("High-dimensional data - PCA preprocessing recommended")
    
    # CPU recommendations
    cpu_count = os.cpu_count() or 1
    if cpu_count >= 8:
        recommendations.append(f"Multi-core system ({cpu_count} CPUs) - n_jobs=-1 optimal")
    elif cpu_count >= 4:
        recommendations.append(f"Quad-core system - good parallelization available")
    else:
        recommendations.append("Limited CPU cores - consider reducing n_epochs")
    
    # Memory recommendations
    if n_samples * n_features > 10_000_000:  # Rough memory threshold
        recommendations.append("Large memory footprint - consider low_memory=True")
    
    return "; ".join(recommendations) if recommendations else "Standard configuration optimal"

# Performance monitoring thresholds
PERFORMANCE_THRESHOLDS = {
    "fast": 5.0,      # Under 5 seconds is fast
    "acceptable": 30.0,  # Under 30 seconds is acceptable
    "slow": 120.0,    # Over 2 minutes is slow
}

def classify_performance(elapsed_time: float) -> str:
    """Classify performance based on elapsed time.
    
    Args:
        elapsed_time: Time taken in seconds
        
    Returns:
        Performance classification: "fast", "acceptable", "slow", or "very_slow"
    """
    if elapsed_time < PERFORMANCE_THRESHOLDS["fast"]:
        return "fast"
    elif elapsed_time < PERFORMANCE_THRESHOLDS["acceptable"]:
        return "acceptable"
    elif elapsed_time < PERFORMANCE_THRESHOLDS["slow"]:
        return "slow"
    else:
        return "very_slow" 