# Issue: Type Conversion Error in Bulk Research Summary Length Parameter

## Description
When submitting articles for analysis through the bulk research interface, a type conversion error occurs when the `summary_length` parameter is sent as a string value (e.g., 'medium') instead of an integer. This causes the backend to fail with an error message indicating a failure to convert the string to an integer.

## Impact
- Users cannot successfully analyze articles in bulk when using the bulk research interface
- The application fails with a type conversion error
- No analysis results are returned to the user

## Root Cause
The frontend was sending the `summary_length` parameter as a string value (e.g., 'medium') from the dropdown selection, but the backend expected an integer value. This mismatch in data types caused the conversion error.

## Solution Implemented
1. **Frontend Changes**:
   - Updated the `getSummaryLength()` function in `templates/bulk_research.html` to always return an integer value
   - Added proper handling for custom summary length values
   - Implemented a default value of 50 words if a custom value is empty

2. **Backend Changes**:
   - Updated the `analyze_bulk_urls` method in `app/bulk_research.py` to accept `summary_length` as an integer
   - Removed unnecessary `int()` conversion since the value is now already an integer
   - Added proper type hints for better code clarity

3. **API Route Changes**:
   - Added validation and conversion of the `summary_length` parameter in the FastAPI route
   - Set a default value of 50 words if no value is provided
   - Added error handling for invalid values

## Files Modified
- `templates/bulk_research.html`
- `app/bulk_research.py`
- `app/main.py`

## Testing
- Verified that the frontend now sends integer values for `summary_length`
- Confirmed that the backend properly processes the integer values
- Tested with various summary length options including custom values
- Ensured that the analysis process completes successfully

## Related Issues
- None

## Additional Notes
This fix ensures type consistency between the frontend and backend, preventing conversion errors and improving the robustness of the bulk research functionality. 