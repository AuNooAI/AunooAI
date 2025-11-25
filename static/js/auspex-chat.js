class FloatingChat {
    constructor() {
        console.log('FloatingChat constructor called');
        this.elements = {
            button: document.getElementById('floatingChatBtn'),
            modal: document.getElementById('floatingChatModal'),
            topicSelect: document.getElementById('floatingTopicSelect'),
            modelSelect: document.getElementById('floatingModelSelect'),
            sampleSizeMode: document.getElementById('floatingSampleSizeMode'),
            customLimit: document.getElementById('floatingCustomLimit'),
            messages: document.getElementById('floatingChatMessages'),
            input: document.getElementById('floatingChatInput'),
            sendBtn: document.getElementById('floatingChatSend'),
            saveBtn: document.getElementById('floatingChatSave'),
            loading: document.getElementById('floatingChatLoading'),
            clearBtn: document.getElementById('clearChatBtn'),
            exportBtn: document.getElementById('exportChatBtn'),
            toggleSidebar: document.getElementById('toggleSidebar'),
            quickQueries: document.getElementById('floatingQuickQueries'),
            sidebar: document.getElementById('chatSidebar'),
            sessionsList: document.getElementById('chatSessionsList'),
            promptEditBtn: document.getElementById('promptEditBtn'),
            expandWindowBtn: document.getElementById('expandWindowBtn'),
            toolsConfigBtn: document.getElementById('toolsConfigBtn'),
            contextInfo: document.getElementById('contextInfo'),
            contextStats: document.getElementById('contextStats'),
            toolsConfigModal: document.getElementById('toolsConfigModal')
        };
        
        // Chat state
        this.currentChatId = null;
        this.chatSessions = [];
        this.isStreaming = false;
        this.modalInstance = null;
        this.researchMode = false;
        this.researchInProgress = false;
        
        this.storageKeys = {
            topic: 'auspex_floating_last_topic',
            model: 'auspex_floating_last_model',
            sampleSizeMode: 'auspex_floating_sample_size_mode',
            customLimit: 'auspex_floating_custom_limit',
            customQueries: 'auspex_floating_custom_queries',
            minimized: 'auspex_floating_minimized',
            toolsConfig: 'auspex_floating_tools_config',
            researchMode: 'auspex_floating_research_mode'
        };
        
        this.customQueries = this.loadCustomQueries();
        this.isMinimized = localStorage.getItem(this.storageKeys.minimized) === 'true';
        this.toolsConfig = this.loadToolsConfig();
        
        // Context window estimation with optimization-aware limits
        this.contextLimits = {
            'gpt-3.5-turbo': 16385,
            'gpt-3.5-turbo-16k': 16385,
            'gpt-4': 8192,
            'gpt-4-32k': 32768,
            'gpt-4-turbo': 128000,
            'gpt-4-turbo-preview': 128000,
            'gpt-4o': 128000,
            'gpt-4o-mini': 128000,
            'gpt-4.1': 1000000,  // 1M context window
            'gpt-4.1-mini': 1000000,  // 1M context window
            'gpt-4.1-nano': 1000000,  // 1M context window
            'claude-3-opus': 200000,
            'claude-3-sonnet': 200000,
            'claude-3-haiku': 200000,
            'claude-3.5-sonnet': 200000,
            'claude-4': 200000,
            'claude-4-opus': 200000,
            'claude-4-sonnet': 200000,
            'claude-4-haiku': 200000,
            'gemini-pro': 32768,
            'gemini-1.5-pro': 2097152,
            'llama-2-70b': 4096,
            'llama-3-70b': 8192,
            'mixtral-8x7b': 32768,
            'default': 16385
        };
        
        // Optimization factors for different query types
        this.optimizationFactors = {
            'trend_analysis': {
                compression_ratio: 0.6,  // 40% reduction through compression
                diversity_ratio: 0.7,    // 30% reduction through diversity filtering
                format_efficiency: 0.8   // 20% reduction through optimized formatting
            },
            'detailed_analysis': {
                compression_ratio: 0.7,
                diversity_ratio: 0.8,
                format_efficiency: 0.9
            },
            'quick_summary': {
                compression_ratio: 0.5,
                diversity_ratio: 0.6,
                format_efficiency: 0.7
            },
            'comprehensive': {
                compression_ratio: 0.65,
                diversity_ratio: 0.75,
                format_efficiency: 0.85
            }
        };
        
        console.log('Initializing chat...');
        this.init();
    }

    async init() {
        try {
            console.log('Starting initialization...');
            
            // Initialize modal instance
            if (this.elements.modal) {
                this.modalInstance = new bootstrap.Modal(this.elements.modal, {
                    backdrop: true,
                    keyboard: true
                });
                
                // Add modal event listeners
                this.elements.modal.addEventListener('shown.bs.modal', () => {
                    console.log('Modal shown, checking elements again...');
                    setTimeout(() => {
                        this.initializeAfterModalShow();
                    }, 200);
                });
                
                this.elements.modal.addEventListener('hidden.bs.modal', () => {
                    console.log('Modal hidden');
                });
            }
            
            // Check if all required elements are present
            const missingElements = [];
            Object.entries(this.elements).forEach(([key, element]) => {
                if (!element) {
                    missingElements.push(key);
                }
            });
            
            if (missingElements.length > 0) {
                console.warn('Missing elements:', missingElements);
            }
            
            await this.initializeDropdowns();
            this.loadSavedSelections();
            this.addEventListeners();
            this.updateUIState();
            console.log('Initialization complete');
        } catch (error) {
            console.error('Error initializing chat:', error);
        }
    }
    
    initializeAfterModalShow() {
        console.log('Reinitializing elements after modal show...');
        
        // Re-check all elements that might not have been available initially
        const elementIds = {
            sessionsList: 'chatSessionsList',
            sidebar: 'chatSidebar',
            toggleSidebar: 'toggleSidebar',
            input: 'floatingChatInput',
            sendBtn: 'floatingChatSend',
            saveBtn: 'floatingChatSave',
            clearBtn: 'clearChatBtn',
            exportBtn: 'exportChatBtn',
            quickQueries: 'floatingQuickQueries',
            promptEditBtn: 'promptEditBtn',
            expandWindowBtn: 'expandWindowBtn'
        };
        
        let foundCount = 0;
        Object.entries(elementIds).forEach(([key, id]) => {
            if (!this.elements[key]) {
                this.elements[key] = document.getElementById(id);
                if (this.elements[key]) {
                    console.log(`Found missing element: ${key}`);
                    foundCount++;
                } else {
                    console.warn(`Still missing element: ${key} (${id})`);
                }
            } else {
                foundCount++;
            }
        });
        
        console.log(`Found ${foundCount}/${Object.keys(elementIds).length} elements`);

        // Update UI state now that elements are available
        this.updateUIState();

        // Initialize research mode toggle button
        this.initResearchModeToggle();
        
        // Check for pending chat switch from insights research
        if (window.pendingChatSwitch) {
            console.log(`Processing pending chat switch to session ${window.pendingChatSwitch}`);
            const chatId = window.pendingChatSwitch;
            window.pendingChatSwitch = null; // Clear the pending switch
            
            setTimeout(async () => {
                try {
                    // Refresh chat sessions list to include the new research session
                    const topic = this.elements.topicSelect?.value || 'AI and Machine Learning';
                    await this.loadChatSessions(topic);
                    this.updateSessionsList();
                    
                    // Switch to the research chat
                    await this.switchToChat(chatId);
                    console.log(`Successfully switched to research chat session ${chatId}`);
                } catch (error) {
                    console.error('Error switching to pending research chat:', error);
                }
            }, 500); // Give more time for processing
        }
    }
    
    retryElementInitialization() {
        console.log('Retrying element initialization...');
        
        // Try to find critical elements again
        if (!this.elements.sessionsList) {
            this.elements.sessionsList = document.getElementById('chatSessionsList');
        }
        if (!this.elements.sidebar) {
            this.elements.sidebar = document.getElementById('chatSidebar');
        }
        if (!this.elements.toggleSidebar) {
            this.elements.toggleSidebar = document.getElementById('toggleSidebar');
        }
        if (!this.elements.expandWindowBtn) {
            this.elements.expandWindowBtn = document.getElementById('expandWindowBtn');
        }
        if (!this.elements.promptEditBtn) {
            this.elements.promptEditBtn = document.getElementById('promptEditBtn');
        }
        
        if (this.elements.sessionsList && this.elements.sidebar) {
            console.log('Critical elements found on retry!');
            
            this.updateUIState();
        } else {
            console.warn('Critical elements still not found after retry');
            this.debugModalContent();
        }
    }
    
    debugModalContent() {
        console.log('=== DEBUGGING MODAL CONTENT ===');
        
        // Check if modal exists and is visible
        if (this.elements.modal) {
            console.log('Modal element exists:', this.elements.modal);
            console.log('Modal classes:', this.elements.modal.className);
            console.log('Modal style display:', this.elements.modal.style.display);
        }
        
        // Check for the modal body
        const modalBody = document.querySelector('.chat-modal .modal-body');
        if (modalBody) {
            console.log('Modal body found:', modalBody);
            
            // Look for our specific elements
            const searchIds = ['chatSessionsList', 'chatSidebar', 'toggleSidebar'];
            searchIds.forEach(id => {
                const element = modalBody.querySelector(`#${id}`);
                console.log(`Looking for #${id}:`, element ? 'FOUND' : 'NOT FOUND');
                if (!element) {
                    // Try looking anywhere in the document
                    const globalElement = document.getElementById(id);
                    console.log(`Global search for #${id}:`, globalElement ? 'FOUND' : 'NOT FOUND');
                }
            });
            
            // Show the modal body structure
            console.log('Modal body innerHTML preview:', modalBody.innerHTML.substring(0, 500) + '...');
        } else {
            console.log('Modal body not found');
        }
        
        console.log('=== END DEBUG ===');
    }

    async initializeDropdowns() {
        try {
            console.log('Initializing dropdowns...');
            
            // Fetch topics
            const topicsResponse = await fetch('/api/topics');
            if (!topicsResponse.ok) {
                throw new Error(`Topics API returned status: ${topicsResponse.status}`);
            }
            const topics = await topicsResponse.json();
            console.log('Fetched topics:', topics);
            
            // Clear existing options except the first one
            while (this.elements.topicSelect.options.length > 1) {
                this.elements.topicSelect.remove(1);
            }
            
            // Add topic options
            topics.forEach(topic => {
                const option = document.createElement('option');
                option.value = topic.name;
                option.textContent = topic.name;
                this.elements.topicSelect.appendChild(option);
            });

            // Fetch models
            const modelsResponse = await fetch('/api/models');
            if (!modelsResponse.ok) {
                throw new Error(`Models API returned status: ${modelsResponse.status}`);
            }
            const models = await modelsResponse.json();
            console.log('Fetched models:', models);
            
            // Clear existing options except the first one
            while (this.elements.modelSelect.options.length > 1) {
                this.elements.modelSelect.remove(1);
            }
            
            // Add model options
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.name;
                option.textContent = `${model.name} (${model.provider})`;
                this.elements.modelSelect.appendChild(option);
            });
        } catch (error) {
            console.error('Error initializing dropdowns:', error);
            this.elements.topicSelect.innerHTML = '<option value="">Error loading topics</option>';
            this.elements.modelSelect.innerHTML = '<option value="">Error loading models</option>';
        }
    }

    loadSavedSelections() {
        const savedTopic = localStorage.getItem(this.storageKeys.topic);
        if (savedTopic) {
            this.elements.topicSelect.value = savedTopic;
        }

        const savedModel = localStorage.getItem(this.storageKeys.model);
        if (savedModel) {
            this.elements.modelSelect.value = savedModel;
        }

        const savedSampleSizeMode = localStorage.getItem(this.storageKeys.sampleSizeMode);
        if (savedSampleSizeMode) {
            this.elements.sampleSizeMode.value = savedSampleSizeMode;
        } else {
            this.elements.sampleSizeMode.value = 'auto'; // Default to auto
        }

        const savedCustomLimit = localStorage.getItem(this.storageKeys.customLimit);
        if (savedCustomLimit) {
            this.elements.customLimit.value = savedCustomLimit;
        }

        // Initialize sample size mode
        this.handleSampleSizeModeChange();
        
        // Apply settings after loading dropdowns with a longer delay to ensure DOM is ready
        if (savedTopic) {
            setTimeout(() => {
                console.log('Applying saved topic:', savedTopic);
                this.onTopicChange();
            }, 500);
        }
    }

    addEventListeners() {
        // Topic selection change
        if (this.elements.topicSelect) {
            this.elements.topicSelect.addEventListener('change', async () => {
                console.log(`DEBUG: Topic changed to: '${this.elements.topicSelect.value}'`);
                localStorage.setItem(this.storageKeys.topic, this.elements.topicSelect.value);
                await this.onTopicChange();
                this.updateUIState();
            });
        }

        // Model selection change
        if (this.elements.modelSelect) {
            this.elements.modelSelect.addEventListener('change', () => {
                console.log(`DEBUG: Model changed to: '${this.elements.modelSelect.value}'`);
                localStorage.setItem(this.storageKeys.model, this.elements.modelSelect.value);
                this.updateUIState();
                this.updateContextInfo();
            });
        }

        // Sample size mode change
        if (this.elements.sampleSizeMode) {
            this.elements.sampleSizeMode.addEventListener('change', () => {
                localStorage.setItem(this.storageKeys.sampleSizeMode, this.elements.sampleSizeMode.value);
                this.handleSampleSizeModeChange();
                this.updateContextInfo();
            });
        }

        // Custom limit change
        if (this.elements.customLimit) {
            this.elements.customLimit.addEventListener('change', () => {
                localStorage.setItem(this.storageKeys.customLimit, this.elements.customLimit.value);
                this.updateContextInfo();
            });
        }

        // Send message
        if (this.elements.sendBtn) {
            this.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        }
        
        // Enter key to send
        if (this.elements.input) {
            this.elements.input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        // Clear chat
        if (this.elements.clearBtn) {
            this.elements.clearBtn.addEventListener('click', () => this.clearChat());
        }

        // Export chat
        if (this.elements.exportBtn) {
            this.elements.exportBtn.addEventListener('click', () => this.exportChat());
        }

        // Save query
        if (this.elements.saveBtn) {
            this.elements.saveBtn.addEventListener('click', () => this.saveCurrentQuery());
        }
        
        // Quick queries
        if (this.elements.quickQueries) {
            this.elements.quickQueries.addEventListener('click', (e) => {
                if (e.target.classList.contains('floating-quick-btn')) {
                    const query = e.target.dataset.query || e.target.textContent;
                    if (query) {
                        console.log(`DEBUG: Quick query clicked: '${query}'`);
                        if (this.elements.input) {
                            this.elements.input.value = query;
                            this.sendMessage();
                        }
                    }
                }
            });
        }

        // Prompt edit button
        if (this.elements.promptEditBtn) {
            this.elements.promptEditBtn.addEventListener('click', () => this.openPromptManager());
            console.log('✓ Prompt edit event listener added');
        } else {
            console.warn('✗ Prompt edit button not found for event listener');
        }

        // Tools configuration modal event listeners
        this.addToolsConfigEventListeners();

        // Use event delegation for buttons that might not be available initially
        // BUT exclude navigation elements to avoid interfering with Bootstrap dropdowns
        document.addEventListener('click', (e) => {
            // Don't interfere with navigation dropdowns or any Bootstrap components
            if (e.target.closest('.navbar') || 
                e.target.closest('.dropdown-menu') || 
                e.target.closest('[data-bs-toggle="dropdown"]') ||
                e.target.closest('.navbar-nav') ||
                e.target.closest('.nav-item')) {
                return; // Let Bootstrap handle navigation clicks
            }
            
            // Only handle our specific chat modal buttons
            if (!e.target.closest('#floatingChatModal')) {
                return; // Only handle clicks within our chat modal
            }
            
            // Check if the clicked element or any of its parents is the toggle sidebar button
            const toggleSidebarBtn = e.target.closest('#toggleSidebar');
            if (toggleSidebarBtn) {
                console.log('Toggle sidebar clicked via delegation');
                e.preventDefault();
                e.stopPropagation();
                this.toggleSidebar();
                return;
            }
            
            // Check if the clicked element or any of its parents is the expand window button
            const expandWindowBtn = e.target.closest('#expandWindowBtn');
            if (expandWindowBtn) {
                console.log('Expand window clicked via delegation');
                e.preventDefault();
                e.stopPropagation();
                this.toggleExpandWindow();
                return;
            }
        });
        
        // Note: Using event delegation above for toggleSidebar, expandWindowBtn, and toolsToggleBtn
        // to handle cases where elements might not be available during initial load

        // Floating chat button
        if (this.elements.button) {
            this.elements.button.addEventListener('click', () => {
                if (this.modalInstance) {
                    this.modalInstance.show();
                }
            });
        }
    }

    async onTopicChange() {
        const topic = this.elements.topicSelect.value;
        console.log(`DEBUG: onTopicChange called with topic: '${topic}'`);
        
        if (!topic) {
            console.log(`DEBUG: No topic selected, clearing chat`);
            this.currentChatId = null;
            this.clearChatDisplay();
            this.clearSessionsList();
            return;
        }

        try {
            console.log(`DEBUG: Loading chat sessions for topic: ${topic}`);
            // Load existing chat sessions for this topic
            await this.loadChatSessions(topic);
            
            console.log(`DEBUG: Found ${this.chatSessions.length} existing chat sessions`);
            
            // Update sidebar with sessions
            this.updateSessionsList();
            
            // Create new chat session if none exists OR if currentChatId is stale
            if (this.chatSessions.length === 0) {
                console.log(`DEBUG: No existing sessions, creating new one...`);
                await this.createNewChatSession(topic);
            } else if (this.chatSessions.length > 0) {
                // Only load if we don't have a current chat or if current chat is not in the sessions list
                const currentChatExists = this.chatSessions.some(session => session.id === this.currentChatId);
                if (!this.currentChatId || !currentChatExists) {
                    console.log(`DEBUG: Loading most recent chat session: ${this.chatSessions[0].id}`);
                    // Load the most recent chat session
                    this.currentChatId = this.chatSessions[0].id;
                    await this.loadChatHistory(this.currentChatId);
                }
            }
            
            console.log(`DEBUG: Chat session setup complete, currentChatId: ${this.currentChatId}`);
        } catch (error) {
            console.error('Error handling topic change:', error);
            // Show error to user
            this.addMessage(`Error loading chat for topic "${topic}": ${error.message}. Please try refreshing the page.`, false);
        }
    }

    async loadChatSessions(topic) {
        try {
            console.log(`DEBUG: Fetching chat sessions for topic: ${topic}`);
            const response = await fetch(`/api/auspex/chat/sessions?topic=${encodeURIComponent(topic)}`);
            console.log(`DEBUG: Chat sessions response status: ${response.status}`);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error(`DEBUG: Chat sessions error response: ${errorText}`);
                throw new Error(`Failed to load chat sessions: ${response.status} - ${errorText}`);
            }
            const data = await response.json();
            console.log(`DEBUG: Chat sessions data:`, data);
            this.chatSessions = data.sessions || [];
        } catch (error) {
            console.error('Error loading chat sessions:', error);
            this.chatSessions = [];
            throw error; // Re-throw to be caught by onTopicChange
        }
    }

    async createNewChatSession(topic) {
        console.log(`DEBUG: createNewChatSession called for topic: ${topic}`);
        
        try {
            // Get organizational profile ID from parent window (news feed)
            let profileId = null;
            try {
                const parentWindow = window.parent || window.opener || window;
                const profileSelect = parentWindow.document?.getElementById('profile-select');
                if (profileSelect && profileSelect.value) {
                    profileId = parseInt(profileSelect.value);
                    console.log(`DEBUG: Creating chat session with organizational profile ID: ${profileId}`);
                }
            } catch (error) {
                console.log('Could not access parent window profile selection for chat creation');
            }
            
            const requestBody = {
                topic: topic,
                title: `Chat about ${topic}`,
                profile_id: profileId
            };
            console.log(`DEBUG: Creating chat session with body:`, requestBody);
            
            const response = await fetch('/api/auspex/chat/sessions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });

            console.log(`DEBUG: Chat session creation response status:`, response.status);

            if (!response.ok) {
                const errorText = await response.text();
                console.error(`DEBUG: Failed to create chat session:`, response.status, response.statusText, errorText);
                throw new Error(`Failed to create chat session: ${response.status} - ${errorText}`);
            }

            const data = await response.json();
            console.log(`DEBUG: Chat session created:`, data);
            
            this.currentChatId = data.chat_id;
            
            // Clear display and show welcome message
            this.clearChatDisplay();
            this.addWelcomeMessage();
            
            console.log(`Created new chat session: ${this.currentChatId}`);
        } catch (error) {
            console.error('Error creating chat session:', error);
            this.addMessage(`Failed to create chat session: ${error.message}`, false);
            throw error; // Re-throw to be caught by onTopicChange
        }
    }

    async loadChatHistory(chatId) {
        try {
            const response = await fetch(`/api/auspex/chat/sessions/${chatId}/messages`);
            if (!response.ok) {
                throw new Error(`Failed to load chat history: ${response.status}`);
            }

            const data = await response.json();
            
            // Clear current display
            this.clearChatDisplay();
            
            // Add welcome message
            this.addWelcomeMessage();
            
            // Add historical messages
            data.messages.forEach(msg => {
                this.addMessage(msg.content, msg.role === 'user');
            });
            
            console.log(`Loaded ${data.messages.length} messages for chat ${chatId}`);
        } catch (error) {
            console.error('Error loading chat history:', error);
            this.clearChatDisplay();
            this.addWelcomeMessage();
        }
    }

    async sendMessage() {
        if (this.isStreaming) return;

        if (!this.elements.input) {
            console.warn('Input element not found');
            return;
        }

        const message = this.elements.input.value.trim();
        if (!message) return;

        // Check if research mode is enabled
        if (this.researchMode) {
            this.elements.input.value = '';
            await this.startDeepResearch(message);
            return;
        }

        const topic = this.elements.topicSelect ? this.elements.topicSelect.value : '';
        const model = this.elements.modelSelect ? this.elements.modelSelect.value : '';
        const limit = this.calculateOptimalSampleSize(model, message);

        console.log(`DEBUG: sendMessage called with:`, {
            message,
            topic,
            model,
            limit,
            currentChatId: this.currentChatId,
            hasChat: this.currentChatId !== null,
            toolsConfig: this.toolsConfig
        });

        if (!topic || !model || !this.currentChatId) {
            console.error(`DEBUG: Missing required fields:`, {
                topic: !!topic,
                model: !!model,
                currentChatId: !!this.currentChatId
            });
            this.addMessage('Please select a topic and model first.', false);
            return;
        }

        // Add user message to display
        this.addMessage(message, true);
        this.elements.input.value = '';

        // Show loading
        this.showLoading(true);
        this.isStreaming = true;

        console.log(`DEBUG: About to call /api/auspex/chat/message with:`, {
            chat_id: this.currentChatId,
            message: message,
            model: model,
            limit: limit,
            use_tools: this.toolsEnabled
        });

        try {
            // Get organizational profile ID from parent window (news feed)
            let profileId = null;
            try {
                const parentWindow = window.parent || window.opener || window;
                const profileSelect = parentWindow.document?.getElementById('profile-select');
                if (profileSelect && profileSelect.value) {
                    profileId = parseInt(profileSelect.value);
                    console.log(`DEBUG: Using organizational profile ID: ${profileId}`);
                }
            } catch (error) {
                console.log('Could not access parent window profile selection');
            }
            
            const response = await fetch('/api/auspex/chat/message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    chat_id: this.currentChatId,
                    message: message,
                    model: model,
                    limit: limit,
                    profile_id: profileId,
                    tools_config: this.toolsConfig,
                    article_detail_limit: limit  // Use same limit for both search and citations
                })
            });

            console.log(`DEBUG: Response status:`, response.status);
            console.log(`DEBUG: Response headers:`, [...response.headers.entries()]);

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            // Handle streaming response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let assistantMessage = '';
            let messageElement = null;

            console.log(`DEBUG: Starting to read streaming response...`);

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            
                            if (data.error) {
                                console.error(`DEBUG: Received error from stream:`, data.error);
                                throw new Error(data.error);
                            }
                            
                            if (data.done) {
                                console.log(`DEBUG: Stream completed successfully`);
                                this.isStreaming = false;
                                this.showLoading(false);
                                return;
                            }
                            
                            if (data.content) {
                                assistantMessage += data.content;
                                
                                // Create message element if it doesn't exist
                                if (!messageElement) {
                                    messageElement = this.createStreamingMessage();
                                }
                                
                                // Update the streaming message
                                this.updateStreamingMessage(messageElement, assistantMessage);
                            }
                        } catch (e) {
                            console.warn('Error parsing SSE data:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error sending message:', error);
            this.addMessage(`Error: ${error.message}`, false);
        } finally {
            this.isStreaming = false;
            this.showLoading(false);
        }
    }

    createStreamingMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'floating-message assistant streaming';
        
        const avatar = document.createElement('div');
        avatar.className = 'floating-message-avatar';
        avatar.innerHTML = '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'floating-message-content';
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
        
        const copyButton = document.createElement('button');
        copyButton.className = 'floating-message-copy';
        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
        copyButton.title = 'Copy message';
        copyButton.onclick = () => this.copyMessage(contentDiv.textContent);
        messageDiv.appendChild(copyButton);
        
        this.elements.messages.appendChild(messageDiv);
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
        
        return messageDiv;
    }

    updateStreamingMessage(messageElement, content) {
        const contentDiv = messageElement.querySelector('.floating-message-content');

        // Process chart markers before parsing markdown
        const processedContent = this.processChartMarkers(content, contentDiv);

        // Parse markdown for the text content (with chart markers removed)
        contentDiv.innerHTML = marked.parse(processedContent.textContent);

        // Render any charts that were found
        if (processedContent.charts && processedContent.charts.length > 0) {
            this.renderChartsInMessage(contentDiv, processedContent.charts);
        }

        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
    }

    processChartMarkers(content, container) {
        /**
         * Process chart markers from the streaming content.
         * Markers are in format: <!-- CHART_DATA:{json}:END_CHART -->
         * Returns: { textContent: string, charts: Array }
         */
        const chartRegex = /<!-- CHART_DATA:([\s\S]*?):END_CHART -->/g;
        const errorRegex = /<!-- CHART_ERROR:([\s\S]*?):END_CHART -->/g;

        const charts = [];
        let textContent = content;

        // Extract chart data
        let match;
        while ((match = chartRegex.exec(content)) !== null) {
            try {
                const chartData = JSON.parse(match[1]);
                charts.push(chartData);
                // Remove marker from text content
                textContent = textContent.replace(match[0], '');
            } catch (e) {
                console.error('Failed to parse chart data:', e);
            }
        }

        // Handle error markers (just remove them for now)
        textContent = textContent.replace(errorRegex, '');

        return { textContent: textContent.trim(), charts };
    }

    renderChartsInMessage(container, charts) {
        /**
         * Render Plotly charts within a message container.
         */
        if (!window.Plotly) {
            console.warn('Plotly not loaded, cannot render charts');
            return;
        }

        charts.forEach((chartData, index) => {
            if (chartData.error) {
                console.warn('Chart error:', chartData.error);
                return;
            }

            // Create chart container
            const chartWrapper = document.createElement('div');
            chartWrapper.className = 'auspex-chart-container';
            chartWrapper.style.cssText = 'margin: 15px 0; padding: 10px; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);';

            // Chart title
            if (chartData.title) {
                const titleEl = document.createElement('div');
                titleEl.className = 'auspex-chart-title';
                titleEl.style.cssText = 'font-weight: 600; margin-bottom: 10px; color: #333;';
                titleEl.textContent = chartData.title;
                chartWrapper.appendChild(titleEl);
            }

            // Chart div for Plotly
            const chartDiv = document.createElement('div');
            chartDiv.id = `auspex-chart-${Date.now()}-${index}`;
            chartDiv.style.cssText = 'min-height: 350px; width: 100%;';
            chartWrapper.appendChild(chartDiv);

            // Append to message
            container.appendChild(chartWrapper);

            // Render with Plotly
            if (chartData.format === 'json' && chartData.data) {
                const plotlyData = chartData.data;
                const config = {
                    responsive: true,
                    displayModeBar: true,
                    modeBarButtonsToRemove: ['sendDataToCloud', 'lasso2d', 'select2d'],
                    displaylogo: false
                };

                try {
                    Plotly.newPlot(chartDiv.id, plotlyData.data, plotlyData.layout, config);
                } catch (e) {
                    console.error('Failed to render Plotly chart:', e);
                    chartDiv.innerHTML = '<p style="color: red;">Failed to render chart</p>';
                }
            } else if (chartData.format === 'base64' && chartData.data) {
                // Render as image
                const img = document.createElement('img');
                img.src = chartData.data;
                img.alt = chartData.title || 'Chart';
                img.style.cssText = 'max-width: 100%; height: auto;';
                chartDiv.appendChild(img);
            } else if (chartData.format === 'html' && chartData.data) {
                // Render as HTML
                chartDiv.innerHTML = chartData.data;
            }
        });
    }

    updateUIState() {
        const hasTopic = this.elements.topicSelect ? this.elements.topicSelect.value !== '' : false;
        const hasModel = this.elements.modelSelect ? this.elements.modelSelect.value !== '' : false;
        const hasChat = this.currentChatId !== null;
        
        // Enable/disable input and buttons based on selections
        if (this.elements.input) {
            this.elements.input.disabled = !(hasTopic && hasModel && hasChat);
        }
        
        if (this.elements.sendBtn) {
            this.elements.sendBtn.disabled = !(hasTopic && hasModel && hasChat) || this.isStreaming;
        }
        
        if (this.elements.saveBtn) {
            this.elements.saveBtn.disabled = !(hasTopic && hasModel && hasChat);
        }
        
        // Update tools config button state
        if (this.elements.toolsConfigBtn) {
            const hasCustomConfig = this.hasCustomToolsConfig();
            if (hasCustomConfig) {
                this.elements.toolsConfigBtn.classList.add('has-custom-config');
                this.elements.toolsConfigBtn.title = 'Custom tools configuration active';
            } else {
                this.elements.toolsConfigBtn.classList.remove('has-custom-config');
                this.elements.toolsConfigBtn.title = 'Configure tools';
            }
        }
        
        // Update context info
        this.updateContextInfo();
    }

    showLoading(show) {
        if (this.elements.loading) {
            this.elements.loading.style.display = show ? 'block' : 'none';
        }
        
        if (this.elements.sendBtn) {
            this.elements.sendBtn.disabled = show;
        }
    }

    addWelcomeMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'floating-message assistant welcome';
        
        const avatar = document.createElement('div');
        avatar.className = 'floating-message-avatar';
        avatar.innerHTML = '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'floating-message-content';
        contentDiv.innerHTML = `
            <strong>Welcome to Auspex 2.0!</strong><br>
            I'm your enhanced AI research assistant with advanced capabilities:<br>
            • Real-time news search and analysis<br>
            • Sentiment trend analysis<br>
            • Category and keyword insights<br>
            • Persistent chat history<br>
            • Tool-powered responses<br><br>
            Ask me anything about your selected topic!
        `;
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
        
        this.elements.messages.appendChild(messageDiv);
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
    }

    addMessage(content, isUser = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `floating-message ${isUser ? 'user' : 'assistant'}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'floating-message-avatar';
        avatar.innerHTML = isUser ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'floating-message-content';
        
        if (isUser) {
            contentDiv.textContent = content;
        } else {
            contentDiv.innerHTML = marked.parse(content);
        }
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
        
        if (!isUser) {
            const copyButton = document.createElement('button');
            copyButton.className = 'floating-message-copy';
            copyButton.innerHTML = '<i class="fas fa-copy"></i>';
            copyButton.title = 'Copy message';
            copyButton.onclick = () => this.copyMessage(content);
            messageDiv.appendChild(copyButton);
        }
        
        this.elements.messages.appendChild(messageDiv);
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
    }

    clearChatDisplay() {
        this.elements.messages.innerHTML = '';
    }

    async clearChat() {
        if (!this.currentChatId) return;
        
        if (confirm('Are you sure you want to start a new chat? This will create a fresh conversation.')) {
            try {
                // Create new chat session instead of deleting
                const topic = this.elements.topicSelect.value;
                if (topic) {
                    await this.createNewChatSession(topic);
                    // Reload sessions list to show the new chat
                    await this.loadChatSessions(topic);
                    this.updateSessionsList();
                }
            } catch (error) {
                console.error('Error creating new chat:', error);
                alert('Failed to create new chat. Please try again.');
            }
        }
    }

    async exportChat() {
        if (!this.currentChatId) {
            alert('No active chat to export.');
            return;
        }

        try {
            const response = await fetch(`/api/auspex/chat/sessions/${this.currentChatId}/messages`);
            if (!response.ok) {
                throw new Error('Failed to fetch chat history');
            }

            const data = await response.json();
            
            // Format conversation as Markdown
            const topic = this.elements.topicSelect.value;
            const model = this.elements.modelSelect.value;
            const exportDate = new Date().toLocaleString();
            
            let markdownContent = `# Auspex AI Conversation Export\n\n`;
            markdownContent += `**Topic:** ${topic}\n`;
            markdownContent += `**AI Model:** ${model}\n`;
            markdownContent += `**Chat ID:** ${this.currentChatId}\n`;
            markdownContent += `**Exported:** ${exportDate}\n\n`;
            markdownContent += `---\n\n`;
            
            // Add each message to the markdown
            data.messages.forEach((message, index) => {
                const isUser = message.role === 'user';
                const speaker = isUser ? '👤 **User**' : '🤖 **Auspex AI**';
                const timestamp = message.timestamp ? new Date(message.timestamp).toLocaleString() : '';
                
                markdownContent += `## ${speaker}`;
                if (timestamp) {
                    markdownContent += ` *(${timestamp})*`;
                }
                markdownContent += `\n\n`;
                markdownContent += `${message.content}\n\n`;
                
                // Add separator between messages (except for the last one)
                if (index < data.messages.length - 1) {
                    markdownContent += `---\n\n`;
                }
            });

            const blob = new Blob([markdownContent], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `auspex-chat-${this.currentChatId}-${new Date().toISOString().split('T')[0]}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Error exporting chat:', error);
            alert('Failed to export chat. Please try again.');
        }
    }

    saveCurrentQuery() {
        const query = this.elements.input.value.trim();
        if (!query) return;

        const customName = prompt('Enter a name for this query:');
        if (!customName) return;

        this.customQueries.push({ name: customName, query: query });
        this.saveCustomQueries();
        this.renderCustomQueries();
    }

    loadCustomQueries() {
        try {
            const saved = localStorage.getItem(this.storageKeys.customQueries);
            return saved ? JSON.parse(saved) : [];
        } catch (error) {
            console.error('Error loading custom queries:', error);
            return [];
        }
    }

    saveCustomQueries() {
        try {
            localStorage.setItem(this.storageKeys.customQueries, JSON.stringify(this.customQueries));
        } catch (error) {
            console.error('Error saving custom queries:', error);
        }
    }

    renderCustomQueries() {
        const container = document.getElementById('customQueries');
        if (!container) return;

        container.innerHTML = '';
        this.customQueries.forEach((query, index) => {
            const btn = document.createElement('button');
            btn.className = 'floating-quick-btn custom';
            btn.textContent = query.name;
            btn.dataset.query = query.query;
            
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-custom';
            removeBtn.innerHTML = '×';
            removeBtn.onclick = (e) => {
                e.stopPropagation();
                this.removeCustomQuery(index);
            };
            
            btn.appendChild(removeBtn);
            container.appendChild(btn);
        });
    }

    removeCustomQuery(index) {
        this.customQueries.splice(index, 1);
        this.saveCustomQueries();
        this.renderCustomQueries();
    }

    copyMessage(content) {
        navigator.clipboard.writeText(content).then(() => {
            // Show brief feedback
            const tooltip = document.createElement('div');
            tooltip.textContent = 'Copied!';
            tooltip.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: #333;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                z-index: 10000;
                font-size: 14px;
            `;
            document.body.appendChild(tooltip);
            setTimeout(() => document.body.removeChild(tooltip), 1000);
        }).catch(err => {
            console.error('Failed to copy text:', err);
        });
    }

    toggleSidebar() {
        console.log('toggleSidebar called');
        
        // Try to find elements if not already found
        if (!this.elements.sidebar) {
            this.elements.sidebar = document.getElementById('chatSidebar');
            console.log('Found sidebar element:', !!this.elements.sidebar);
        }
        if (!this.elements.toggleSidebar) {
            this.elements.toggleSidebar = document.getElementById('toggleSidebar');
            console.log('Found toggle sidebar element:', !!this.elements.toggleSidebar);
        }
        
        if (!this.elements.sidebar) {
            console.error('CRITICAL: Sidebar element not found! Looking for #chatSidebar');
            // Debug: list all elements with chat-sidebar class
            const sidebarElements = document.querySelectorAll('.chat-sidebar');
            console.log('Found elements with .chat-sidebar class:', sidebarElements.length);
            sidebarElements.forEach((el, i) => console.log(`  ${i}: id="${el.id}", classes="${el.className}"`));
            return;
        }
        
        if (!this.elements.toggleSidebar) {
            console.error('CRITICAL: Toggle sidebar button not found! Looking for #toggleSidebar');
            return;
        }
        
        const isCurrentlyShown = this.elements.sidebar.classList.contains('shown');
        console.log('Sidebar currently shown:', isCurrentlyShown);
        console.log('Sidebar current classes:', this.elements.sidebar.className);
        
        if (isCurrentlyShown) {
            // Hide sidebar
            this.elements.sidebar.classList.remove('shown');
            this.elements.sidebar.classList.add('hidden');
            
            // Update button
            const icon = this.elements.toggleSidebar.querySelector('i');
            if (icon) {
                icon.className = 'fas fa-chevron-right';
                this.elements.toggleSidebar.title = 'Show chat history';
                this.elements.toggleSidebar.setAttribute('data-bs-original-title', 'Show chat history');
            }
            console.log('Sidebar hidden - new classes:', this.elements.sidebar.className);
        } else {
            // Show sidebar
            this.elements.sidebar.classList.remove('hidden');
            this.elements.sidebar.classList.add('shown');
            
            // Update button
            const icon = this.elements.toggleSidebar.querySelector('i');
            if (icon) {
                icon.className = 'fas fa-chevron-left';
                this.elements.toggleSidebar.title = 'Hide chat history';
                this.elements.toggleSidebar.setAttribute('data-bs-original-title', 'Hide chat history');
            }
            console.log('Sidebar shown - new classes:', this.elements.sidebar.className);
        }
    }

    clearSessionsList() {
        if (!this.elements.sessionsList) {
            console.warn('Sessions list element not found');
            return;
        }
        this.elements.sessionsList.innerHTML = `
            <div class="text-muted text-center p-3">
                <i class="fas fa-comments"></i><br>
                Select a topic to see chat history
            </div>
        `;
    }

    updateSessionsList() {
        if (!this.elements.sessionsList) {
            console.warn('Sessions list element not found');
            return;
        }
        
        if (!this.chatSessions || this.chatSessions.length === 0) {
            this.elements.sessionsList.innerHTML = `
                <div class="text-muted text-center p-3">
                    <i class="fas fa-comment-slash"></i><br>
                    No chat history for this topic
                </div>
            `;
            return;
        }

        const sessionsHtml = this.chatSessions.map(session => {
            const isActive = session.id === this.currentChatId;
            const createdAt = new Date(session.created_at).toLocaleDateString();
            const title = session.title || `Chat ${session.id}`;
            
            return `
                <div class="chat-session-item ${isActive ? 'active' : ''}" data-chat-id="${session.id}">
                    <div class="chat-session-content" onclick="floatingChatInstance.switchToChat(${session.id})">
                        <div class="chat-session-title">${title}</div>
                        <div class="chat-session-info">
                            <i class="fas fa-calendar"></i> ${createdAt}
                            <span class="ms-2"><i class="fas fa-comments"></i> ${session.message_count || 0}</span>
                        </div>
                    </div>
                    <div class="chat-session-actions">
                        <button class="btn btn-sm btn-outline-danger" onclick="floatingChatInstance.deleteChatSession(${session.id})" title="Delete chat">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        this.elements.sessionsList.innerHTML = sessionsHtml;
    }

    async deleteChatSession(chatId) {
        if (chatId === this.currentChatId) {
            alert('Cannot delete the currently active chat session. Please switch to another chat first.');
            return;
        }

        if (!confirm('Are you sure you want to delete this chat session? This action cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch(`/api/auspex/chat/sessions/${chatId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                // Reload the chat sessions list
                const topic = this.elements.topicSelect.value;
                if (topic) {
                    await this.loadChatSessions(topic);
                    this.updateSessionsList();
                }
            } else {
                throw new Error('Failed to delete chat session');
            }
        } catch (error) {
            console.error('Error deleting chat session:', error);
            alert('Failed to delete chat session. Please try again.');
        }
    }

    async switchToChat(chatId) {
        if (chatId === this.currentChatId) return;

        try {
            this.currentChatId = chatId;
            await this.loadChatHistory(chatId);
            this.updateSessionsList(); // Update active state
        } catch (error) {
            console.error('Error switching to chat:', error);
            this.addMessage(`Error loading chat: ${error.message}`, false);
        }
    }

    openPromptManager() {
        // Open the Auspex prompt manager modal
        const promptModal = document.getElementById('auspexPromptModal');
        if (promptModal) {
            const modal = new bootstrap.Modal(promptModal);
            modal.show();
            
            // Trigger the prompt manager to load prompts
            // The prompt manager is initialized as 'auspexPromptManager' in base.html
            setTimeout(() => {
                if (typeof auspexPromptManager !== 'undefined' && auspexPromptManager) {
                    auspexPromptManager.loadPrompts();
                } else {
                    console.error('Prompt manager not initialized yet');
                }
            }, 100);
        } else {
            console.error('Prompt manager modal not found');
        }
    }

    toggleExpandWindow() {
        console.log('toggleExpandWindow called');
        
        if (!this.elements.modal) {
            console.error('CRITICAL: Modal element not found! Looking for #floatingChatModal');
            return;
        }
        
        const modalDialog = this.elements.modal.querySelector('.modal-dialog');
        const icon = this.elements.expandWindowBtn.querySelector('i');
        
        if (!modalDialog || !icon) {
            console.error('CRITICAL: Modal dialog or icon not found!');
            return;
        }

        const isExpanded = modalDialog.classList.contains('modal-fullscreen');
        console.log(`Modal currently expanded: ${isExpanded}`);
        
        if (isExpanded) {
            // Collapse to normal size
            modalDialog.classList.remove('modal-fullscreen');
            if (!modalDialog.classList.contains('modal-xl')) {
                modalDialog.classList.add('modal-xl');
            }
            icon.className = 'fas fa-expand';
            this.elements.expandWindowBtn.title = 'Expand window';
            this.elements.expandWindowBtn.setAttribute('data-bs-original-title', 'Expand window');
            console.log('Modal collapsed');
        } else {
            // Expand to fullscreen
            modalDialog.classList.remove('modal-xl');
            modalDialog.classList.add('modal-fullscreen');
            icon.className = 'fas fa-compress';
            this.elements.expandWindowBtn.title = 'Collapse window';
            this.elements.expandWindowBtn.setAttribute('data-bs-original-title', 'Collapse window');
            console.log('Modal expanded');
        }
    }

    // Tools Configuration Methods
    loadToolsConfig() {
        try {
            const saved = localStorage.getItem(this.storageKeys.toolsConfig);
            return saved ? JSON.parse(saved) : this.getDefaultToolsConfig();
        } catch (error) {
            console.error('Error loading tools config:', error);
            return this.getDefaultToolsConfig();
        }
    }

    getDefaultToolsConfig() {
        return {
            get_topic_articles: true,
            semantic_search_and_analyze: true,
            search_articles_by_keywords: true,
            follow_up_query: true,
            analyze_sentiment_trends: true,
            get_article_categories: true,
            search_news: true
        };
    }

    saveToolsConfig() {
        try {
            localStorage.setItem(this.storageKeys.toolsConfig, JSON.stringify(this.toolsConfig));
        } catch (error) {
            console.error('Error saving tools config:', error);
        }
    }

    hasCustomToolsConfig() {
        const defaultConfig = this.getDefaultToolsConfig();
        return JSON.stringify(this.toolsConfig) !== JSON.stringify(defaultConfig);
    }

    addToolsConfigEventListeners() {
        // Save tools config
        const saveBtn = document.getElementById('saveToolsConfig');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveToolsConfiguration());
        }

        // Enable all tools
        const enableAllBtn = document.getElementById('enableAllTools');
        if (enableAllBtn) {
            enableAllBtn.addEventListener('click', () => this.setAllTools(true));
        }

        // Disable all tools
        const disableAllBtn = document.getElementById('disableAllTools');
        if (disableAllBtn) {
            disableAllBtn.addEventListener('click', () => this.setAllTools(false));
        }

        // Reset to default
        const resetBtn = document.getElementById('resetDefaultTools');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => this.resetToolsToDefault());
        }

        // Individual tool toggles
        const toolIds = [
            'toolGetTopicArticles',
            'toolSemanticSearch', 
            'toolKeywordSearch',
            'toolFollowUp',
            'toolSentimentTrends',
            'toolCategoryAnalysis',
            'toolNewsSearch'
        ];

        toolIds.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('change', () => this.updateToolConfig(id, element.checked));
            }
        });

        // Load current config into modal when it's shown
        if (this.elements.toolsConfigModal) {
            this.elements.toolsConfigModal.addEventListener('shown.bs.modal', () => {
                this.loadToolsConfigIntoModal();
            });
        }
    }

    loadToolsConfigIntoModal() {
        const toolMapping = {
            'toolGetTopicArticles': 'get_topic_articles',
            'toolSemanticSearch': 'semantic_search_and_analyze',
            'toolKeywordSearch': 'search_articles_by_keywords',
            'toolFollowUp': 'follow_up_query',
            'toolSentimentTrends': 'analyze_sentiment_trends',
            'toolCategoryAnalysis': 'get_article_categories',
            'toolNewsSearch': 'search_news'
        };

        Object.entries(toolMapping).forEach(([elementId, configKey]) => {
            const element = document.getElementById(elementId);
            if (element) {
                element.checked = this.toolsConfig[configKey] || false;
            }
        });
    }

    updateToolConfig(elementId, enabled) {
        const toolMapping = {
            'toolGetTopicArticles': 'get_topic_articles',
            'toolSemanticSearch': 'semantic_search_and_analyze',
            'toolKeywordSearch': 'search_articles_by_keywords',
            'toolFollowUp': 'follow_up_query',
            'toolSentimentTrends': 'analyze_sentiment_trends',
            'toolCategoryAnalysis': 'get_article_categories',
            'toolNewsSearch': 'search_news'
        };

        const configKey = toolMapping[elementId];
        if (configKey) {
            this.toolsConfig[configKey] = enabled;
        }
    }

    saveToolsConfiguration() {
        this.saveToolsConfig();
        this.updateUIState();
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(this.elements.toolsConfigModal);
        if (modal) {
            modal.hide();
        }

        // Show notification
        this.showNotification('Tools configuration saved successfully!', 'success');
    }

    setAllTools(enabled) {
        Object.keys(this.toolsConfig).forEach(key => {
            this.toolsConfig[key] = enabled;
        });
        this.loadToolsConfigIntoModal();
    }

    resetToolsToDefault() {
        this.toolsConfig = this.getDefaultToolsConfig();
        this.loadToolsConfigIntoModal();
    }

    // Dynamic Sample Sizing Methods
    calculateOptimalSampleSize(model, message) {
        const mode = this.elements.sampleSizeMode ? this.elements.sampleSizeMode.value : 'auto';
        
        switch (mode) {
            case 'auto':
                return this.calculateAutoSampleSize(model, message);
            case 'balanced':
                return 50;
            case 'comprehensive':
                return 100;
            case 'focused':
                return 25;
            case 'custom':
                return parseInt(this.elements.customLimit.value) || 50;
            default:
                return 50;
        }
    }

    calculateAutoSampleSize(model, message) {
        // Get context window limit for the model
        const contextLimit = this.contextLimits[model] || this.contextLimits.default;
        
        // Determine query type for optimization
        const queryType = this.determineQueryType(message);
        const optimizationFactor = this.optimizationFactors[queryType];
        
        // Calculate budget allocation (matching backend logic)
        const allocation = this.optimizationFactors[queryType];
        const systemPromptTokens = Math.floor(contextLimit * 0.12); // System prompt allocation
        const conversationHistoryTokens = this.estimateConversationTokens();
        const messageTokens = this.estimateTokens(message);
        const responseReserveTokens = Math.floor(contextLimit * 0.05); // Response buffer
        const articlesAllocation = Math.floor(contextLimit * 0.73); // Articles get 73% for comprehensive
        
        // Available tokens for articles (use backend logic)
        const availableTokens = Math.min(
            articlesAllocation,
            contextLimit - systemPromptTokens - conversationHistoryTokens - messageTokens - responseReserveTokens
        );
        
        // Use backend token estimation (120 tokens per compressed article)
        const optimizedTokensPerArticle = 120;
        
        // Calculate rough max articles (matching backend logic)
        const roughMaxArticles = Math.floor(availableTokens / optimizedTokensPerArticle);
        
        // Match backend logic for target count
        const targetCount = Math.max(roughMaxArticles, 50); // Allow at least 50 if possible
        
        // Apply reasonable bounds (matching backend bounds)
        return Math.max(10, Math.min(300, targetCount));
    }
    
    determineQueryType(message) {
        if (!message) return 'comprehensive';
        
        const messageLower = message.toLowerCase();
        
        if (messageLower.includes('trend') || messageLower.includes('pattern') || 
            messageLower.includes('over time') || messageLower.includes('recent') || 
            messageLower.includes('latest')) {
            return 'trend_analysis';
        }
        
        if (messageLower.includes('comprehensive') || messageLower.includes('detailed') || 
            messageLower.includes('deep') || messageLower.includes('thorough')) {
            return 'detailed_analysis';
        }
        
        if (messageLower.includes('summary') || messageLower.includes('brief') || 
            messageLower.includes('overview') || messageLower.includes('quick')) {
            return 'quick_summary';
        }
        
        return 'comprehensive';
    }
    
    calculateOptimizedTokenUsage(sampleSize, model, message) {
        const queryType = this.determineQueryType(message);
        const optimizationFactor = this.optimizationFactors[queryType];
        const contextLimit = this.contextLimits[model] || this.contextLimits.default;
        
        // Match backend token calculation exactly
        const systemPromptTokens = Math.floor(contextLimit * 0.12); // 12% allocation
        const conversationHistoryTokens = this.estimateConversationTokens();
        const messageTokens = this.estimateTokens(message);
        
        // Use backend's optimized tokens per article (120 tokens per compressed article)
        const optimizedTokensPerArticle = 120;
        const articleTokens = sampleSize * optimizedTokensPerArticle;
        
        return {
            total: systemPromptTokens + conversationHistoryTokens + messageTokens + articleTokens,
            breakdown: {
                system: systemPromptTokens,
                conversation: conversationHistoryTokens,
                message: messageTokens,
                articles: articleTokens,
                per_article: optimizedTokensPerArticle
            },
            optimization: {
                query_type: queryType,
                compression_ratio: optimizationFactor.compression_ratio,
                diversity_ratio: optimizationFactor.diversity_ratio,
                format_efficiency: optimizationFactor.format_efficiency
            }
        };
    }

    estimateTokens(text) {
        // Rough estimation: ~4 characters per token for English text
        return Math.ceil(text.length / 4);
    }

    estimateConversationTokens() {
        // Estimate based on current chat messages
        const messages = this.elements.messages.querySelectorAll('.floating-message-content');
        let totalChars = 0;
        
        messages.forEach(msg => {
            totalChars += msg.textContent.length;
        });
        
        return Math.ceil(totalChars / 4);
    }

    handleSampleSizeModeChange() {
        const mode = this.elements.sampleSizeMode.value;

        if (mode === 'custom') {
            this.elements.customLimit.classList.add('show');
            this.elements.customLimit.style.display = 'block';
        } else {
            this.elements.customLimit.classList.remove('show');
            this.elements.customLimit.style.display = 'none';
        }

        this.updateContextInfo();
    }

    updateContextInfo() {
        if (!this.elements.contextInfo || !this.elements.contextStats) return;
        
        const model = this.elements.modelSelect ? this.elements.modelSelect.value : '';
        const message = this.elements.input ? this.elements.input.value : '';
        let sampleSize = this.calculateOptimalSampleSize(model, message);
        
        // Get optimized token usage calculation
        const contextLimit = this.contextLimits[model] || this.contextLimits.default;
        const modelContextLimit = contextLimit; // For consistent naming
        const tokenUsage = this.calculateOptimizedTokenUsage(sampleSize, model, message);
        
        // Safety check: If we're over 95% of context, automatically reduce sample size
        let contextUsage = (tokenUsage.total / contextLimit) * 100;
        
        if (contextUsage > 95 && this.elements.sampleSizeMode.value === 'auto') {
            // Calculate safe sample size with optimization
            const safeTokenBudget = contextLimit * 0.9; // Use 90% of context for safety
            const availableForArticles = safeTokenBudget - tokenUsage.breakdown.system - tokenUsage.breakdown.conversation - tokenUsage.breakdown.message;
            const safeSampleSize = Math.max(5, Math.floor(availableForArticles / tokenUsage.breakdown.per_article));
            
            if (safeSampleSize < sampleSize) {
                sampleSize = safeSampleSize;
                const newTokenUsage = this.calculateOptimizedTokenUsage(sampleSize, model, message);
                contextUsage = (newTokenUsage.total / contextLimit) * 100;
                tokenUsage.total = newTokenUsage.total;
                tokenUsage.breakdown = newTokenUsage.breakdown;
            }
        }
        
        // Warning for custom limits that exceed capacity
        let warningText = '';
        let optimizationInfo = '';
        
        if (contextUsage > 100) {
            warningText = ' ⚠️ OVERFLOW';
            if (this.elements.sampleSizeMode.value === 'custom') {
                // Calculate safe custom limit with optimization
                const maxSafeTokens = contextLimit * 0.9;
                const maxSafeArticles = Math.floor((maxSafeTokens - tokenUsage.breakdown.system - tokenUsage.breakdown.conversation - tokenUsage.breakdown.message) / tokenUsage.breakdown.per_article);
                warningText += ` (Max safe: ${Math.max(5, maxSafeArticles)})`;
            }
        }
        
        // Add optimization information for better understanding
        if (message && message.length > 0) {
            const queryType = tokenUsage.optimization.query_type;
            const compressionPercent = Math.round((1 - tokenUsage.optimization.compression_ratio) * 100);
            
            // Calculate what the old system would have used
            const oldTokensPerArticle = 300;
            const oldTotalTokens = tokenUsage.breakdown.system + tokenUsage.breakdown.conversation + tokenUsage.breakdown.message + (sampleSize * oldTokensPerArticle);
            const oldContextUsage = (oldTotalTokens / contextLimit) * 100;
            const tokenSavings = Math.round(((oldTotalTokens - tokenUsage.total) / oldTotalTokens) * 100);
            
            optimizationInfo = ` | ${queryType.replace('_', ' ')} (${compressionPercent}% compressed, ${tokenSavings}% tokens saved)`;
        }
        
        // Enhanced context display with optimization details
        const modelIndicator = modelContextLimit >= 1000000 ? ' 🚀1M' : 
                              modelContextLimit >= 200000 ? ' ⚡200K' : 
                              modelContextLimit >= 100000 ? ' 💫100K' : '';
        
        const contextText = `Context: ${sampleSize} articles, ~${tokenUsage.total.toLocaleString()} tokens (${contextUsage.toFixed(1)}%)${modelIndicator}${optimizationInfo}${warningText}`;
        
        this.elements.contextStats.textContent = contextText;
        
        // Add tooltip with detailed breakdown and comparison
        let tooltipText = `OPTIMIZED TOKEN BREAKDOWN:
System: ${tokenUsage.breakdown.system.toLocaleString()}
Conversation: ${tokenUsage.breakdown.conversation.toLocaleString()}
Message: ${tokenUsage.breakdown.message.toLocaleString()}
Articles: ${tokenUsage.breakdown.articles.toLocaleString()} (${tokenUsage.breakdown.per_article}/article)
Total: ${tokenUsage.total.toLocaleString()} tokens

OPTIMIZATION DETAILS:
Query Type: ${tokenUsage.optimization.query_type.replace('_', ' ')}
Compression: ${Math.round((1 - tokenUsage.optimization.compression_ratio) * 100)}%
Format Efficiency: ${Math.round((1 - tokenUsage.optimization.format_efficiency) * 100)}% reduction
Diversity Factor: ${Math.round((1 - tokenUsage.optimization.diversity_ratio) * 100)}% filtering`;

        // Add comparison if we have a message
        if (message && message.length > 0) {
            const oldTokensPerArticle = 300;
            const oldTotalTokens = tokenUsage.breakdown.system + tokenUsage.breakdown.conversation + tokenUsage.breakdown.message + (sampleSize * oldTokensPerArticle);
            const tokenSavings = oldTotalTokens - tokenUsage.total;
            const percentSavings = Math.round((tokenSavings / oldTotalTokens) * 100);
            
            tooltipText += `

WITHOUT OPTIMIZATION:
Articles would use: ${(sampleSize * oldTokensPerArticle).toLocaleString()} tokens (${oldTokensPerArticle}/article)
Total would be: ${oldTotalTokens.toLocaleString()} tokens
Context usage: ${((oldTotalTokens / contextLimit) * 100).toFixed(1)}%

SAVINGS: ${tokenSavings.toLocaleString()} tokens (${percentSavings}%)`;
        }
        
        this.elements.contextStats.title = tooltipText;
        
        // Show/hide context info based on whether we have selections
        const hasModel = model !== '';
        this.elements.contextInfo.style.display = hasModel ? 'block' : 'none';
        
        // Enhanced color coding for context usage with optimization awareness
        const isMegaContext = modelContextLimit >= 1000000; // 1M+ tokens
        
        if (contextUsage > 100) {
            this.elements.contextStats.style.color = '#dc3545'; // Red for overflow
            this.elements.contextStats.style.fontWeight = 'bold';
        } else if (contextUsage > 90) {
            this.elements.contextStats.style.color = '#dc3545'; // Red for danger
            this.elements.contextStats.style.fontWeight = '600';
        } else if (contextUsage > 70) {
            this.elements.contextStats.style.color = '#fd7e14'; // Orange for warning
            this.elements.contextStats.style.fontWeight = '500';
        } else if (contextUsage > 50) {
            this.elements.contextStats.style.color = '#28a745'; // Green for good efficiency
            this.elements.contextStats.style.fontWeight = '500';
        } else {
            this.elements.contextStats.style.color = isMegaContext ? '#6f42c1' : '#007bff'; // Purple for mega-context models, blue for others
            this.elements.contextStats.style.fontWeight = '500';
        }
        
        // Add special styling for mega-context models
        if (isMegaContext && contextUsage < 10) {
            this.elements.contextStats.style.background = 'linear-gradient(90deg, rgba(111,66,193,0.1) 0%, rgba(111,66,193,0.05) 100%)';
            this.elements.contextStats.style.border = '1px solid rgba(111,66,193,0.2)';
            this.elements.contextStats.style.borderRadius = '4px';
            this.elements.contextStats.style.padding = '4px 8px';
        } else {
            this.elements.contextStats.style.background = '';
            this.elements.contextStats.style.border = '';
            this.elements.contextStats.style.borderRadius = '';
            this.elements.contextStats.style.padding = '';
        }
        
        // Add optimization indicator
        if (message && message.length > 0) {
            const oldTokensPerArticle = 300;
            const oldTotalTokens = tokenUsage.breakdown.system + tokenUsage.breakdown.conversation + tokenUsage.breakdown.message + (sampleSize * oldTokensPerArticle);
            const tokenSavings = Math.round(((oldTotalTokens - tokenUsage.total) / oldTotalTokens) * 100);
            
            // Add visual optimization indicator for significant savings
            if (tokenSavings >= 30) {
                this.elements.contextStats.style.textShadow = '0 0 3px rgba(40, 167, 69, 0.5)'; // Green glow for great optimization
                this.elements.contextStats.style.borderLeft = '3px solid #28a745';
                this.elements.contextStats.style.paddingLeft = '8px';
            } else if (tokenSavings >= 15) {
                this.elements.contextStats.style.textShadow = '0 0 2px rgba(0, 123, 255, 0.4)'; // Blue glow for good optimization
                this.elements.contextStats.style.borderLeft = '2px solid #007bff';
                this.elements.contextStats.style.paddingLeft = '6px';
            } else {
                this.elements.contextStats.style.textShadow = '';
                this.elements.contextStats.style.borderLeft = '';
                this.elements.contextStats.style.paddingLeft = '';
            }
        }
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.textContent = message;

        const colors = {
            success: '#28a745',
            error: '#dc3545',
            warning: '#ffc107',
            info: '#007bff'
        };

        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${colors[type] || colors.info};
            color: white;
            padding: 12px 20px;
            border-radius: 6px;
            z-index: 10000;
            font-size: 14px;
            font-weight: 500;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        `;

        document.body.appendChild(notification);
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 3000);
    }

    // ==================== RESEARCH MODE ====================

    toggleResearchMode() {
        this.researchMode = !this.researchMode;
        localStorage.setItem(this.storageKeys.researchMode, this.researchMode);

        // Update UI to reflect research mode
        const researchToggle = document.getElementById('researchModeToggle');
        if (researchToggle) {
            researchToggle.classList.toggle('active', this.researchMode);
            researchToggle.setAttribute('aria-pressed', this.researchMode);
        }

        // Update input placeholder
        if (this.elements.input) {
            this.elements.input.placeholder = this.researchMode
                ? 'Enter your research question for deep analysis...'
                : 'Type your message...';
        }

        // Update send button appearance
        if (this.elements.sendBtn) {
            this.elements.sendBtn.innerHTML = this.researchMode
                ? '<i class="bi bi-search"></i> Research'
                : '<i class="bi bi-send"></i>';
            this.elements.sendBtn.title = this.researchMode
                ? 'Start Deep Research'
                : 'Send Message';
        }

        this.showNotification(
            this.researchMode
                ? 'Research Mode Enabled - Your queries will trigger comprehensive multi-stage research'
                : 'Research Mode Disabled - Standard chat mode active',
            'info'
        );

        console.log(`Research mode: ${this.researchMode ? 'enabled' : 'disabled'}`);
    }

    async startDeepResearch(query) {
        if (this.researchInProgress) {
            this.showNotification('Research already in progress', 'warning');
            return;
        }

        const topic = this.elements.topicSelect ? this.elements.topicSelect.value : '';
        if (!topic) {
            this.showNotification('Please select a topic first', 'warning');
            return;
        }

        console.log(`Starting deep research: query="${query}", topic="${topic}"`);

        this.researchInProgress = true;
        this.addMessage(query, true);

        // Create research progress element
        const progressElement = this.createResearchProgressElement();
        this.elements.messages.appendChild(progressElement);
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;

        try {
            const response = await fetch('/api/auspex/research', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    query: query,
                    topic: topic,
                    chat_id: this.currentChatId
                })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            // Handle SSE streaming with buffering for partial chunks
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let finalReport = '';
            let buffer = '';  // Buffer to handle partial SSE data

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                // Append decoded chunk to buffer
                buffer += decoder.decode(value, { stream: true });

                // SSE events are separated by double newlines
                // Each event starts with "data: " and contains JSON
                const events = buffer.split('\n\n');
                // Keep the last potentially incomplete event in the buffer
                buffer = events.pop() || '';

                for (const event of events) {
                    // Skip empty events
                    if (!event.trim()) continue;

                    // Extract data from event (handle multi-line data)
                    const dataMatch = event.match(/^data:\s*([\s\S]*)$/m);
                    if (!dataMatch) continue;

                    try {
                        const jsonStr = dataMatch[1].trim();
                        if (!jsonStr) continue;
                        const data = JSON.parse(jsonStr);

                        if (data.error) {
                            this.updateResearchProgress(progressElement, 'error', data.error, 0);
                            throw new Error(data.error);
                        }

                        if (data.done) {
                            console.log('Research completed');
                            this.researchInProgress = false;
                            // Remove progress element and show final report
                            progressElement.remove();
                            if (finalReport) {
                                this.addMessage(finalReport, false);
                            }
                            return;
                        }

                        // Update progress UI based on stage
                        if (data.stage) {
                            const progress = data.progress || 0;
                            let statusText = '';

                            switch (data.stage) {
                                case 'planning':
                                    statusText = data.status === 'started'
                                        ? 'Planning research objectives...'
                                        : `Planning complete: ${data.objectives?.length || 0} objectives identified`;
                                    break;
                                case 'searching':
                                    statusText = data.status === 'started'
                                        ? 'Searching for relevant sources...'
                                        : `Found ${data.results_count || 0} relevant articles`;
                                    break;
                                case 'synthesis':
                                    statusText = data.status === 'started'
                                        ? 'Synthesizing findings...'
                                        : 'Synthesis complete';
                                    break;
                                case 'writing':
                                    statusText = data.status === 'started'
                                        ? 'Writing research report...'
                                        : 'Report generation complete';
                                    break;
                            }

                            this.updateResearchProgress(progressElement, data.stage, statusText, progress);
                        }

                        // Capture streaming report content (from chunk field)
                        if (data.chunk) {
                            finalReport += data.chunk;
                        }

                        // Also handle report_chunk for backwards compat
                        if (data.report_chunk) {
                            finalReport += data.report_chunk;
                        }

                        // Handle final report
                        if (data.final_report) {
                            finalReport = data.final_report;
                        }

                    } catch (e) {
                        // Only log if it's not an empty string parse error
                        if (jsonStr && jsonStr.length > 0) {
                            console.warn('Error parsing SSE data:', e, 'Data:', jsonStr.substring(0, 100));
                        }
                    }
                }
            }

            // Process any remaining buffer content after stream ends
            if (buffer.trim() && buffer.startsWith('data: ')) {
                try {
                    const jsonStr = buffer.slice(6).trim();
                    if (jsonStr) {
                        const data = JSON.parse(jsonStr);
                        if (data.final_report) {
                            finalReport = data.final_report;
                        }
                    }
                } catch (e) {
                    console.warn('Error parsing final buffer:', e);
                }
            }

            // If we have a report but didn't get a done signal, show it anyway
            if (finalReport && progressElement.parentNode) {
                progressElement.remove();
                this.addMessage(finalReport, false);
            }

        } catch (error) {
            console.error('Deep research error:', error);
            this.updateResearchProgress(progressElement, 'error', error.message, 0);
            this.showNotification(`Research failed: ${error.message}`, 'error');
        } finally {
            this.researchInProgress = false;
        }
    }

    createResearchProgressElement() {
        const container = document.createElement('div');
        container.className = 'research-progress-container p-3 mb-3';
        container.style.cssText = `
            background: linear-gradient(135deg, #1a1f36 0%, #0d1224 100%);
            border-radius: 12px;
            border: 1px solid rgba(99, 102, 241, 0.3);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        `;

        container.innerHTML = `
            <div class="d-flex align-items-center mb-3">
                <div class="research-icon me-3" style="font-size: 24px;">🔬</div>
                <div>
                    <h6 class="mb-0 text-light">Deep Research in Progress</h6>
                    <small class="text-muted">Analyzing sources and synthesizing findings...</small>
                </div>
            </div>

            <div class="research-stages">
                <div class="research-stage" data-stage="planning">
                    <div class="stage-indicator">
                        <span class="stage-icon">📋</span>
                        <span class="stage-name">Planning</span>
                        <span class="stage-status badge bg-secondary">Pending</span>
                    </div>
                    <div class="progress mt-1" style="height: 4px;">
                        <div class="progress-bar bg-primary" style="width: 0%"></div>
                    </div>
                </div>

                <div class="research-stage mt-2" data-stage="searching">
                    <div class="stage-indicator">
                        <span class="stage-icon">🔍</span>
                        <span class="stage-name">Searching</span>
                        <span class="stage-status badge bg-secondary">Pending</span>
                    </div>
                    <div class="progress mt-1" style="height: 4px;">
                        <div class="progress-bar bg-info" style="width: 0%"></div>
                    </div>
                </div>

                <div class="research-stage mt-2" data-stage="synthesis">
                    <div class="stage-indicator">
                        <span class="stage-icon">🧪</span>
                        <span class="stage-name">Synthesis</span>
                        <span class="stage-status badge bg-secondary">Pending</span>
                    </div>
                    <div class="progress mt-1" style="height: 4px;">
                        <div class="progress-bar bg-warning" style="width: 0%"></div>
                    </div>
                </div>

                <div class="research-stage mt-2" data-stage="writing">
                    <div class="stage-indicator">
                        <span class="stage-icon">📝</span>
                        <span class="stage-name">Writing</span>
                        <span class="stage-status badge bg-secondary">Pending</span>
                    </div>
                    <div class="progress mt-1" style="height: 4px;">
                        <div class="progress-bar bg-success" style="width: 0%"></div>
                    </div>
                </div>
            </div>

            <div class="research-status mt-3 p-2 rounded" style="background: rgba(99, 102, 241, 0.1);">
                <small class="text-light status-text">Initializing research workflow...</small>
            </div>
        `;

        return container;
    }

    updateResearchProgress(element, stage, statusText, progress) {
        if (!element) return;

        // Update status text
        const statusEl = element.querySelector('.status-text');
        if (statusEl) {
            statusEl.textContent = statusText;
        }

        // Handle error state
        if (stage === 'error') {
            const statusDiv = element.querySelector('.research-status');
            if (statusDiv) {
                statusDiv.style.background = 'rgba(220, 53, 69, 0.2)';
                statusDiv.innerHTML = `<small class="text-danger"><i class="bi bi-exclamation-triangle"></i> ${statusText}</small>`;
            }
            return;
        }

        // Update stage indicators
        const stageEl = element.querySelector(`[data-stage="${stage}"]`);
        if (stageEl) {
            const badge = stageEl.querySelector('.stage-status');
            const progressBar = stageEl.querySelector('.progress-bar');

            if (progress === 0) {
                // Starting
                badge.className = 'stage-status badge bg-primary';
                badge.textContent = 'In Progress';
            } else if (progress >= 1) {
                // Complete
                badge.className = 'stage-status badge bg-success';
                badge.textContent = 'Complete';
            }

            if (progressBar) {
                progressBar.style.width = `${Math.min(100, progress * 100)}%`;
            }
        }

        // Mark previous stages as complete
        const stages = ['planning', 'searching', 'synthesis', 'writing'];
        const currentIndex = stages.indexOf(stage);
        for (let i = 0; i < currentIndex; i++) {
            const prevStage = element.querySelector(`[data-stage="${stages[i]}"]`);
            if (prevStage) {
                const badge = prevStage.querySelector('.stage-status');
                const progressBar = prevStage.querySelector('.progress-bar');
                if (badge) {
                    badge.className = 'stage-status badge bg-success';
                    badge.textContent = 'Complete';
                }
                if (progressBar) {
                    progressBar.style.width = '100%';
                }
            }
        }
    }

    initResearchModeToggle() {
        // Load saved research mode state
        this.researchMode = localStorage.getItem(this.storageKeys.researchMode) === 'true';

        // Find or create research mode toggle button
        const toolsConfigBtn = document.getElementById('toolsConfigBtn');
        if (toolsConfigBtn && !document.getElementById('researchModeToggle')) {
            const toggleBtn = document.createElement('button');
            toggleBtn.id = 'researchModeToggle';
            toggleBtn.className = `btn btn-sm ${this.researchMode ? 'btn-primary' : 'btn-outline-secondary'} ms-2`;
            toggleBtn.innerHTML = '<i class="bi bi-search"></i> Research';
            toggleBtn.title = 'Toggle Deep Research Mode';
            toggleBtn.setAttribute('aria-pressed', this.researchMode);
            toggleBtn.onclick = () => this.toggleResearchMode();

            toolsConfigBtn.parentNode.insertBefore(toggleBtn, toolsConfigBtn.nextSibling);
        }

        // Update UI state
        if (this.researchMode) {
            this.toggleResearchMode();
            this.toggleResearchMode(); // Toggle twice to apply UI without notification
        }
    }
}

// Initialize floating chat when DOM is ready, but only if the required elements exist
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded - Checking for FloatingChat elements');
    
    // Only initialize if the floating chat button exists
    const floatingChatBtn = document.getElementById('floatingChatBtn');
    const floatingChatModal = document.getElementById('floatingChatModal');
    
    if (floatingChatBtn && floatingChatModal) {
        console.log('FloatingChat elements found - Initializing FloatingChat');
        window.floatingChatInstance = new FloatingChat();
    } else {
        console.log('FloatingChat elements not found - Skipping initialization');
        console.log(`floatingChatBtn: ${floatingChatBtn ? 'found' : 'not found'}`);
        console.log(`floatingChatModal: ${floatingChatModal ? 'found' : 'not found'}`);
    }
});