let isProcessing = false;
let isSearchEnabled = false;
let isEnglish = false;

document.addEventListener("DOMContentLoaded", function () {
    loadHistory();
    initializeEventListeners();
});

function autoResizeInput(element) {
    element.style.height = 'auto';
    const newHeight = Math.min(Math.max(element.scrollHeight, 24), 200);
    element.style.height = newHeight + 'px';
}

function initializeEventListeners() {
    const userInput = document.getElementById("user-input");
    if (userInput.tagName.toLowerCase() === 'input') {
        const textarea = document.createElement('textarea');
        textarea.id = 'user-input';
        textarea.placeholder = userInput.placeholder;
        textarea.className = userInput.className;
        userInput.parentNode.replaceChild(textarea, userInput);
    }
    document.getElementById("user-input").addEventListener("input", function () {
        autoResizeInput(this);
    });

    document.getElementById("user-input").addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    document.getElementById("send-button").addEventListener("click", sendMessage);
    document.getElementById("search-button").addEventListener("click", toggleSearch);
    document.getElementById("logout-button").addEventListener("click", logout);
    document.getElementById("push-button").addEventListener("click", pushNews);

    const fileUploadButton = document.getElementById("file-upload-button");
    const fileInput = document.getElementById("file-input");

    fileUploadButton.addEventListener("click", () => {
        fileInput.click();
    });

    fileInput.addEventListener("change", (event) => {
        const file = event.target.files[0];
        if (file) {
            uploadFile(file);
        }
    });
}

function toggleSearch() {
    isSearchEnabled = !isSearchEnabled;
    const searchButton = document.getElementById("search-button");
    searchButton.innerHTML = `<i class="fas fa-search"></i> ${isSearchEnabled ? 'Disable search' : 'Enable search'}`;
    searchButton.style.backgroundColor = isSearchEnabled ? '#cc0000' : '#4CAF50';
}

// 消息处理
function addMessage(sender, content) {
    const chatBox = document.getElementById("chat-box");
    const messageDiv = document.createElement("div");
    messageDiv.classList.add("message", sender);

    if (sender === 'bot') {
        const contentDiv = document.createElement("div");
        contentDiv.className = "message-content";

        if (content === (isEnglish ? "Thinking..." : "思考中...")) {
            contentDiv.textContent = content;
        } else {
            // 立即应用 Markdown 格式
            contentDiv.innerHTML = formatMarkdownContent(content);
        }

        messageDiv.appendChild(contentDiv);
    } else {
        const messageSpan = document.createElement("span");
        messageSpan.textContent = content;
        messageDiv.appendChild(messageSpan);
    }

    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    return messageDiv.querySelector(".message-content") || messageDiv.querySelector("span");
}

// 思考部分区域
function createThinkSection(content) {
    const thinkSection = document.createElement("div");
    thinkSection.className = "think-section";

    const thinkLabel = document.createElement("div");
    thinkLabel.className = "section-label";
    thinkLabel.textContent = isEnglish ? "Thinking Process" : "思考中";

    const thinkText = document.createElement("div");
    thinkText.innerHTML = formatMarkdownContent(content);

    thinkSection.appendChild(thinkLabel);
    thinkSection.appendChild(thinkText);

    return thinkSection;
}

// 响应部分区域
function createResponseSection(content) {
    const responseSection = document.createElement("div");
    responseSection.className = "response-section";

    const responseLabel = document.createElement("div");
    responseLabel.className = "section-label";
    responseLabel.textContent = isEnglish ? "Response" : "回答";

    const responseText = document.createElement("div");
    responseText.className = "markdown-content";
    responseText.innerHTML = formatMarkdownContent(content);

    responseSection.appendChild(responseLabel);
    responseSection.appendChild(responseText);

    return responseSection;
}


// 创建分隔线
function createDivider() {
    const divider = document.createElement("div");
    divider.className = "section-divider";
    return divider;
}

// Markdown格式
function formatMarkdownContent(content) {
    if (!content) return '';

    try {
        return content
            .replace(/```(\w+)?\n([\s\S]+?)```/g, (match, lang, code) => {
                return `<pre><code class="language-${lang || ''}">${code.trim()}</code></pre>`;
            })
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/#{1,6}\s?([^\n]+)/g, (match, text) => {
                const level = match.trim().split('#').length - 1;
                return `<h${level} class="markdown-heading">${text.trim()}</h${level}>`;
            })
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em>$1</em>')
            .replace(/```(\w+)?\n([\s\S]+?)```/g, '<pre><code class="language-$1">$2</code></pre>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n\n/g, '<br><br>');
    } catch (error) {
        console.error('Markdown formatting error:', error);
        return content;
    }
}

// 文件处理函数
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatContent(content) {
    return content.replace(/\n/g, '<br>').replace(/\s/g, '&nbsp;');
}

// API 相关函数
async function sendMessage() {
    const userInput = document.getElementById("user-input");
    const message = userInput.value.trim();

    if (!message || isProcessing) return;

    isEnglish = isEnglishText(message);
    addMessage("user", message);
    const thinkingMessage = addMessage("bot", isEnglish ? "Thinking..." : "think...");

    userInput.value = "";
    toggleInputState(true);
    isProcessing = true;

    try {
        if (isSearchEnabled) {
            await searchAndProcess(message, thinkingMessage);
        } else {
            await chat(message, thinkingMessage);
        }
    } finally {
        isProcessing = false;
        toggleInputState(false);
    }
}

function isEnglishText(text) {
    return /^[a-zA-Z0-9\s.,!?-]+$/.test(text);
}

function toggleInputState(disabled) {
    const userInput = document.getElementById("user-input");
    const sendButton = document.getElementById("send-button");
    userInput.disabled = disabled;
    sendButton.disabled = disabled;
}

// 图片处理
class ImageHandler {
    constructor() {
        this.initializeUI();
        this.setupEventListeners();
    }

    initializeUI() {
        this.imageUploadButton = document.getElementById('image-upload-button');
        this.imageInput = document.getElementById('image-input');
    }

    setupEventListeners() {
        this.imageUploadButton.addEventListener('click', () => this.imageInput.click());
        this.imageInput.addEventListener('change', (e) => this.handleImageUpload(e));
    }

    async handleImageUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        addMessage('user', `[upload pictures: ${file.name}]`);
        const loadingMessage = addMessage('bot', `Processing images: ${file.name}...`);

        try {
            const previewUrl = URL.createObjectURL(file);
            await this.processAndDisplayImage(file, previewUrl, loadingMessage);
        } catch (error) {
            loadingMessage.textContent = `错误: ${error.message}`;
        } finally {
            this.imageInput.value = '';
        }
    }

    async processAndDisplayImage(file, previewUrl, loadingMessage) {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/api/image/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.status === 'success') {
            loadingMessage.parentElement.remove();
            addMessage('bot', data.description || data.formatted_text);

            const chatBox = document.getElementById("chat-box");
            chatBox.scrollTop = chatBox.scrollHeight;
        } else {
            throw new Error(data.message || 'Image processing failed');
        }
    }
}

// 搜索功能
async function searchAndProcess(query, thinkingMessage) {
    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('搜索请求失败');

        const data = await response.json();
        if (data.error) throw new Error(data.error);

        // 处理搜索响应
        if (data.llm_response) {
            let responseContent = '';

            if (typeof data.llm_response === 'object') {
                responseContent = data.llm_response.content;
            } else {
                responseContent = data.llm_response;
            }

            // 格式化并显示响应
            if (thinkingMessage && thinkingMessage.parentElement) {
                const contentDiv = document.createElement("div");
                contentDiv.className = "message-content markdown-content";
                contentDiv.innerHTML = formatSearchResponse(responseContent);
                thinkingMessage.parentElement.replaceChild(contentDiv, thinkingMessage);
            }
        }

        // 显示搜索结果
        if (data.search_results?.length > 0) {
            displaySearchResults(data.search_results);
        }
    } catch (err) {
        console.error('Search error:', err);
        if (thinkingMessage) {
            thinkingMessage.textContent = `错误：${err.message}`;
        }
    }
}

async function chat(message, thinkingMessage) {
    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ message })
        });

        if (!response.ok) {
            throw new Error(isEnglish ? 'Chat request failed' : '对话请求失败');
        }

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error || (isEnglish ? 'Unknown error' : '未知错误'));
        }

        if (data.response) {
            const responseDiv = document.createElement('div');
            responseDiv.className = 'message-content markdown-content';

            // 创建思考部分（如果有推理内容）
            let thinkContent = '';
            if (data.response.reasoning_content) {
                thinkContent = `
                    <div class="think-section">
                        <div class="section-label">${isEnglish ? 'Thinking Process' : '思考中'}</div>
                        ${formatMarkdownContent(data.response.reasoning_content)}
                    </div>
                    <div class="section-divider"></div>
                `;
            }

            // 创建响应部分
            const content = data.response.content || data.response;
            const responseContent = `
                <div class="response-section">
                    <div class="section-label">${isEnglish ? 'Response' : 'Response'}</div>
                    ${formatMarkdownContent(content)}
                </div>
            `;

            // 组合完整响应
            responseDiv.innerHTML = thinkContent + responseContent;

            // thinking 消息格式
            if (thinkingMessage.parentElement) {
                thinkingMessage.parentElement.replaceChild(responseDiv, thinkingMessage);
            }

            // 确保新内容可见
            const chatBox = document.getElementById("chat-box");
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    } catch (err) {
        if (thinkingMessage) {
            thinkingMessage.textContent = `${isEnglish ? 'Error: ' : '错误：'}${err.message}`;
        }
    }
}

function displaySearchResults(results) {
    const chatBox = document.getElementById("chat-box");
    const resultsDiv = document.createElement("div");
    resultsDiv.className = "search-results message bot";

    if (!results || results.length === 0) {
        resultsDiv.textContent = isEnglish ? "No results found" : "没有找到相关结果";
    } else {
        resultsDiv.innerHTML = results.map((result, index) => `
            <div class="search-result">
                <div class="result-title">${index + 1}. ${result.title || (isEnglish ? 'No title' : '无标题')}</div>
                <div class="result-description">${result.abstract || result.description || (isEnglish ? 'No description' : '无描述')}</div>
                <div class="result-url"><a href="${result.url}" target="_blank">${result.url}</a></div>
            </div>
        `).join('');
    }

    chatBox.appendChild(resultsDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// 历史记录函数
async function loadHistory() {
    try {
        const response = await fetch("/api/history");
        if (!response.ok) {
            throw new Error(isEnglish ? 'Failed to load history' : '加载历史记录失败');
        }

        const data = await response.json();
        if (data.history) {
            renderHistory(data.history);
        }
    } catch (err) {
        console.error("History error:", err);
    }
}

function formatSearchResponse(content) {
    content = content.replace(/\\n/g, '\n')
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, '\\')
        .replace(/, *'reasoning_content': *None\}$/g, '')
        .replace(/, *"reasoning_content": *null\}$/g, '');
    // 将think标签格式化(如果存在且不为空)
    content = content.replace(/<think>([\s\S]*?)<\/think>/g, (match, thinkContent) => {
        const trimmedThinkContent = thinkContent.trim();
        // 如果思考内容为空,直接返回空字符串
        if (!trimmedThinkContent) {
            return '';
        }
        // 否则返回格式化的思考部分
        return `<div class="think-section">
            <div class="section-label">thinking</div>
            <div class="think-content">${trimmedThinkContent}</div>
        </div>
        <div class="section-divider"></div>`;
    });
    // 将搜索响应解析为结构化内容
    const sections = content.split('\n\n');
    let formattedContent = '';

    sections.forEach(section => {
        if (section.trim()) {
            if (section.startsWith('###')) {
                formattedContent += `${section}\n\n`;
            } else {
                formattedContent += `${section.trim()}\n\n`;
            }
        }
    });
    return formatMarkdownContent(formattedContent);
}

function renderHistory(history) {
    const chatBox = document.getElementById("chat-box");
    chatBox.innerHTML = "";

    history.forEach(message => {
        if (message.content?.trim()) {
            const messageElement = document.createElement("div");
            messageElement.className = `message ${message.role === "user" ? "user" : "bot"}`;

            if (message.role === "user") {
                const messageSpan = document.createElement("span");
                messageSpan.textContent = message.content;
                messageElement.appendChild(messageSpan);
            } else {
                const contentDiv = document.createElement("div");
                contentDiv.className = "message-content markdown-content";

                if (message.content.includes("[Search Response]")) {
                    const formattedContent = formatSearchResponse(message.content);
                    if (formattedContent.trim()) {
                        contentDiv.innerHTML = formattedContent;
                        messageElement.appendChild(contentDiv);
                    }
                } else {
                    contentDiv.innerHTML = formatMarkdownContent(message.content);
                    messageElement.appendChild(contentDiv);
                }
            }
            if (messageElement.children.length > 0) {
                chatBox.appendChild(messageElement);
            }
        }
    });
    chatBox.scrollTop = chatBox.scrollHeight;
}

// 文件上传函数
async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const processingMessage = addMessage('bot', `Processing file: ${file.name}...`);

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.status === 'success') {
            processingMessage.innerHTML = `
                <div class="file-processing">
                    <strong>File processed successfully:</strong><br>
                    <small>
                        Size: ${formatFileSize(data.metadata.file_size)}<br>
                        ${Object.entries(data.metadata)
                    .filter(([key]) => key !== 'file_size')
                    .map(([key, value]) => `${key}: ${value}`)
                    .join('<br>')}
                    </small>
                    <hr>
                    <div class="file-content">${formatContent(data.content)}</div>
                </div>
            `;
        } else {
            processingMessage.textContent = `Error processing file: ${data.message}`;
        }
    } catch (error) {
        processingMessage.textContent = `Error uploading file: ${error.message}`;
    } finally {
        document.getElementById('file-input').value = '';
    }
}

// 登出函数
async function logout() {
    try {
        const response = await fetch("/logout");
        if (response.redirected) {
            window.location.href = response.url;
        }
    } catch (err) {
        console.error("Logout error:", err);
    }
}

// 新闻推送函数
async function pushNews() {
    const loadingMessage = addMessage("bot", "Get the latest news...");

    try {
        const response = await fetch("/api/push-news");
        if (!response.ok) {
            throw new Error('获取news fail');
        }

        const data = await response.json();

        // 移除加载消息
        if (loadingMessage.parentElement) {
            loadingMessage.parentElement.remove();
        }

        // 如果有新闻项目，即使摘要生成失败也显示它们
        if (data.news_items?.length > 0) {
            const chatBox = document.getElementById("chat-box");
            const newsContainer = document.createElement("div");
            newsContainer.className = "news-container message bot";

            data.news_items.forEach(item => {
                const newsCard = document.createElement("div");
                newsCard.className = `news-card ${item.source?.toLowerCase() || 'unknown'}`;

                // 处理summary为"Unable to generate summary"的情况
                const summaryContent = item.summary === "Unable to generate summary" ?
                    "点击阅读更多查看详细内容" : (item.summary || "暂无摘要");

                newsCard.innerHTML = `
                    <div class="news-card-content">
                        <div class="news-source">${(item.source || 'Unknown').toUpperCase()}</div>
                        <div class="news-title">${item.title || '无标题'}</div>
                        <div class="news-summary">${summaryContent}</div>
                        <a href="${item.url || '#'}" target="_blank" class="news-link">
                            read more <i class="fas fa-external-link-alt"></i>
                        </a>
                    </div>
                `;
                newsContainer.appendChild(newsCard);
            });

            chatBox.appendChild(newsContainer);
            chatBox.scrollTop = chatBox.scrollHeight;
        } else {
            addMessage("bot", "暂时没有新的新闻");
        }
    } catch (err) {
        console.error('News error:', err);
        if (loadingMessage) {
            loadingMessage.textContent = `获取新闻失败: ${err.message}`;
        } else {
            addMessage("bot", `获取新闻失败: ${err.message}`);
        }
    }
}
// 帮助格式化新闻内容的辅助函数
function formatNewsContent(content) {
    if (!content || typeof content !== 'string') return '暂无内容';
    if (content === "Unable to generate summary") return "read more";
    return content.trim();
}

function displayNewsItems(newsItems) {
    const newsContainer = document.createElement("div");
    newsContainer.className = "news-container message bot";

    newsItems.forEach(item => {
        const source = item.source || 'unknown';
        const title = item.title || '无标题';
        const summary = item.summary || item.content || '无内容';
        const url = item.url || '#';
        const newsCard = document.createElement("div");
        newsCard.className = `news-card ${source.toLowerCase()}`;
        newsCard.innerHTML = `
            <div class="news-card-content">
                <div class="news-source">${source.toUpperCase()}</div>
                <div class="news-title">${formatMarkdownContent(title)}</div>
                <div class="news-summary">${formatMarkdownContent(summary)}</div>
                <a href="${url}" target="_blank" class="news-link">
                    read more <i class="fas fa-external-link-alt"></i>
                </a>
            </div>
        `;
        newsContainer.appendChild(newsCard);
    });

    const chatBox = document.getElementById("chat-box");
    if (chatBox) {
        chatBox.appendChild(newsContainer);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
}

function displayNewsItems(newsItems) {
    const newsContainer = document.createElement("div");
    newsContainer.className = "news-container message bot markdown-content";

    newsItems.forEach(item => {
        const newsCard = document.createElement("div");
        newsCard.className = `news-card ${item.source}`;

        // 使用 Markdown 格式化新闻内容
        const formattedTitle = formatMarkdownContent(`## ${item.title}`);
        const formattedSummary = formatMarkdownContent(item.summary);

        newsCard.innerHTML = `
            <div class="news-card-content">
                <div class="news-source ${item.source.toLowerCase()}">${item.source.toUpperCase()}</div>
                <div class="news-title">${formattedTitle}</div>
                <div class="news-summary">${formattedSummary}</div>
                <a href="${item.url}" target="_blank" class="news-link">
                    ${item.language === 'en' ? 'Read more' : 'read more'} 
                    <i class="fas fa-external-link-alt"></i>
                </a>
            </div>
        `;
        newsContainer.appendChild(newsCard);
    });

    const chatBox = document.getElementById("chat-box");
    chatBox.appendChild(newsContainer);
    chatBox.scrollTop = chatBox.scrollHeight;
}

const imageHandler = new ImageHandler();

// 导出全局函数
window.pushNews = pushNews;
window.toggleSearch = toggleSearch;
window.sendMessage = sendMessage;
window.logout = logout;