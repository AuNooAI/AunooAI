import os
import sys

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from app.security.auth import get_password_hash

# Generate hash for 'admin'
password = "admin"
hashed = get_password_hash(password)
print(f"\nFor password '{password}':")
print(f"Generated hash: {hashed}")
print("\nSQL to update database:")
print(f"UPDATE users SET password = '{hashed}' WHERE username = 'admin';") 