Oliver Rochford 21 October 2024
- Added research.py logger.info statement to print out the extracted publication date to help debug an issue where the date is not successfully extracted
- Fixed an issue on the research page (research.html) with the Clear Button not clearing all data in the Research Form

Oliver Rochford 22 October 2024
- Attempted to resolve 'Session' object has no attribute 'save_raw_article' error in Research class
- Updated Research class initialization to ensure it's using the correct Database instance
- Modified BulkResearch class to use the correct Database instance
- Updated main.py to ensure correct Database instance is passed to Research class
- Issue with 'Session' object persists and requires further investigation
