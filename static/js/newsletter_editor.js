class NewsletterEditor {
    constructor(elementId) {
        this.elementId = elementId;
        this.editor = null;
        this.initialize();
    }

    initialize() {
        const element = document.getElementById(this.elementId);
        if (!element) {
            console.error(`Element with id '${this.elementId}' not found`);
            return;
        }

        // Check if EasyMDE exists
        if (typeof EasyMDE === 'undefined') {
            console.error("EasyMDE not found. Make sure the library is loaded.");
            element.value = "Error: EasyMDE library not loaded. Please check your internet connection.";
            return;
        }

        console.log("Initializing EasyMDE on element:", element);
        
        try {
            // Initialize with improved configuration for EasyMDE
            this.editor = new EasyMDE({
                element: element,
                autoDownloadFontAwesome: false, // We're loading FA ourselves
                spellChecker: false,
                autofocus: true,
                lineWrapping: true,
                tabSize: 4,
                toolbar: [
                    "bold", "italic", "heading", "|",
                    "quote", "unordered-list", "ordered-list", "|",
                    "link", "image", "|",
                    "preview", "side-by-side", "fullscreen", "|",
                    "guide"
                ],
                renderingConfig: {
                    codeSyntaxHighlighting: true,
                    singleLineBreaks: false,
                    sanitizerFunction: (html) => {
                        return html; // Don't sanitize to allow more formatting
                    }
                },
                status: ["autosave", "lines", "words", "cursor"],
                initialValue: "# Test Content\n\nThis is a test to verify the editor is working.",
                maxHeight: "500px",
                placeholder: "Write your newsletter content here..."
            });
            
            console.log("EasyMDE initialized successfully:", this.editor);
            
            // Set up preview renderer
            this.editor.codemirror.on("change", () => {
                this.updatePreview();
            });
            
            // Initial preview
            setTimeout(() => this.updatePreview(), 100);
            
        } catch (error) {
            console.error("Error initializing EasyMDE:", error);
            element.value = "Error initializing editor: " + error.message;
        }
    }

    updatePreview() {
        const previewElement = document.getElementById('preview-content');
        if (!previewElement || !this.editor) return;

        const content = this.getValue();
        if (!content || !content.trim()) {
            previewElement.innerHTML = '<p>Preview will appear here...</p>';
            return;
        }

        try {
            // Use marked for rendering markdown
            if (typeof marked !== 'undefined') {
                const html = marked.parse(content);
                previewElement.innerHTML = html;
                
                // Apply syntax highlighting to code blocks
                if (window.hljs) {
                    document.querySelectorAll('pre code').forEach((block) => {
                        hljs.highlightBlock(block);
                    });
                }
            } else {
                // Basic fallback rendering if marked is not loaded
                const html = content
                    .replace(/^# (.*$)/gm, '<h1>$1</h1>')
                    .replace(/^## (.*$)/gm, '<h2>$1</h2>')
                    .replace(/^### (.*$)/gm, '<h3>$1</h3>')
                    .replace(/\*\*(.*)\*\*/gm, '<strong>$1</strong>')
                    .replace(/\*(.*)\*/gm, '<em>$1</em>')
                    .replace(/\n/gm, '<br>');
                
                previewElement.innerHTML = html;
            }
        } catch (error) {
            console.error("Error updating preview:", error);
            previewElement.innerHTML = `<p class="text-danger">Error rendering preview: ${error.message}</p>`;
        }
    }

    getValue() {
        return this.editor ? this.editor.value() : '';
    }

    setValue(content) {
        if (this.editor) {
            this.editor.value(content);
            this.updatePreview();
        }
    }
} 