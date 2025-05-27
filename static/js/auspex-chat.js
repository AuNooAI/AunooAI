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
            minimizeBtn: document.getElementById('minimizeChatBtn'),
            quickQueries: document.getElementById('floatingQuickQueries')
        };
        
        // Log found elements
        console.log('Found elements:', {
            button: !!this.elements.button,
            modal: !!this.elements.modal,
            topicSelect: !!this.elements.topicSelect,
            modelSelect: !!this.elements.modelSelect,
            limitSelect: !!this.elements.limitSelect,
            messages: !!this.elements.messages,
            input: !!this.elements.input,
            sendBtn: !!this.elements.sendBtn,
            saveBtn: !!this.elements.saveBtn,
            loading: !!this.elements.loading,
            clearBtn: !!this.elements.clearBtn,
            exportBtn: !!this.elements.exportBtn,
            minimizeBtn: !!this.elements.minimizeBtn,
            quickQueries: !!this.elements.quickQueries
        });
        
        this.storageKeys = {
            topic: 'auspex_floating_last_topic',
            model: 'auspex_floating_last_model',
            limit: 'auspex_floating_last_limit',
            customQueries: 'auspex_floating_custom_queries',
            minimized: 'auspex_floating_minimized',
            chatHistory: 'auspex_floating_chat_history'
        };
        
        this.conversationHistory = this.loadChatHistory();
        this.customQueries = this.loadCustomQueries();
        this.isMinimized = localStorage.getItem(this.storageKeys.minimized) === 'true';
        
        console.log('Initializing chat...');
        // Initialize immediately
        this.init();
    }

    async init() {
        try {
            console.log('Starting initialization...');
            // Initialize dropdowns
            await this.initializeDropdowns();
            console.log('Dropdowns initialized');
            
            // Load saved selections
            this.loadSavedSelections();
            console.log('Saved selections loaded');
            
            // Add event listeners
            this.addEventListeners();
            console.log('Event listeners added');
            
            // Initialize UI state
            this.updateUIState();
            console.log('UI state updated');
        } catch (error) {
            console.error('Error initializing chat:', error);
        }
    }

    async initializeDropdowns() {
        try {
            console.log('Initializing dropdowns...');
            // Fetch topics
            console.log('Fetching topics...');
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
            console.log('Topic options added');

            // Fetch models
            console.log('Fetching models...');
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
            console.log('Model options added');
        } catch (error) {
            console.error('Error initializing dropdowns:', error);
            // Show error in dropdowns
            this.elements.topicSelect.innerHTML = '<option value="">Error loading topics</option>';
            this.elements.modelSelect.innerHTML = '<option value="">Error loading models</option>';
        }
    }

    loadSavedSelections() {
        // Load saved topic
        const savedTopic = localStorage.getItem(this.storageKeys.topic);
        if (savedTopic) {
            this.elements.topicSelect.value = savedTopic;
        }

        // Load saved model
        const savedModel = localStorage.getItem(this.storageKeys.model);
        if (savedModel) {
            this.elements.modelSelect.value = savedModel;
        }

        // Load saved limit
        const savedLimit = localStorage.getItem(this.storageKeys.limit);
        if (savedLimit) {
            this.elements.limitSelect.value = savedLimit;
        }
    }

    addEventListeners() {
        // Topic selection change
        this.elements.topicSelect.addEventListener('change', () => {
            localStorage.setItem(this.storageKeys.topic, this.elements.topicSelect.value);
            this.updateUIState();
        });

        // Model selection change
        this.elements.modelSelect.addEventListener('change', () => {
            localStorage.setItem(this.storageKeys.model, this.elements.modelSelect.value);
            this.updateUIState();
        });

        // Limit selection change
        this.elements.limitSelect.addEventListener('change', () => {
            localStorage.setItem(this.storageKeys.limit, this.elements.limitSelect.value);
        });
    }

    updateUIState() {
        const hasTopic = this.elements.topicSelect.value !== '';
        const hasModel = this.elements.modelSelect.value !== '';
        
        // Enable/disable input and buttons based on selections
        this.elements.input.disabled = !(hasTopic && hasModel);
        this.elements.sendBtn.disabled = !(hasTopic && hasModel);
        this.elements.saveBtn.disabled = !(hasTopic && hasModel);
    }

    loadChatHistory() {
        try {
            const saved = localStorage.getItem(this.storageKeys.chatHistory);
            return saved ? JSON.parse(saved) : [];
        } catch (error) {
            console.error('Error loading chat history:', error);
            return [];
        }
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

    saveChatHistory() {
        try {
            localStorage.setItem(this.storageKeys.chatHistory, JSON.stringify(this.conversationHistory));
        } catch (error) {
            console.error('Error saving chat history:', error);
        }
    }

    saveCustomQueries() {
        try {
            localStorage.setItem(this.storageKeys.customQueries, JSON.stringify(this.customQueries));
        } catch (error) {
            console.error('Error saving custom queries:', error);
        }
    }

    addMessage(content, isUser = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `floating-message ${isUser ? 'user' : 'assistant'}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'floating-message-avatar';
        avatar.innerHTML = isUser ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'floating-message-content';
        
        const textContent = typeof content === 'object' && content.response ? content.response : content;
        
        if (isUser) {
            contentDiv.textContent = textContent;
        } else {
            contentDiv.innerHTML = marked.parse(textContent);
        }
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
        
        if (!isUser) {
            const copyButton = document.createElement('button');
            copyButton.className = 'floating-message-copy';
            copyButton.innerHTML = '<i class="fas fa-copy"></i>';
            copyButton.title = 'Copy message';
            copyButton.onclick = () => this.copyMessage(textContent);
            messageDiv.appendChild(copyButton);
        }
        
        this.elements.messages.appendChild(messageDiv);
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
        
        if (messageDiv !== this.elements.messages.firstElementChild) {
            this.conversationHistory.push({ content: textContent, isUser, timestamp: new Date().toISOString() });
            this.saveChatHistory();
        }
    }

    clearChat() {
        const welcomeMessage = this.elements.messages.querySelector('.floating-message.assistant');
        this.elements.messages.innerHTML = '';
        if (welcomeMessage) {
            this.elements.messages.appendChild(welcomeMessage.cloneNode(true));
        }
        this.conversationHistory = [];
        this.saveChatHistory();
    }

    // ... rest of the existing methods ...
}

// Initialize floating chat when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded - Initializing FloatingChat');
    window.floatingChatInstance = new FloatingChat();
}); 