import sqlite3
import json # Needed for _decode_options, though not strictly for update
import logging
import os
from typing import Optional, List, Dict, Any # Added for type hints from original code

# --- Configuration ---
# Adjust this path if your database file is located elsewhere relative to the project root
DB_PATH = os.path.join(os.path.dirname(__file__), 'app/data/fnaapp.db') 
TARGET_KIND = "generation"
BLOCK_NAMES_TO_UPDATE = ["keywords", "relevant tags"] # Case-insensitive check
# --- End Configuration ---

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Included helper from ontology_service for completeness, though not used in main update logic
def _decode_options(raw: Optional[str]) -> Optional[List[str]]:
	if raw:
		try:
			return json.loads(raw)
		except Exception:
			logger.warning("Could not decode options JSON: %s", raw)
	return None

def update_kind_in_db(block_id: int, new_kind: str):
	"""Updates the kind for a specific block ID."""
	conn = None
	try:
		conn = sqlite3.connect(DB_PATH)
		cursor = conn.cursor()
		cursor.execute("UPDATE building_blocks SET kind = ? WHERE id = ?", (new_kind, block_id))
		if cursor.rowcount == 0:
			logger.warning(f"Block ID {block_id} not found for update.")
		else:
			 logger.info(f"Updated kind for block ID {block_id} to '{new_kind}'.")
		conn.commit()
	except sqlite3.Error as e:
		logger.error(f"Database error updating block {block_id}: {e}")
		if conn:
			conn.rollback()
	finally:
		if conn:
			conn.close()

def main():
	"""Finds blocks by name and updates their kind."""
	logger.info(f"Connecting to database at: {DB_PATH}")
	if not os.path.exists(DB_PATH):
		 logger.error(f"Database file not found at {DB_PATH}. Please check the path.")
		 return

	conn = None
	try:
		conn = sqlite3.connect(DB_PATH)
		conn.row_factory = sqlite3.Row
		cursor = conn.cursor()
		# Fetch only necessary columns
		cursor.execute("SELECT id, name, kind FROM building_blocks") 
		blocks = cursor.fetchall()
	except sqlite3.Error as e:
		logger.error(f"Database error listing blocks: {e}")
		return
	finally:
		if conn:
			conn.close()

	if not blocks:
		logger.info("No building blocks found in the database.")
		return

	blocks_updated_count = 0
	block_names_lower = [name.lower() for name in BLOCK_NAMES_TO_UPDATE]

	logger.info(f"Checking {len(blocks)} blocks to potentially update to kind '{TARGET_KIND}'...")

	for block_row in blocks:
		block = dict(block_row) # Convert Row object to dict
		block_id = block.get("id")
		name_lower = block.get("name", "").lower()
		current_kind = block.get("kind", "").lower()

		if name_lower in block_names_lower:
			if current_kind != TARGET_KIND:
				logger.info(f"Found block '{block.get('name')}' (ID: {block_id}) with current kind '{block.get('kind')}'. Updating to '{TARGET_KIND}'.")
				update_kind_in_db(block_id, TARGET_KIND)
				blocks_updated_count += 1
			else:
				logger.info(f"Block '{block.get('name')}' (ID: {block_id}) already has kind '{TARGET_KIND}'. Skipping.")

	if blocks_updated_count == 0:
		logger.info(f"No blocks matching the names {BLOCK_NAMES_TO_UPDATE} required an update.")
	else:
		 logger.info(f"Finished updating {blocks_updated_count} block(s).")

if __name__ == "__main__":
	main()