@echo off
REM Auspex MCP Server Runner for Windows

echo Starting Auspex MCP Server...

REM Change to project directory
cd /d "%~dp0\.."

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Run the MCP server
python scripts\run_mcp_server.py

pause 