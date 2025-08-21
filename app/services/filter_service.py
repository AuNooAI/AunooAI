from typing import Optional, Dict, Any
import json
import logging
from app.database import Database

logger = logging.getLogger(__name__)

class FilterService:
    """Service that loads / saves Vantage-Desk filter presets."""

    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _serialise(value: Any) -> Any:
        """Store lists / dicts as JSON strings, leave scalars unchanged."""
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        return value

    @staticmethod
    def _deserialise(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            # try json
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_filters(self, user_key: str, group_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Return the saved filter row for (user_key, group_id) or None."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT * FROM vantage_desk_filters WHERE user_key = ? AND group_id IS ? LIMIT 1""",
                (user_key, group_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            columns = [col[0] for col in cur.description]
            data = dict(zip(columns, row))
            # de-json source_date_combinations
            data['source_date_combinations'] = self._deserialise(data.get('source_date_combinations'))
            return data

    def upsert_filters(self, user_key: str, group_id: Optional[int], payload: Dict[str, Any]) -> bool:
        """Insert or update a filter row for the given user & group."""
        logger.info(f"Upserting filters for user_key={user_key}, group_id={group_id}")
        logger.info(f"Payload: {payload}")
        
        # Prepare values & JSON encode source_date_combinations
        if "source_date_combinations" in payload:
            payload["source_date_combinations"] = self._serialise(payload["source_date_combinations"])

        #prepare placeholders and update params for update query
        placeholders = ", ".join([f"{k} = ?" for k in payload.keys()])
        update_params = [v for k, v in payload.items()]

        payload['user_key'] = user_key
        payload['group_id'] = group_id

        #prepare placeholders and insert params for insert query
        insert_cols = ", ".join(payload.keys())
        insert_values   = ", ".join(["?" for _ in payload.keys()])
        insert_params = list(payload.values())

        logger.info(f"Update SQL: UPDATE vantage_desk_filters SET {placeholders} WHERE user_key = ? AND group_id = ?")
        logger.info(f"Update params: {update_params + [user_key, group_id]}")
        logger.info(f"Insert SQL: INSERT INTO vantage_desk_filters ({insert_cols}) VALUES ({insert_values})")
        logger.info(f"Insert params: {insert_params}")

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            # Try UPDATE first
            cur.execute(
                f"UPDATE vantage_desk_filters SET {placeholders} WHERE user_key = ? AND group_id IS ?",
                update_params + [user_key, group_id],
            )
            logger.info(f"Update rowcount: {cur.rowcount}")
            
            if cur.rowcount == 0:
                # Insert
                cur.execute(
                    f"INSERT INTO vantage_desk_filters ({insert_cols}) VALUES ({insert_values})",
                    insert_params,
                )
                # For insert, check if we got a valid row ID
                success = cur.lastrowid is not None
                logger.info(f"Insert lastrowid: {cur.lastrowid}, success: {success}")
            else:
                # For update, rowcount > 0 means success
                success = cur.rowcount > 0
                logger.info(f"Update success: {success}")
            conn.commit()
            logger.info(f"Upsert operation completed with success: {success}")
            return success
