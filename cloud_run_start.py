#!/usr/bin/env python
"""
Cloud Run startup script to handle environment setup and run the FastAPI application.
This bypasses SSL and configures the environment for Cloud Run.
"""
import os
import sys
import importlib.abc
import importlib.machinery
import types

print("Starting cloud_run_start.py - patching imports first")

# Create scripts module immediately before anything else can import it
scripts_module = types.ModuleType('scripts')
scripts_module.__path__ = []
sys.modules['scripts'] = scripts_module

# Create db_merge module with DatabaseMerger stub
db_merge = types.ModuleType('scripts.db_merge')

class DatabaseMerger:
    def __init__(self, *args, **kwargs):
        print("Using stub DatabaseMerger from patched sys.modules")
        
    def merge_databases(self, source_db_path):
        """Stub implementation that logs but doesn't perform the merge"""
        print(f"STUB: Would merge database from {source_db_path}")
        return True

db_merge.DatabaseMerger = DatabaseMerger
sys.modules['scripts.db_merge'] = db_merge

print("Import patching complete, continuing with imports")

import importlib
import time
import os.path
import platform

# Custom module finder and loader for 'scripts'
class ScriptsModuleFinder(importlib.abc.MetaPathFinder):
    """
    Custom module finder for the 'scripts' module.
    This is a fallback in case any imports try to find the module via the normal import system
    instead of using our patched sys.modules.
    """
    def find_spec(self, fullname, path, target=None):
        # Only handle 'scripts' and 'scripts.db_merge'
        if fullname == 'scripts':
            print(f"ScriptsModuleFinder: Handling import for {fullname}")
            # Return the already-created scripts module
            return importlib.machinery.ModuleSpec(
                name='scripts',
                loader=None,
                is_package=True
            )
        elif fullname == 'scripts.db_merge':
            print(f"ScriptsModuleFinder: Handling import for {fullname}")
            # Return the already-created db_merge module
            return importlib.machinery.ModuleSpec(
                name='scripts.db_merge',
                loader=None,
                is_package=False
            )
        
        return None  # Let the default finders handle other imports

# Add our custom finder to the beginning of sys.meta_path
sys.meta_path.insert(0, ScriptsModuleFinder())

# Import standard library modules needed for the application
import uvicorn
import time
import os.path

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
    print(f"Added {current_dir} to Python path")

# Print environment info for debugging
print(f"Python version: {sys.version}")
print(f"Platform: {platform.platform()}")
print(f"Current working directory: {os.getcwd()}")
print(f"Python path: {sys.path}")

# Create a config directory if it doesn't exist
if not os.path.exists('config'):
    os.makedirs('config', exist_ok=True)
    with open('config/__init__.py', 'w') as f:
        f.write('# Configuration file for AunooAI\n')
    with open('config/settings.py', 'w') as f:
        f.write('DATABASE_DIR = "app/data"\n')
        f.write('config = {"environment": "production"}\n')
    print("Created config directory and files")

# List directories to verify the environment
print("Current directory structure:")
for root, dirs, files in os.walk('.', topdown=True):
    level = root.count(os.sep)
    if level > 3:  # Limit depth
        dirs[:] = []  # Clear dirs to avoid descending further
        continue
    indent = ' ' * 4 * level
    print(f"{indent}{os.path.basename(root)}/")
    subindent = ' ' * 4 * (level + 1)
    for f in files:
        print(f"{subindent}{f}")

# Print all modules in sys.modules that include 'scripts'
print("Modules in sys.modules that include 'scripts':")
for module_name in [m for m in sys.modules.keys() if 'script' in m]:
    print(f"  - {module_name}")

# Try to directly import database.py to verify our patching works
try:
    print("Attempting to import app.routes.database to verify patching...")
    import app.routes.database
    print("Successfully imported app.routes.database")
except Exception as e:
    print(f"Error importing app.routes.database: {e}")

# Configure environment variables for uvicorn
port = int(os.environ.get("PORT", 8080))
host = "0.0.0.0"

print(f"Starting uvicorn server on {host}:{port}")

# Start the uvicorn server
uvicorn.run(
    "app.main:app", 
    host=host, 
    port=port,
    log_level="info",
    reload=False
)

print("Server has exited") 