import sqlite3
from passlib.context import CryptContext

# Create password context - matches the one used in the application
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def update_admin_password(db_path: str, new_password: str):
    # Hash the password
    hashed_password = pwd_context.hash(new_password)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Update the admin user's password
        cursor.execute(
            "UPDATE users SET password = ? WHERE username = 'admin'",
            (hashed_password,)
        )
        conn.commit()
        print("Admin password updated successfully")
    except Exception as e:
        print(f"Error updating password: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # Update these values as needed
    DB_PATH = "../data/fnaapp.db"
    NEW_PASSWORD = "admin"
    
    update_admin_password(DB_PATH, NEW_PASSWORD) 
