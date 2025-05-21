// API functions for newsletter compiler
async function loadTopics() {
    try {
        const response = await fetch('/api/newsletter/topics');
        if (!response.ok) {
            throw new Error(`Failed to fetch topics: ${response.status} ${response.statusText}`);
        }
        
        const topics = await response.json();
        const topicsSelect = document.getElementById('topics');
        
        // Clear existing options and loading message
        topicsSelect.innerHTML = '';
        
        // Add topics as options
        topics.forEach(topic => {
            const option = document.createElement('option');
            option.value = topic;
            option.textContent = topic;
            topicsSelect.appendChild(option);
        });
        
        console.log(`Loaded ${topics.length} topics`);
    } catch (error) {
        console.error('Error loading topics:', error);
        
        // Add fallback topics if API fails
        const fallbackTopics = ["AI and Machine Learning", "Trend Monitoring", "Competitor Analysis"];
        const topicsSelect = document.getElementById('topics');
        
        // Clear existing options and loading message
        topicsSelect.innerHTML = '';
        
        // Add fallback topics
        fallbackTopics.forEach(topic => {
            const option = document.createElement('option');
            option.value = topic;
            option.textContent = topic;
            topicsSelect.appendChild(option);
        });
    }
}

async function loadContentTypes() {
    try {
        const response = await fetch('/api/newsletter/content_types');
        if (!response.ok) {
            throw new Error(`Failed to fetch content types: ${response.status} ${response.statusText}`);
        }
        
        const contentTypes = await response.json();
        const contentTypesTable = document.getElementById('contentTypesTable');
        
        // Clear existing content
        contentTypesTable.innerHTML = '';
        
        // Create table rows for content types
        let tableHtml = '';
        for (let i = 0; i < contentTypes.length; i++) {
            const contentType = contentTypes[i];
            const rowClass = i % 2 === 0 ? 'bg-light' : '';
            
            tableHtml += `
                <tr class="${rowClass}">
                    <td>
                        <div class="d-flex flex-column">
                            <strong>${contentType.name}</strong>
                            <small class="text-muted">${contentType.description}</small>
                        </div>
                    </td>
                    <td class="text-center">
                        <div class="custom-control custom-checkbox">
                            <input type="checkbox" class="custom-control-input content-type-checkbox" 
                                   id="contentType_${contentType.id}" name="contentTypes" value="${contentType.id}">
                            <label class="custom-control-label" for="contentType_${contentType.id}"></label>
                        </div>
                    </td>
                    <td class="text-right">
                        <button type="button" class="btn btn-sm btn-outline-secondary edit-prompt-btn"
                                data-content-type-id="${contentType.id}"
                                data-toggle="tooltip" data-placement="left"
                                title="Edit prompt template for ${contentType.name}">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                    </td>
                </tr>
            `;
        }
        
        contentTypesTable.innerHTML = tableHtml;
        
        // Add select all functionality
        const selectAllBtn = document.getElementById('selectAllContentTypes');
        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', function() {
                const checkboxes = document.querySelectorAll('input[name="contentTypes"]');
                const allChecked = Array.from(checkboxes).every(checkbox => checkbox.checked);
                
                // Toggle all checkboxes based on current state
                checkboxes.forEach(checkbox => {
                    checkbox.checked = !allChecked;
                });
                
                // Update button text
                selectAllBtn.textContent = allChecked ? 'Select All' : 'Deselect All';
            });
        }

        // Initialize tooltips
        if (typeof jQuery !== 'undefined') {
            jQuery('[data-toggle="tooltip"]').tooltip();
        }
        
        console.log(`Loaded ${contentTypes.length} content types`);
    } catch (error) {
        console.error('Error loading content types:', error);
        const contentTypesTable = document.getElementById('contentTypesTable');
        contentTypesTable.innerHTML = `
            <tr>
                <td colspan="3" class="text-danger">Error loading content types. Please refresh the page or try again later.</td>
            </tr>
        `;
    }
} 