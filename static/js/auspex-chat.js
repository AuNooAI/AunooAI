class FloatingChat {
    constructor() {
        console.log('FloatingChat constructor called');
        this.elements = {
            button: document.getElementById('floatingChatBtn'),
            modal: document.getElementById('floatingChatModal'),
            topicSelect: document.getElementById('floatingTopicSelect'),
            modelSelect: document.getElementById('floatingModelSelect'),
            limitSelect: document.getElementById('floatingLimitSelect'),
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
            toolsToggleBtn: document.getElementById('toolsToggleBtn')
        };
        
        // Chat state
        this.currentChatId = null;
        this.chatSessions = [];
        this.isStreaming = false;
        this.modalInstance = null;
        
        this.storageKeys = {
            topic: 'auspex_floating_last_topic',
            model: 'auspex_floating_last_model',
            limit: 'auspex_floating_last_limit',
            customQueries: 'auspex_floating_custom_queries',
            minimized: 'auspex_floating_minimized',
            toolsEnabled: 'auspex_floating_tools_enabled'
        };
        
        this.customQueries = this.loadCustomQueries();
        this.isMinimized = localStorage.getItem(this.storageKeys.minimized) === 'true';
        this.toolsEnabled = localStorage.getItem(this.storageKeys.toolsEnabled) !== 'false'; // Default to true
        
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
        
        // Add specific event listeners for buttons that might have been missing
        if (this.elements.toggleSidebar && !this.elements.toggleSidebar.hasAttribute('data-listener-added')) {
            this.elements.toggleSidebar.addEventListener('click', (e) => {
                console.log('Toggle sidebar clicked via modal show listener');
                e.preventDefault();
                e.stopPropagation();
                this.toggleSidebar();
            });
            this.elements.toggleSidebar.setAttribute('data-listener-added', 'true');
            console.log('✓ Added toggle sidebar listener after modal show');
        }
        
        if (this.elements.expandWindowBtn && !this.elements.expandWindowBtn.hasAttribute('data-listener-added')) {
            this.elements.expandWindowBtn.addEventListener('click', (e) => {
                console.log('Expand window clicked via modal show listener');
                e.preventDefault();
                e.stopPropagation();
                this.toggleExpandWindow();
            });
            this.elements.expandWindowBtn.setAttribute('data-listener-added', 'true');
            console.log('✓ Added expand window listener after modal show');
        }
        
        if (this.elements.toolsToggleBtn && !this.elements.toolsToggleBtn.hasAttribute('data-listener-added')) {
            this.elements.toolsToggleBtn.addEventListener('click', (e) => {
                console.log('Tools toggle clicked via modal show listener');
                e.preventDefault();
                e.stopPropagation();
                this.toggleTools();
            });
            this.elements.toolsToggleBtn.setAttribute('data-listener-added', 'true');
            console.log('✓ Added tools toggle listener after modal show');
        }
        
        // If still missing critical elements, try again after a longer delay
        if (!this.elements.sessionsList || !this.elements.sidebar) {
            console.log('Critical elements still missing, trying again in 500ms...');
            setTimeout(() => {
                this.retryElementInitialization();
            }, 500);
        } else {
            // Update UI state now that elements are available
            this.updateUIState();
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
            
            // Add event listeners for the newly found elements
            if (this.elements.toggleSidebar && !this.elements.toggleSidebar.hasAttribute('data-listener-added')) {
                this.elements.toggleSidebar.addEventListener('click', (e) => {
                    console.log('Toggle sidebar clicked via retry listener');
                    e.preventDefault();
                    e.stopPropagation();
                    this.toggleSidebar();
                });
                this.elements.toggleSidebar.setAttribute('data-listener-added', 'true');
                console.log('✓ Added toggle sidebar listener on retry');
            }
            
            if (this.elements.expandWindowBtn && !this.elements.expandWindowBtn.hasAttribute('data-listener-added')) {
                this.elements.expandWindowBtn.addEventListener('click', (e) => {
                    console.log('Expand window clicked via retry listener');
                    e.preventDefault();
                    e.stopPropagation();
                    this.toggleExpandWindow();
                });
                this.elements.expandWindowBtn.setAttribute('data-listener-added', 'true');
                console.log('✓ Added expand window listener on retry');
            }
            
            if (this.elements.toolsToggleBtn && !this.elements.toolsToggleBtn.hasAttribute('data-listener-added')) {
                this.elements.toolsToggleBtn.addEventListener('click', (e) => {
                    console.log('Tools toggle clicked via retry listener');
                    e.preventDefault();
                    e.stopPropagation();
                    this.toggleTools();
                });
                this.elements.toolsToggleBtn.setAttribute('data-listener-added', 'true');
                console.log('✓ Added tools toggle listener on retry');
            }
            
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

        const savedLimit = localStorage.getItem(this.storageKeys.limit);
        if (savedLimit) {
            this.elements.limitSelect.value = savedLimit;
        }
        
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
            });
        }

        // Limit selection change
        if (this.elements.limitSelect) {
            this.elements.limitSelect.addEventListener('change', () => {
                localStorage.setItem(this.storageKeys.limit, this.elements.limitSelect.value);
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

        // Use event delegation for buttons that might not be available initially
        document.addEventListener('click', (e) => {
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
            
            // Check if the clicked element or any of its parents is the tools toggle button
            const toolsToggleBtn = e.target.closest('#toolsToggleBtn');
            if (toolsToggleBtn) {
                console.log('Tools toggle clicked via delegation');
                e.preventDefault();
                e.stopPropagation();
                this.toggleTools();
                return;
            }
        });
        
        // Also try direct event listeners if elements exist
        if (this.elements.toggleSidebar) {
            this.elements.toggleSidebar.addEventListener('click', (e) => {
                console.log('Toggle sidebar clicked via direct listener');
                e.preventDefault();
                e.stopPropagation();
                this.toggleSidebar();
            });
            console.log('✓ Toggle sidebar element found and direct listener added');
        } else {
            console.warn('✗ Toggle sidebar button not found initially');
        }

        if (this.elements.expandWindowBtn) {
            this.elements.expandWindowBtn.addEventListener('click', (e) => {
                console.log('Expand window clicked via direct listener');
                e.preventDefault();
                e.stopPropagation();
                this.toggleExpandWindow();
            });
            console.log('✓ Expand window element found and direct listener added');
        } else {
            console.warn('✗ Expand window button not found initially');
        }

        if (this.elements.toolsToggleBtn) {
            this.elements.toolsToggleBtn.addEventListener('click', (e) => {
                console.log('Tools toggle clicked via direct listener');
                e.preventDefault();
                e.stopPropagation();
                this.toggleTools();
            });
            console.log('✓ Tools toggle element found and direct listener added');
        } else {
            console.warn('✗ Tools toggle button not found initially');
        }

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
            
            // Create new chat session if none exists and we don't already have an active chat
            if (this.chatSessions.length === 0 && !this.currentChatId) {
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
            const requestBody = {
                topic: topic,
                title: `Chat about ${topic}`
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

        const topic = this.elements.topicSelect ? this.elements.topicSelect.value : '';
        const model = this.elements.modelSelect ? this.elements.modelSelect.value : '';
        const limit = this.elements.limitSelect ? parseInt(this.elements.limitSelect.value) || 50 : 50;

        console.log(`DEBUG: sendMessage called with:`, {
            message,
            topic,
            model,
            limit,
            currentChatId: this.currentChatId,
            hasChat: this.currentChatId !== null,
            toolsEnabled: this.toolsEnabled
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
                    use_tools: this.toolsEnabled
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
        contentDiv.innerHTML = marked.parse(content);
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
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
        
        // Update tools toggle button state
        if (this.elements.toolsToggleBtn) {
            if (this.toolsEnabled) {
                this.elements.toolsToggleBtn.classList.add('active');
                this.elements.toolsToggleBtn.title = 'Tools enabled - Click to disable';
                this.elements.toolsToggleBtn.setAttribute('data-bs-original-title', 'Tools enabled - Click to disable');
            } else {
                this.elements.toolsToggleBtn.classList.remove('active');
                this.elements.toolsToggleBtn.title = 'Tools disabled - Click to enable';
                this.elements.toolsToggleBtn.setAttribute('data-bs-original-title', 'Tools disabled - Click to enable');
            }
        }
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
            const chatData = {
                chat_id: this.currentChatId,
                topic: this.elements.topicSelect.value,
                model: this.elements.modelSelect.value,
                exported_at: new Date().toISOString(),
                messages: data.messages
            };

            const blob = new Blob([JSON.stringify(chatData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `auspex-chat-${this.currentChatId}-${new Date().toISOString().split('T')[0]}.json`;
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

    toggleTools() {
        console.log('toggleTools called');
        
        this.toolsEnabled = !this.toolsEnabled;
        localStorage.setItem(this.storageKeys.toolsEnabled, this.toolsEnabled.toString());
        
        // Update button appearance
        if (this.elements.toolsToggleBtn) {
            if (this.toolsEnabled) {
                this.elements.toolsToggleBtn.classList.add('active');
                this.elements.toolsToggleBtn.title = 'Tools enabled - Click to disable';
                this.elements.toolsToggleBtn.setAttribute('data-bs-original-title', 'Tools enabled - Click to disable');
            } else {
                this.elements.toolsToggleBtn.classList.remove('active');
                this.elements.toolsToggleBtn.title = 'Tools disabled - Click to enable';
                this.elements.toolsToggleBtn.setAttribute('data-bs-original-title', 'Tools disabled - Click to enable');
            }
        }
        
        console.log(`Tools ${this.toolsEnabled ? 'enabled' : 'disabled'}`);
        
        // Show a brief notification
        this.showToolsNotification(this.toolsEnabled);
    }

    showToolsNotification(enabled) {
        const notification = document.createElement('div');
        notification.textContent = `Tools ${enabled ? 'enabled' : 'disabled'}`;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${enabled ? '#28a745' : '#dc3545'};
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
        }, 2000);
    }
}

// Initialize floating chat when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded - Initializing FloatingChat');
    window.floatingChatInstance = new FloatingChat();
});