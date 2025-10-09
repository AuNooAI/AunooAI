"""Media bias database models and import functions."""

import csv
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import sqlite3
from urllib.parse import urlparse

from app.database import Database
from app.database_query_facade import DatabaseQueryFacade

logger = logging.getLogger(__name__)

def normalize_domain(url):
    """Normalize a URL to just its domain, without www. prefix.
    
    Args:
        url: URL or domain to normalize
        
    Returns:
        Normalized domain (lowercased, without www.)
    """
    if not url:
        return ""
    
    # Handle if the URL doesn't have a protocol
    if not url.startswith('http') and not url.startswith('https'):
        # Check if it looks like a domain with slashes or just contains spaces
        if '/' in url and ' ' not in url:
            url = 'https://' + url
        else:
            # This is likely a name, not a URL, so return it cleaned
            return url.lower()
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
            
        return domain
    except Exception as e:
        logger.error(f"Error normalizing domain for {url}: {e}")
        # If can't parse, return the original stripped of protocol and path
        return url.lower()

def domains_match(source_domain, target_domain):
    """Check if two domains match, including subdomain support and missing TLD handling.

    Args:
        source_domain: First domain to compare
        target_domain: Second domain to compare

    Returns:
        True if the domains match, False otherwise
    """
    if not source_domain or not target_domain:
        return False

    source_domain = source_domain.lower()
    target_domain = target_domain.lower()

    # Exact match
    if source_domain == target_domain:
        return True

    # Check if source_domain is a subdomain of target_domain
    if source_domain.endswith('.' + target_domain):
        return True

    # Check if target_domain is a subdomain of source_domain
    if target_domain.endswith('.' + source_domain):
        return True

    # Extract root domain (e.g., "example.com" from "sub.example.com")
    source_parts = source_domain.split('.')
    target_parts = target_domain.split('.')

    # If either domain doesn't have at least 2 parts, use the whole domain
    if len(source_parts) >= 2:
        source_root = '.'.join(source_parts[-2:])
    else:
        source_root = source_domain

    if len(target_parts) >= 2:
        target_root = '.'.join(target_parts[-2:])
    else:
        target_root = target_domain

    # Match on root domains
    if source_root == target_root:
        return True

    # SAFETY NET: Handle missing TLDs (e.g., "westernjournal" vs "westernjournal.com")
    # If one domain has no TLD (single part) and the other does (2+ parts),
    # check if the single-part domain matches the domain name portion
    if len(source_parts) == 1 and len(target_parts) >= 2:
        # source is "westernjournal", target is "westernjournal.com"
        # Check if source matches the domain part of target
        if source_domain == target_parts[-2]:
            logger.debug(f"Matched '{source_domain}' (no TLD) with '{target_domain}' (domain part: {target_parts[-2]})")
            return True

    if len(target_parts) == 1 and len(source_parts) >= 2:
        # target is "westernjournal", source is "westernjournal.com"
        # Check if target matches the domain part of source
        if target_domain == source_parts[-2]:
            logger.debug(f"Matched '{target_domain}' (no TLD) with '{source_domain}' (domain part: {source_parts[-2]})")
            return True

    return False

class MediaBias:
    """Media bias data management and enrichment."""
    
    def __init__(self, db: Database):
        """Initialize with database connection."""
        self.db = db
        self.logger = logging.getLogger(__name__)
        self.sources = self._load_sources()
        logger.info(f"Loaded {len(self.sources)} media bias sources")
        # Enable media bias enrichment by default
        self.set_enabled(True)
    
    def import_from_csv(self, file_path: str) -> Tuple[int, int]:
        """Import media bias data from a CSV file.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            Tuple of (imported_count, failed_count)
        """
        try:
            imported_count = 0
            failed_count = 0
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")
                
            with open(file_path, 'r', encoding='utf-8') as csv_file:
                try:
                    csv_reader = csv.DictReader(csv_file)
                    
                    try:
                        # Process each row in the CSV
                        for row in csv_reader:
                            try:
                                # Skip rows without a source
                                source = row.get('source', '').strip()
                                if not source:
                                    logger.warning(f"Skipping row with empty source: {row}")
                                    failed_count += 1
                                    continue

                                # Insert or update the source with enabled=1 by default
                                # Always ensure sources are enabled when importing
                                self.db.facade.insert_media_bias((
                                    source,
                                    row.get('country', ''),
                                    row.get('bias', ''),
                                    row.get('factual_reporting', ''),
                                    row.get('press_freedom', ''),
                                    row.get('media_type', ''),
                                    row.get('popularity', ''),
                                    row.get('mbfc_credibility_rating', ''),
                                    1
                                ))

                                imported_count += 1

                            except Exception as e:
                                logger.error(f"Error importing row {row}: {str(e)}")
                                failed_count += 1

                    except Exception as table_error:
                        # If we get a table error (like missing column), try to recover
                        logger.warning(f"Table error during import: {str(table_error)}")
                        logger.info("Recreating mediabias table and retrying import")

                        # Reset the file pointer and skip header
                        csv_file.seek(0)
                        next(csv_reader)

                        # Retry processing rows
                        for row in csv_reader:
                            try:
                                # Skip rows without a source
                                source = row.get('source', '').strip()
                                if not source:
                                    logger.warning(f"Skipping row with empty source: {row}")
                                    failed_count += 1
                                    continue

                                # Insert the source with enabled=1 by default
                                self.db.facade.insert_media_bias((
                                    source,
                                    row.get('country', ''),
                                    row.get('bias', ''),
                                    row.get('factual_reporting', ''),
                                    row.get('press_freedom', ''),
                                    row.get('media_type', ''),
                                    row.get('popularity', ''),
                                    row.get('mbfc_credibility_rating', ''),
                                    1
                                ))

                                imported_count += 1

                            except Exception as e:
                                logger.error(f"Error in retry - importing row {row}: {str(e)}")
                                failed_count += 1

                        # Update settings
                        self.db.facade.update_media_bias_settings(file_path)
                            
                    logger.info(f"Imported {imported_count} sources, failed {failed_count}")
                    return imported_count, failed_count
                    
                except Exception as e:
                    logger.error(f"Error reading CSV file: {str(e)}")
                    raise
        except Exception as e:
            logger.error(f"Failed to import media bias data: {str(e)}")
            raise
    
    def get_all_sources(self) -> List[Dict[str, Any]]:
        """Get all media bias sources.
        
        Returns:
            List of dictionaries containing media bias data
        """
        rows = self.db.facade.get_all_media_bias_sources()

        sources = []
        for row in rows:
            sources.append({
                'source': row['source'],
                'country': row['country'],
                'bias': row['bias'],
                'factual_reporting': row['factual_reporting'],
                'press_freedom': row['press_freedom'],
                'media_type': row['media_type'],
                'popularity': row['popularity'],
                'mbfc_credibility_rating': row['mbfc_credibility_rating']
            })

        return sources
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of media bias enrichment.
        
        Returns:
            Dict with status information including enabled flag,
            total sources count, and last updated timestamp
        """
        try:
            # Get settings
            row = self.db.facade.get_media_bias_status()
            if not row:
                return {
                    "enabled": False,
                    "total_sources": 0,
                    "last_updated": None
                }

            enabled, last_updated, source_file = row

            # Get total sources
            total_sources = self.db.facade.get_total_media_bias_sources()

            return {
                "enabled": bool(enabled),
                "total_sources": total_sources,
                "last_updated": last_updated,
                "source_file": source_file
            }
                
        except Exception as e:
            self.logger.error(f"Error getting media bias status: {str(e)}")
            return {
                "enabled": False,
                "total_sources": 0,
                "last_updated": None,
                "error": str(e)
            }
    
    def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable media bias enrichment.
        
        Args:
            enabled: True to enable, False to disable
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.db.facade.enable_media_bias_sources(enabled)

            self.logger.info(
                f"Media bias enrichment {'enabled' if enabled else 'disabled'}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error setting media bias enabled state: {str(e)}")
            return False
    
    def reset(self) -> bool:
        """Reset media bias data by deleting all sources.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.db.facade.reset_media_bias_sources()
            return True
        except Exception as e:
            logger.error(f"Error resetting media bias data: {str(e)}")
            return False
    
    def get_bias_for_source(self, source):
        """Get media bias data for a source.
        
        Args:
            source: Source name or URL.
            
        Returns:
            dict: Media bias data if found, otherwise None.
        """
        if not source:
            return None
            
        self.logger.debug(f"Getting bias data for source: {source}")
            
        # Normalize source
        normalized_source = normalize_domain(source)
        self.logger.debug(f"Normalized source: {normalized_source}")
        
        # Load sources if needed
        if not self.sources:
            self.sources = self._load_sources()
        
        # Debug empty sources
        if not self.sources:
            self.logger.warning("No media bias sources loaded")
            return None
        
        # First try an exact match on normalized source with enabled=1
        for s in self.sources:
            source_domain = normalize_domain(s.get('source', ''))
            if source_domain == normalized_source:
                # Check if source is enabled
                if 'enabled' in s and s['enabled'] == 1:
                    self.logger.debug(f"Found exact match for {normalized_source} using source {source_domain} (enabled)")
                    return s
        
        # Then try domain matching with enabled=1
        for s in self.sources:
            source_domain = normalize_domain(s.get('source', ''))
            if domains_match(source_domain, normalized_source):
                # Check if source is enabled
                if 'enabled' in s and s['enabled'] == 1:
                    self.logger.debug(f"Found domain match for {normalized_source} using source {source_domain} (enabled)")
                    return s
        
        # If no enabled sources found, try again with disabled ones
        # First exact match with disabled sources
        for s in self.sources:
            source_domain = normalize_domain(s.get('source', ''))
            if source_domain == normalized_source:
                self.logger.debug(f"Found exact match for {normalized_source} using source {source_domain} (disabled)")
                # Auto-enable this source for future requests
                try:
                    self.db.facade.enable_media_source(s.get('source'))
                    # Update the current record
                    s['enabled'] = 1
                    self.logger.info(f"Auto-enabled media bias source: {s.get('source')}")
                except Exception as e:
                    self.logger.error(f"Error auto-enabling source {s.get('source')}: {e}")
                return s
                
        # Then domain matching with disabled sources
        for s in self.sources:
            source_domain = normalize_domain(s.get('source', ''))
            if domains_match(source_domain, normalized_source):
                self.logger.debug(f"Found domain match for {normalized_source} using source {source_domain} (disabled)")
                # Auto-enable this source for future requests
                try:
                    self.db.facade.enable_media_source(s.get('source'))
                    # Update the current record
                    s['enabled'] = 1
                    self.logger.info(f"Auto-enabled media bias source: {s.get('source')}")
                except Exception as e:
                    self.logger.error(f"Error auto-enabling source {s.get('source')}: {e}")
                return s

        self.logger.debug(f"No match found for {normalized_source}")
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
        (total_count, rows) = self.db.facade.search_media_bias_sources(
            query,
            bias_filter,
            factual_filter,
            country_filter,
            page,
            per_page
        )
            
        # Format results
        sources = []
        for row in rows:
            sources.append({
                'id': row['id'],
                'source': row['source'],
                'country': row['country'],
                'bias': row['bias'],
                'factual_reporting': row['factual_reporting'],
                'press_freedom': row['press_freedom'],
                'media_type': row['media_type'],
                'popularity': row['popularity'],
                'mbfc_credibility_rating': row['mbfc_credibility_rating']
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
            # Validate required fields
            source = source_data.get('source', '').strip()
            if not source:
                raise ValueError("Source URL is required")

            # Insert data
            source_id = self.db.facade.insert_media_bias((
                source,
                source_data.get('country', ''),
                source_data.get('bias', ''),
                source_data.get('factual_reporting', ''),
                source_data.get('press_freedom', ''),
                source_data.get('media_type', ''),
                source_data.get('popularity', ''),
                source_data.get('mbfc_credibility_rating', ''),
                source_data.get('enabled', 1)
            ))

            # Update last_updated in settings
            self.db.facade.update_media_bias_last_updated()
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
            # Validate source existence
            if not self.db.facade.get_media_bias_source(source_id):
                raise ValueError(f"Source with ID {source_id} not found")

            # Validate required fields
            source = source_data.get('source', '').strip()
            if not source:
                raise ValueError("Source URL is required")

            # Update data
            self.db.facade.update_media_bias_source((
                           source,
                           source_data.get('country', ''),
                           source_data.get('bias', ''),
                           source_data.get('factual_reporting', ''),
                           source_data.get('press_freedom', ''),
                           source_data.get('media_type', ''),
                           source_data.get('popularity', ''),
                           source_data.get('mbfc_credibility_rating', ''),
                           source_data.get('enabled', 1),
                           source_id
                       ))

            # Update last_updated in settings
            self.db.facade.update_media_bias_last_updated()

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
            # Validate source existence
            if not self.db.facade.get_media_bias_source(source_id):
                raise ValueError(f"Source with ID {source_id} not found")

            # Delete the source
            self.db.facade.delete_media_bias_source(source_id)

            # Update last_updated in settings
            # Return success if a row was affected
            return self.db.facade.update_media_bias_last_updated() > 0

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
            row = self.db.facade.get_media_bias_source_by_id(source_id)
            if not row:
                return None

            return {
                'id': row['id'],
                'source': row['source'],
                'country': row['country'],
                'bias': row['bias'],
                'factual_reporting': row['factual_reporting'],
                'press_freedom': row['press_freedom'],
                'media_type': row['media_type'],
                'popularity': row['popularity'],
                'mbfc_credibility_rating': row['mbfc_credibility_rating']
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
            (biases, factual_levels, countries) = self.db.facade.get_media_bias_filter_options()

            return {
                'biases': biases,
                'factual_levels': factual_levels,
                'countries': countries
            }
                
        except Exception as e:
            logger.error(f"Error getting filter options: {str(e)}")
            return {'biases': [], 'factual_levels': [], 'countries': []}
    
    def _load_sources(self):
        """Load media bias sources from the database."""
        try:
            return self.db.facade.load_media_bias_sources_from_database()
        except Exception as e:
            logger.error(f"Error loading media bias sources: {e}")
            return [] 