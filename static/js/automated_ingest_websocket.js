/**
 * Automated Ingest WebSocket Client
 * 
 * Provides real-time progress updates for automated article ingestion
 * with a responsive UI that doesn't block the frontend.
 */

class AutoIngestProgressTracker {
    constructor(jobId, options = {}) {
        this.jobId = jobId;
        this.options = {
            reconnectAttempts: 3,
            reconnectDelay: 1000,
            pingInterval: 30000, // 30 seconds
            ...options
        };
        
        this.ws = null;
        this.reconnectCount = 0;
        this.pingTimer = null;
        this.isConnected = false;
        
        this.initializeWebSocket();
    }
    
    initializeWebSocket() {
        const wsUrl = `ws://${window.location.host}/keyword-monitor/ws/bulk-process/${this.jobId}`;
        
        try {
            this.ws = new WebSocket(wsUrl);
            this.setupEventListeners();
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.onError(error);
        }
    }
    
    setupEventListeners() {
        this.ws.onopen = (event) => {
            console.log(`WebSocket connected for job ${this.jobId}`);
            this.isConnected = true;
            this.reconnectCount = 0;
            this.startPingTimer();
            this.onConnectionOpen(event);
        };
        
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
            }
        };
        
        this.ws.onclose = (event) => {
            console.log(`WebSocket connection closed for job ${this.jobId}`);
            this.isConnected = false;
            this.stopPingTimer();
            this.onConnectionClose(event);
            
            // Attempt reconnection if not intentional
            if (!event.wasClean && this.reconnectCount < this.options.reconnectAttempts) {
                this.attemptReconnect();
            }
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.onError(error);
        };
    }
    
    handleMessage(data) {
        const { type, status } = data;
        
        switch (type) {
            case 'direct_message':
                this.handleDirectMessage(data);
                break;
            case 'job_update':
                this.handleJobUpdate(data);
                break;
            default:
                console.log('Received unknown message type:', type, data);
        }
    }
    
    handleDirectMessage(data) {
        if (data.status === 'connected') {
            this.onConnected(data);
        } else if (data.type === 'pong') {
            // Pong received, connection is alive
        }
    }
    
    handleJobUpdate(data) {
        const { status } = data;
        
        switch (status) {
            case 'progress':
                this.onProgress(data);
                break;
            case 'batch_update':
                this.onBatchUpdate(data);
                break;
            case 'completed':
                this.onCompleted(data);
                break;
            case 'error':
                this.onError(data.error || 'Unknown error occurred');
                break;
            default:
                console.log('Received unknown job update status:', status, data);
        }
    }
    
    startPingTimer() {
        this.stopPingTimer();
        this.pingTimer = setInterval(() => {
            if (this.isConnected) {
                this.ping();
            }
        }, this.options.pingInterval);
    }
    
    stopPingTimer() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
    }
    
    ping() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'ping' }));
        }
    }
    
    attemptReconnect() {
        this.reconnectCount++;
        console.log(`Attempting to reconnect (${this.reconnectCount}/${this.options.reconnectAttempts})...`);
        
        setTimeout(() => {
            this.initializeWebSocket();
        }, this.options.reconnectDelay * this.reconnectCount);
    }
    
    close() {
        this.stopPingTimer();
        if (this.ws) {
            this.ws.close();
        }
    }
    
    // Event handlers to be overridden
    onConnectionOpen(event) {
        console.log('WebSocket connection opened');
    }
    
    onConnected(data) {
        console.log('Connected to job updates:', data);
    }
    
    onProgress(data) {
        console.log('Progress update:', data);
        this.updateProgressUI(data);
    }
    
    onBatchUpdate(data) {
        console.log('Batch update:', data);
        this.updateBatchUI(data);
    }
    
    onCompleted(data) {
        console.log('Processing completed:', data);
        this.updateCompletedUI(data);
        this.close();
    }
    
    onConnectionClose(event) {
        console.log('WebSocket connection closed');
    }
    
    onError(error) {
        console.error('Error:', error);
        this.updateErrorUI(error);
    }
    
    // UI Update Methods
    updateProgressUI(data) {
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');
        const progressDetails = document.getElementById('progress-details');
        
        if (progressBar) {
            const percentage = Math.round(data.progress || 0);
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
        }
        
        if (progressText) {
            progressText.textContent = data.message || `${Math.round(data.progress || 0)}% complete`;
        }
        
        if (progressDetails) {
            const processed = data.processed || 0;
            const total = data.total || 0;
            const results = data.results || {};
            
            progressDetails.innerHTML = `
                <div class="row">
                    <div class="col-md-3">
                        <strong>Processed:</strong> ${processed}/${total}
                    </div>
                    <div class="col-md-3">
                        <strong>Approved:</strong> ${results.saved || 0}
                    </div>
                    <div class="col-md-3">
                        <strong>Indexed:</strong> ${results.vector_indexed || 0}
                    </div>
                    <div class="col-md-3">
                        <strong>Errors:</strong> ${results.errors?.length || 0}
                    </div>
                </div>
            `;
        }
    }
    
    updateBatchUI(data) {
        const batchInfo = document.getElementById('batch-info');
        
        if (batchInfo) {
            batchInfo.innerHTML = `
                <div class="alert alert-info">
                    <strong>Batch ${data.batch_completed}/${data.total_batches} completed</strong><br>
                    <small>${data.message}</small>
                </div>
            `;
        }
    }
    
    updateCompletedUI(data) {
        const progressContainer = document.getElementById('progress-container');
        const results = data.results || {};
        
        if (progressContainer) {
            progressContainer.innerHTML = `
                <div class="alert alert-success">
                    <h5><i class="fas fa-check-circle"></i> Processing Completed Successfully!</h5>
                    <div class="row mt-3">
                        <div class="col-md-2">
                            <strong>Processed:</strong><br>
                            <span class="badge badge-primary">${results.processed || 0}</span>
                        </div>
                        <div class="col-md-2">
                            <strong>Approved:</strong><br>
                            <span class="badge badge-success">${results.quality_passed || 0}</span>
                        </div>
                        <div class="col-md-2">
                            <strong>Saved:</strong><br>
                            <span class="badge badge-info">${results.saved || 0}</span>
                        </div>
                        <div class="col-md-2">
                            <strong>Vector Indexed:</strong><br>
                            <span class="badge badge-secondary">${results.vector_indexed || 0}</span>
                        </div>
                        <div class="col-md-2">
                            <strong>Filtered:</strong><br>
                            <span class="badge badge-warning">${(results.processed || 0) - (results.relevant || 0)}</span>
                        </div>
                        <div class="col-md-2">
                            <strong>Errors:</strong><br>
                            <span class="badge badge-danger">${results.errors?.length || 0}</span>
                        </div>
                    </div>
                </div>
            `;
        }
        
        // Re-enable action buttons
        this.enableActionButtons();
    }
    
    updateErrorUI(error) {
        const errorContainer = document.getElementById('error-container');
        
        if (errorContainer) {
            errorContainer.innerHTML = `
                <div class="alert alert-danger">
                    <h5><i class="fas fa-exclamation-triangle"></i> Processing Failed</h5>
                    <p>${error}</p>
                    <button class="btn btn-primary" onclick="location.reload()">Retry</button>
                </div>
            `;
        }
        
        // Re-enable action buttons
        this.enableActionButtons();
    }
    
    enableActionButtons() {
        const buttons = document.querySelectorAll('.btn[disabled]');
        buttons.forEach(btn => btn.removeAttribute('disabled'));
    }
}

// Utility function to start bulk processing with real-time updates
function startBulkProcessingWithProgress(topicId, options = {}) {
    // Disable action buttons
    const buttons = document.querySelectorAll('.btn-process');
    buttons.forEach(btn => btn.setAttribute('disabled', 'disabled'));
    
    // Show progress container
    const progressContainer = document.getElementById('progress-container');
    if (progressContainer) {
        progressContainer.innerHTML = `
            <div class="alert alert-info">
                <h5><i class="fas fa-hourglass-start"></i> Starting Processing...</h5>
                <div class="progress mt-3">
                    <div id="progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" 
                         role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                    </div>
                </div>
                <div id="progress-text" class="mt-2">Initializing...</div>
                <div id="progress-details" class="mt-2"></div>
                <div id="batch-info" class="mt-2"></div>
            </div>
            <div id="error-container"></div>
        `;
    }
    
    // Start the bulk processing request
    fetch('/keyword-monitor/bulk-process-topic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            topic_id: topicId,
            max_articles: options.maxArticles || 100,
            dry_run: options.dryRun || false,
            ...options
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Start WebSocket progress tracking
            const tracker = new AutoIngestProgressTracker(data.job_id);
            
            // Store tracker globally for potential cleanup
            window.currentProgressTracker = tracker;
            
            console.log('Bulk processing started:', data);
        } else {
            throw new Error(data.detail || 'Failed to start bulk processing');
        }
    })
    .catch(error => {
        console.error('Failed to start bulk processing:', error);
        
        const errorContainer = document.getElementById('error-container');
        if (errorContainer) {
            errorContainer.innerHTML = `
                <div class="alert alert-danger">
                    <h5><i class="fas fa-exclamation-triangle"></i> Failed to Start Processing</h5>
                    <p>${error.message}</p>
                    <button class="btn btn-primary" onclick="location.reload()">Retry</button>
                </div>
            `;
        }
        
        // Re-enable buttons
        buttons.forEach(btn => btn.removeAttribute('disabled'));
    });
}

// Cleanup function
window.addEventListener('beforeunload', function() {
    if (window.currentProgressTracker) {
        window.currentProgressTracker.close();
    }
});

// Export for use in other scripts
window.AutoIngestProgressTracker = AutoIngestProgressTracker;
window.startBulkProcessingWithProgress = startBulkProcessingWithProgress; 