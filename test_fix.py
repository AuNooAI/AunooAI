#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import Database
import traceback

def test_fix():
    db = Database()

    try:
        print("=== Testing Foreign Key Fix ===")

        # Test with invalid user_id (OAuth user not in users table)
        chat_id = db.create_auspex_chat(
            topic="test_fix",
            title="Test Fix",
            user_id="oauth_user@example.com",  # This doesn't exist in users table
            profile_id=None,
            metadata={"test": "fix_verification"}
        )
        print(f"✓ Fix working: Chat created with ID {chat_id}")

        # Test adding message to the chat
        message_id = db.add_auspex_message(
            chat_id=chat_id,
            role="system",
            content="Test message",
            metadata={"test": "fix_verification"}
        )
        print(f"✓ Message added with ID {message_id}")

        # Clean up test data
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM auspex_messages WHERE chat_id = ?", (chat_id,))
        cursor.execute("DELETE FROM auspex_chats WHERE id = ?", (chat_id,))
        conn.commit()
        print(f"✓ Test data cleaned up")

    except Exception as e:
        print(f"✗ Fix failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_fix()
