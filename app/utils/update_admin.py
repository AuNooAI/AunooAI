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
        # Update the admin user's password and set force_password_change
        cursor.execute(
            "UPDATE users SET password = ?, force_password_change = 1 WHERE username = 'admin'",
            (hashed_password,)
        )
        
        # If no rows were updated, create the admin user
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO users (username, password, force_password_change) VALUES ('admin', ?, 1)",
                (hashed_password,)
            )
            
        conn.commit()
        print("Admin password updated successfully and force_password_change set to true")
    except Exception as e:
        print(f"Error updating password: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # Update these values as needed
    DB_PATH = "../data/fnaapp.db"
    NEW_PASSWORD = "admin"
    
    update_admin_password(DB_PATH, NEW_PASSWORD) 
