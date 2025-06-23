#!/usr/bin/env python3
"""
Script to fix version file encoding issues.
Converts UTF-16 files to UTF-8 without BOM to prevent Linux compatibility issues.
"""

import os
import sys
import codecs
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def detect_and_fix_encoding(file_path):
    """Detect file encoding and convert to UTF-8 if needed."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return False
        
    try:
        # Read the raw bytes
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            
        # Detect encoding
        if raw_data.startswith(codecs.BOM_UTF16_LE):
            encoding = 'utf-16-le'
            logger.info(f"Detected UTF-16 LE with BOM in {file_path}")
        elif raw_data.startswith(codecs.BOM_UTF16_BE):
            encoding = 'utf-16-be'
            logger.info(f"Detected UTF-16 BE with BOM in {file_path}")
        elif raw_data.startswith(codecs.BOM_UTF8):
            encoding = 'utf-8-sig'
            logger.info(f"Detected UTF-8 with BOM in {file_path}")
        else:
            # Try to decode as UTF-8 first
            try:
                content = raw_data.decode('utf-8')
                logger.info(f"File {file_path} is already UTF-8 encoded")
                return True
            except UnicodeDecodeError:
                pass
                
            # Try other encodings
            for enc in ['ascii', 'latin1', 'cp1252']:
                try:
                    content = raw_data.decode(enc)
                    encoding = enc
                    logger.info(f"Detected {enc} encoding in {file_path}")
                    break
                except UnicodeDecodeError:
                    continue
            else:
                # Last resort: try UTF-16 without BOM
                try:
                    content = raw_data.decode('utf-16')
                    encoding = 'utf-16'
                    logger.info(f"Detected UTF-16 without BOM in {file_path}")
                except UnicodeDecodeError:
                    logger.error(f"Could not detect encoding for {file_path}")
                    return False
        
        # Read the content with detected encoding
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read().strip()
            
        # Clean up content
        content = content.replace('\ufeff', '').replace('\ufffe', '')  # Remove BOM chars
        content = ''.join(c for c in content if c.isprintable() or c.isspace())  # Keep printable chars
        content = content.strip()
        
        # Write back as UTF-8 without BOM
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        logger.info(f"Successfully converted {file_path} to UTF-8 encoding")
        logger.info(f"Content: '{content}'")
        return True
        
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return False

def main():
    """Main function to fix version file encodings."""
    # Get the project root directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..'))
    
    # Version file locations to check
    version_files = [
        os.path.join(project_root, 'version.txt'),
        os.path.join(project_root, 'app', 'version.txt')
    ]
    
    logger.info("Fixing version file encodings...")
    
    success_count = 0
    total_count = 0
    
    for file_path in version_files:
        if os.path.exists(file_path):
            total_count += 1
            logger.info(f"Processing: {file_path}")
            if detect_and_fix_encoding(file_path):
                success_count += 1
        else:
            logger.info(f"File not found (skipping): {file_path}")
    
    logger.info(f"Processed {success_count}/{total_count} files successfully")
    
    if total_count == 0:
        logger.warning("No version files found")
        return 1
    elif success_count == total_count:
        logger.info("All version files processed successfully")
        return 0
    else:
        logger.error("Some version files could not be processed")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 