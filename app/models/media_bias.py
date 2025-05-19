"""Media bias database models and import functions."""

import csv
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from app.database import Database

logger = logging.getLogger(__name__)

class MediaBias:
    """Media bias data management and enrichment."""
    
    def __init__(self, db: Database):
        """Initialize with database connection."""
        self.db = db
        self._ensure_tables()
    
    def _ensure_tables(self) -> None:
        """Ensure the required tables exist in the database."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create media_bias table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mediabias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL UNIQUE,
                    country TEXT,
                    bias TEXT,
                    factual_reporting TEXT,
                    press_freedom TEXT,
                    media_type TEXT,
                    popularity TEXT,
                    mbfc_credibility_rating TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Check if the updated_at column exists, add it if not
            try:
                cursor.execute("PRAGMA table_info(mediabias)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'updated_at' not in columns:
                    logger.info("Adding updated_at column to mediabias table")
                    cursor.execute("""
                        ALTER TABLE mediabias
                        ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    """)
            except Exception as e:
                # Table might not exist yet, which is fine since we're creating it above
                logger.debug(f"Could not check for updated_at column: {str(e)}")
            
            # Create mediabias_settings table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mediabias_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled BOOLEAN DEFAULT 0,
                    last_updated TIMESTAMP,
                    source_file TEXT
                )
            """)
            
            # Insert default settings if not exist
            cursor.execute("""
                INSERT OR IGNORE INTO mediabias_settings (id, enabled, last_updated, source_file)
                VALUES (1, 0, NULL, NULL)
            """)
            
            conn.commit()
    
    def import_from_csv(self, file_path: str) -> Tuple[int, int]:
        """Import media bias data from a CSV file.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            Tuple containing (imported_count, failed_count)
        """
        imported_count = 0
        failed_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)  # Read all rows first
                
                # Begin transaction
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # First try to import the data
                    try:
                        for row in rows:
                            try:
                                # Clean and validate row data
                                source = row.get('source', '').strip()
                                if not source:
                                    logger.warning(f"Skipping row with empty source: {row}")
                                    failed_count += 1
                                    continue
                                
                                # Insert or update media bias data
                                cursor.execute("""
                                    INSERT INTO mediabias (
                                        source, country, bias, factual_reporting,
                                        press_freedom, media_type, popularity,
                                        mbfc_credibility_rating, updated_at
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                                    ON CONFLICT(source) DO UPDATE SET
                                        country = excluded.country,
                                        bias = excluded.bias,
                                        factual_reporting = excluded.factual_reporting,
                                        press_freedom = excluded.press_freedom,
                                        media_type = excluded.media_type,
                                        popularity = excluded.popularity,
                                        mbfc_credibility_rating = excluded.mbfc_credibility_rating,
                                        updated_at = CURRENT_TIMESTAMP
                                """, (
                                    source,
                                    row.get('country', ''),
                                    row.get('bias', ''),
                                    row.get('factual_reporting', ''),
                                    row.get('press_freedom', ''),
                                    row.get('media_type', ''),
                                    row.get('popularity', ''),
                                    row.get('mbfc_credibility_rating', '')
                                ))
                                
                                imported_count += 1
                                
                            except Exception as e:
                                logger.error(f"Error importing row {row}: {str(e)}")
                                failed_count += 1
                                
                    except Exception as table_error:
                        # If we get a table error (like missing column), try to recover
                        logger.warning(f"Table error during import: {str(table_error)}")
                        logger.info("Recreating mediabias table and retrying import")
                        
                        # Drop and recreate the table
                        cursor.execute("DROP TABLE IF EXISTS mediabias")
                        cursor.execute("""
                            CREATE TABLE mediabias (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                source TEXT NOT NULL UNIQUE,
                                country TEXT,
                                bias TEXT,
                                factual_reporting TEXT,
                                press_freedom TEXT,
                                media_type TEXT,
                                popularity TEXT,
                                mbfc_credibility_rating TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        """)
                        
                        # Reset counters
                        imported_count = 0
                        failed_count = 0
                        
                        # Try import again with new table
                        for row in rows:
                            try:
                                source = row.get('source', '').strip()
                                if not source:
                                    logger.warning(f"Skipping row with empty source: {row}")
                                    failed_count += 1
                                    continue
                                
                                cursor.execute("""
                                    INSERT INTO mediabias (
                                        source, country, bias, factual_reporting,
                                        press_freedom, media_type, popularity,
                                        mbfc_credibility_rating, updated_at
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                                """, (
                                    source,
                                    row.get('country', ''),
                                    row.get('bias', ''),
                                    row.get('factual_reporting', ''),
                                    row.get('press_freedom', ''),
                                    row.get('media_type', ''),
                                    row.get('popularity', ''),
                                    row.get('mbfc_credibility_rating', '')
                                ))
                                
                                imported_count += 1
                                
                            except Exception as e:
                                logger.error(f"Error in retry - importing row {row}: {str(e)}")
                                failed_count += 1
                    
                    # Update settings
                    cursor.execute("""
                        UPDATE mediabias_settings
                        SET last_updated = CURRENT_TIMESTAMP,
                            source_file = ?
                        WHERE id = 1
                    """, (os.path.basename(file_path),))
                    
                    conn.commit()
                    
            logger.info(f"Imported {imported_count} sources, failed {failed_count}")
            return imported_count, failed_count
            
        except Exception as e:
            logger.error(f"Error importing from CSV {file_path}: {str(e)}")
            return 0, 0
    
    def get_all_sources(self) -> List[Dict[str, Any]]:
        """Get all media bias sources.
        
        Returns:
            List of dictionaries containing media bias data
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    source, country, bias, factual_reporting,
                    press_freedom, media_type, popularity,
                    mbfc_credibility_rating
                FROM mediabias
                ORDER BY source ASC
            """)
            
            sources = []
            for row in cursor.fetchall():
                sources.append({
                    'source': row[0],
                    'country': row[1],
                    'bias': row[2],
                    'factual_reporting': row[3],
                    'press_freedom': row[4],
                    'media_type': row[5],
                    'popularity': row[6],
                    'mbfc_credibility_rating': row[7]
                })
            
            return sources
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of media bias data.
        
        Returns:
            Dictionary with status information
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get count of sources
            cursor.execute("SELECT COUNT(*) FROM mediabias")
            count = cursor.fetchone()[0]
            
            # Get settings
            cursor.execute("""
                SELECT enabled, last_updated, source_file
                FROM mediabias_settings
                WHERE id = 1
            """)
            row = cursor.fetchone()
            
            if row:
                enabled, last_updated, source_file = row
            else:
                enabled, last_updated, source_file = False, None, None
            
            return {
                'installed': count > 0,
                'count': count,
                'enabled': bool(enabled),
                'last_updated': last_updated,
                'source_file': source_file
            }
    
    def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable media bias enrichment.
        
        Args:
            enabled: True to enable, False to disable
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE mediabias_settings
                    SET enabled = ?
                    WHERE id = 1
                """, (1 if enabled else 0,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting media bias enabled state: {str(e)}")
            return False
    
    def reset(self) -> bool:
        """Reset media bias data by deleting all sources.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete all media bias data
                cursor.execute("DELETE FROM mediabias")
                
                # Reset settings but keep enabled state
                cursor.execute("""
                    UPDATE mediabias_settings
                    SET last_updated = NULL,
                        source_file = NULL
                    WHERE id = 1
                """)
                
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error resetting media bias data: {str(e)}")
            return False
    
    def get_bias_for_source(self, source: str) -> Optional[Dict[str, Any]]:
        """Get media bias data for a specific source.
        
        Args:
            source: The news source to look up
            
        Returns:
            Dictionary with bias data or None if not found
        """
        # First try exact match
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    source, country, bias, factual_reporting,
                    press_freedom, media_type, popularity,
                    mbfc_credibility_rating
                FROM mediabias
                WHERE source = ?
            """, (source,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'source': row[0],
                    'country': row[1],
                    'bias': row[2],
                    'factual_reporting': row[3],
                    'press_freedom': row[4],
                    'media_type': row[5],
                    'popularity': row[6],
                    'mbfc_credibility_rating': row[7]
                }
            
            # If no exact match, try partial match (e.g., domain without subdomain)
            # This is useful for sources like cnn.com vs. edition.cnn.com
            cursor.execute("""
                SELECT 
                    source, country, bias, factual_reporting,
                    press_freedom, media_type, popularity,
                    mbfc_credibility_rating
                FROM mediabias
                WHERE ? LIKE '%' || source || '%'
                ORDER BY LENGTH(source) DESC
                LIMIT 1
            """, (source,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'source': row[0],
                    'country': row[1],
                    'bias': row[2],
                    'factual_reporting': row[3],
                    'press_freedom': row[4],
                    'media_type': row[5],
                    'popularity': row[6],
                    'mbfc_credibility_rating': row[7]
                }
        
        return None
    
    def enrich_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich an article with media bias data.
        
        Args:
            article: The article data to enrich
            
        Returns:
            Article with added bias data if available
        """
        # Check if enrichment is enabled
        status = self.get_status()
        if not status.get('enabled', False):
            return article
        
        # Get the news source
        source = article.get('news_source')
        if not source:
            return article
        
        # Look up bias data
        bias_data = self.get_bias_for_source(source)
        if not bias_data:
            return article
        
        # Add bias data to article
        article['media_bias'] = bias_data
        
        return article
        
    def search_sources(self, query: str = None, bias_filter: str = None, 
                      factual_filter: str = None, country_filter: str = None, 
                      page: int = 1, per_page: int = 20) -> Tuple[List[Dict[str, Any]], int]:
        """Search and filter media bias sources.
        
        Args:
            query: Optional search query for source name
            bias_filter: Optional filter for bias (e.g., 'left', 'right', 'center')
            factual_filter: Optional filter for factual reporting
            country_filter: Optional filter for country
            page: Page number (1-based)
            per_page: Number of items per page
            
        Returns:
            Tuple containing (list of sources, total count)
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build base query
            query_parts = ["SELECT * FROM mediabias WHERE 1=1"]
            params = []
            
            # Add filters
            if query:
                query_parts.append("AND source LIKE ?")
                params.append(f"%{query}%")
                
            if bias_filter:
                query_parts.append("AND bias LIKE ?")
                params.append(f"%{bias_filter}%")
                
            if factual_filter:
                query_parts.append("AND factual_reporting LIKE ?")
                params.append(f"%{factual_filter}%")
                
            if country_filter:
                query_parts.append("AND country LIKE ?")
                params.append(f"%{country_filter}%")
            
            # Get total count first
            count_query = f"SELECT COUNT(*) FROM ({' '.join(query_parts)})"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Add pagination
            query_parts.append("ORDER BY source ASC LIMIT ? OFFSET ?")
            offset = (page - 1) * per_page
            params.extend([per_page, offset])
            
            # Get data
            cursor.execute(' '.join(query_parts), params)
            
            # Format results
            sources = []
            for row in cursor.fetchall():
                sources.append({
                    'id': row[0],
                    'source': row[1],
                    'country': row[2],
                    'bias': row[3],
                    'factual_reporting': row[4],
                    'press_freedom': row[5],
                    'media_type': row[6],
                    'popularity': row[7],
                    'mbfc_credibility_rating': row[8]
                })
            
            return sources, total_count
    
    def add_source(self, source_data: Dict[str, Any]) -> int:
        """Add a new media bias source.
        
        Args:
            source_data: Dictionary with source data
            
        Returns:
            ID of the newly added source
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Validate required fields
                source = source_data.get('source', '').strip()
                if not source:
                    raise ValueError("Source URL is required")
                
                # Insert data
                cursor.execute("""
                    INSERT INTO mediabias (
                        source, country, bias, factual_reporting,
                        press_freedom, media_type, popularity,
                        mbfc_credibility_rating, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    source,
                    source_data.get('country', ''),
                    source_data.get('bias', ''),
                    source_data.get('factual_reporting', ''),
                    source_data.get('press_freedom', ''),
                    source_data.get('media_type', ''),
                    source_data.get('popularity', ''),
                    source_data.get('mbfc_credibility_rating', '')
                ))
                
                # Get the newly inserted ID
                source_id = cursor.lastrowid
                
                # Update last_updated in settings
                cursor.execute("""
                    UPDATE mediabias_settings
                    SET last_updated = CURRENT_TIMESTAMP
                    WHERE id = 1
                """)
                
                conn.commit()
                return source_id
                
        except Exception as e:
            logger.error(f"Error adding source: {str(e)}")
            raise
    
    def update_source(self, source_id: int, source_data: Dict[str, Any]) -> bool:
        """Update an existing media bias source.
        
        Args:
            source_id: ID of the source to update
            source_data: Dictionary with updated source data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Validate source existence
                cursor.execute("SELECT id FROM mediabias WHERE id = ?", (source_id,))
                if not cursor.fetchone():
                    raise ValueError(f"Source with ID {source_id} not found")
                
                # Validate required fields
                source = source_data.get('source', '').strip()
                if not source:
                    raise ValueError("Source URL is required")
                
                # Update data
                cursor.execute("""
                    UPDATE mediabias SET
                        source = ?,
                        country = ?,
                        bias = ?,
                        factual_reporting = ?,
                        press_freedom = ?,
                        media_type = ?,
                        popularity = ?,
                        mbfc_credibility_rating = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    source,
                    source_data.get('country', ''),
                    source_data.get('bias', ''),
                    source_data.get('factual_reporting', ''),
                    source_data.get('press_freedom', ''),
                    source_data.get('media_type', ''),
                    source_data.get('popularity', ''),
                    source_data.get('mbfc_credibility_rating', ''),
                    source_id
                ))
                
                # Update last_updated in settings
                cursor.execute("""
                    UPDATE mediabias_settings
                    SET last_updated = CURRENT_TIMESTAMP
                    WHERE id = 1
                """)
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error updating source: {str(e)}")
            raise
    
    def delete_source(self, source_id: int) -> bool:
        """Delete a media bias source.
        
        Args:
            source_id: ID of the source to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Validate source existence
                cursor.execute("SELECT id FROM mediabias WHERE id = ?", (source_id,))
                if not cursor.fetchone():
                    raise ValueError(f"Source with ID {source_id} not found")
                
                # Delete the source
                cursor.execute("DELETE FROM mediabias WHERE id = ?", (source_id,))
                
                # Update last_updated in settings
                cursor.execute("""
                    UPDATE mediabias_settings
                    SET last_updated = CURRENT_TIMESTAMP
                    WHERE id = 1
                """)
                
                conn.commit()
                
                # Return success if a row was affected
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Error deleting source: {str(e)}")
            raise
    
    def get_source_by_id(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Get a media bias source by ID.
        
        Args:
            source_id: ID of the source to retrieve
            
        Returns:
            Dictionary with source data or None if not found
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT 
                        id, source, country, bias, factual_reporting,
                        press_freedom, media_type, popularity,
                        mbfc_credibility_rating
                    FROM mediabias
                    WHERE id = ?
                """, (source_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                    
                return {
                    'id': row[0],
                    'source': row[1],
                    'country': row[2],
                    'bias': row[3],
                    'factual_reporting': row[4],
                    'press_freedom': row[5],
                    'media_type': row[6],
                    'popularity': row[7],
                    'mbfc_credibility_rating': row[8]
                }
                
        except Exception as e:
            logger.error(f"Error getting source by ID: {str(e)}")
            return None
            
    def get_filter_options(self) -> Dict[str, List[str]]:
        """Get unique options for filter dropdowns.
        
        Returns:
            Dictionary with lists of unique values for each filter
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get unique biases
                cursor.execute("SELECT DISTINCT bias FROM mediabias WHERE bias IS NOT NULL AND bias != ''")
                biases = [row[0] for row in cursor.fetchall()]
                
                # Get unique factual reporting levels
                cursor.execute("SELECT DISTINCT factual_reporting FROM mediabias WHERE factual_reporting IS NOT NULL AND factual_reporting != ''")
                factual_levels = [row[0] for row in cursor.fetchall()]
                
                # Get unique countries
                cursor.execute("SELECT DISTINCT country FROM mediabias WHERE country IS NOT NULL AND country != ''")
                countries = [row[0] for row in cursor.fetchall()]
                
                return {
                    'biases': biases,
                    'factual_levels': factual_levels,
                    'countries': countries
                }
                
        except Exception as e:
            logger.error(f"Error getting filter options: {str(e)}")
            return {'biases': [], 'factual_levels': [], 'countries': []} 