#!/usr/bin/env python3
"""
Script to run the Auspex MCP Server.
This provides Model Context Protocol tools for Auspex AI.
"""

import asyncio
import sys
import os
import logging

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.services.mcp_server import AuspexMCPServer

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def main():
    """Run the Auspex MCP server."""
    logger.info("Starting Auspex MCP Server...")
    
    try:
        server = AuspexMCPServer()
        await server.run_stdio()
    except KeyboardInterrupt:
        logger.info("MCP Server stopped by user")
    except Exception as e:
        logger.error(f"MCP Server error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 