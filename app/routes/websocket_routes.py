from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()

class ConnectionManager:
    """Manage WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.job_subscribers: Dict[str, List[str]] = {}  # job_id -> list of connection_ids
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        logger.info(f"WebSocket connection established: {connection_id}")
    
    def disconnect(self, connection_id: str):
        """Remove a WebSocket connection"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            logger.info(f"WebSocket connection closed: {connection_id}")
        
        # Clean up job subscriptions
        for job_id, subscribers in self.job_subscribers.items():
            if connection_id in subscribers:
                subscribers.remove(connection_id)
    
    def subscribe_to_job(self, connection_id: str, job_id: str):
        """Subscribe a connection to job updates"""
        if job_id not in self.job_subscribers:
            self.job_subscribers[job_id] = []
        
        if connection_id not in self.job_subscribers[job_id]:
            self.job_subscribers[job_id].append(connection_id)
            logger.debug(f"Connection {connection_id} subscribed to job {job_id}")
    
    async def send_job_update(self, job_id: str, data: dict):
        """Send update to all subscribers of a job"""
        if job_id not in self.job_subscribers:
            return
        
        message = json.dumps({
            "type": "job_update",
            "job_id": job_id,
            "timestamp": datetime.utcnow().isoformat(),
            **data
        })
        
        # Send to all subscribers
        disconnected = []
        for connection_id in self.job_subscribers[job_id]:
            if connection_id in self.active_connections:
                try:
                    await self.active_connections[connection_id].send_text(message)
                except Exception as e:
                    logger.error(f"Failed to send message to {connection_id}: {e}")
                    disconnected.append(connection_id)
            else:
                disconnected.append(connection_id)
        
        # Clean up disconnected clients
        for connection_id in disconnected:
            self.disconnect(connection_id)
    
    async def send_direct_message(self, connection_id: str, data: dict):
        """Send message directly to a specific connection"""
        if connection_id not in self.active_connections:
            return False
        
        try:
            message = json.dumps({
                "type": "direct_message",
                "timestamp": datetime.utcnow().isoformat(),
                **data
            })
            await self.active_connections[connection_id].send_text(message)
            return True
        except Exception as e:
            logger.error(f"Failed to send direct message to {connection_id}: {e}")
            self.disconnect(connection_id)
            return False

# Global connection manager
manager = ConnectionManager()

@router.websocket("/ws/bulk-process/{job_id}")
async def websocket_bulk_process(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for bulk processing job updates"""
    connection_id = f"bulk_{job_id}_{datetime.utcnow().timestamp()}"
    
    await manager.connect(websocket, connection_id)
    manager.subscribe_to_job(connection_id, job_id)
    
    # Send initial connection confirmation
    await manager.send_direct_message(connection_id, {
        "status": "connected",
        "job_id": job_id,
        "message": f"Connected to job {job_id}"
    })
    
    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                # Handle different client message types
                if message.get("type") == "ping":
                    await manager.send_direct_message(connection_id, {
                        "type": "pong",
                        "message": "Connection alive"
                    })
                elif message.get("type") == "get_status":
                    # Client requesting current job status
                    await manager.send_direct_message(connection_id, {
                        "type": "status_request",
                        "job_id": job_id,
                        "message": "Status request received"
                    })
                
            except json.JSONDecodeError:
                await manager.send_direct_message(connection_id, {
                    "type": "error",
                    "message": "Invalid JSON message"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(connection_id)
    except Exception as e:
        logger.error(f"WebSocket error for {connection_id}: {e}")
        manager.disconnect(connection_id)

@router.websocket("/ws/progress/{topic_id}")
async def websocket_topic_progress(websocket: WebSocket, topic_id: str):
    """WebSocket endpoint for topic-specific progress updates"""
    connection_id = f"topic_{topic_id}_{datetime.utcnow().timestamp()}"
    
    await manager.connect(websocket, connection_id)
    
    # Send initial connection confirmation
    await manager.send_direct_message(connection_id, {
        "status": "connected",
        "topic_id": topic_id,
        "message": f"Connected to topic {topic_id} updates"
    })
    
    try:
        while True:
            # Handle client messages
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                if message.get("type") == "subscribe_job":
                    job_id = message.get("job_id")
                    if job_id:
                        manager.subscribe_to_job(connection_id, job_id)
                        await manager.send_direct_message(connection_id, {
                            "type": "subscribed",
                            "job_id": job_id,
                            "message": f"Subscribed to job {job_id}"
                        })
                
            except json.JSONDecodeError:
                await manager.send_direct_message(connection_id, {
                    "type": "error",
                    "message": "Invalid JSON message"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(connection_id)
    except Exception as e:
        logger.error(f"WebSocket error for {connection_id}: {e}")
        manager.disconnect(connection_id)

# Helper functions for sending updates from other parts of the application

async def send_progress_update(job_id: str, progress_data: dict):
    """Send progress update to all job subscribers"""
    await manager.send_job_update(job_id, {
        "status": "progress",
        **progress_data
    })

async def send_completion_update(job_id: str, results: dict):
    """Send completion update to all job subscribers"""
    await manager.send_job_update(job_id, {
        "status": "completed",
        "results": results
    })

async def send_error_update(job_id: str, error: str):
    """Send error update to all job subscribers"""
    await manager.send_job_update(job_id, {
        "status": "error",
        "error": error
    })

async def send_batch_update(job_id: str, batch_info: dict):
    """Send batch processing update"""
    await manager.send_job_update(job_id, {
        "status": "batch_update",
        **batch_info
    })

# Export the manager for use in other modules
__all__ = ['router', 'manager', 'send_progress_update', 'send_completion_update', 'send_error_update', 'send_batch_update'] 