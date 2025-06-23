# Version File Encoding Issue

## Problem Description

The application experienced UTF-16 encoding issues on Linux systems when reading version files. The error occurred because:

1. **Windows**: Version files may be saved with UTF-16 encoding with BOM (Byte Order Mark)
2. **Linux**: The same files transferred to Linux might lose the BOM or be created without it
3. **Python UTF-16 decoder**: Requires a BOM to determine byte order, causing failures on Linux

## Error Message

```
UnicodeError: UTF-16 stream does not start with BOM
```

## Solution

### 1. Updated Code (app/utils/app_info.py)

The `get_version()` function has been enhanced with robust encoding detection:

- **BOM Detection**: Automatically detects UTF-16 LE/BE and UTF-8 BOMs
- **Fallback Encodings**: Tries common encodings (UTF-8, ASCII, Latin1, CP1252)
- **UTF-16 without BOM**: Attempts UTF-16 decoding as last resort
- **Error Handling**: Graceful fallback with detailed logging

### 2. Encoding Fix Script

Created `scripts/fix_version_encoding.py` to:

- Detect current encoding of version files
- Convert UTF-16 files to UTF-8 without BOM
- Clean up any BOM characters or artifacts
- Ensure cross-platform compatibility

### 3. Usage

To fix existing version files:

```bash
# Run from project root
python scripts/fix_version_encoding.py
```

## Prevention

### For Developers

1. **Always save version files as UTF-8** without BOM
2. **Avoid UTF-16 encoding** for simple text files
3. **Test on both Windows and Linux** to ensure compatibility

### For Deployment

1. **Run the encoding fix script** during deployment if needed
2. **Set environment variables** for version info to avoid file dependencies:
   ```bash
   export APP_VERSION="1.6.0"
   export APP_GIT_BRANCH="main"
   export APP_BUILD_DATE="2025-01-15 10:30:00"
   ```

## Technical Details

### BOM (Byte Order Mark)

- **UTF-16 LE**: `FF FE` at file start
- **UTF-16 BE**: `FE FF` at file start  
- **UTF-8**: `EF BB BF` at file start (optional, not recommended)

### File Structure

```
AunooAI/
├── version.txt           # Main version file
├── app/version.txt       # App-specific version
└── scripts/
    └── fix_version_encoding.py  # Encoding fix utility
```

### Environment Variables (Fallback)

The application checks these environment variables first:

- `APP_VERSION`: Application version string
- `APP_GIT_BRANCH`: Git branch name
- `APP_BUILD_DATE`: Build/update timestamp

## Testing

To test the fix:

1. Create a UTF-16 file with/without BOM
2. Run the application on Linux
3. Verify no encoding errors in logs
4. Check that version information displays correctly

## Related Files

- `app/utils/app_info.py`: Main version reading logic
- `scripts/fix_version_encoding.py`: Encoding fix utility
- `version.txt`: Main version file
- `app/version.txt`: App version file 