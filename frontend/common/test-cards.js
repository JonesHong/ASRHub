// Test Cards Configuration and Dynamic Rendering

const testCards = [
    {
        id: 'protocol-test',
        title: '通訊協議測試',
        status: 'ready',
        statusText: '可用',
        description: '測試不同的通訊協議：WebSocket、Socket.io 和 HTTP SSE。支援即時錄音和檔案上傳。',
        path: 'protocol-test/',
        features: ['WebSocket', 'Socket.io', 'HTTP SSE', '即時錄音', '檔案上傳']
    },
    {
        id: 'realtime-test',
        title: '即時語音處理',
        status: 'development',
        statusText: '開發中',
        description: '測試完整的即時語音處理流程，包含 VAD 偵測、自動錄音和語音轉文字。',
        path: 'realtime-test/',
        features: ['連續音訊串流', 'VAD 偵測', '自動錄音', '語音轉文字'],
        expectedDate: '2024 Q2'
    },
    {
        id: 'vad-test',
        title: 'VAD 功能測試',
        status: 'development',
        statusText: '開發中',
        description: '專門測試語音活動偵測（VAD）功能，包含靜音偵測和自動停止錄音。',
        path: 'vad-test/',
        features: ['語音活動偵測', '靜音計時', '自動觸發', '波形顯示'],
        expectedDate: '2024 Q2'
    },
    {
        id: 'wakeword-test',
        title: '喚醒詞偵測',
        status: 'planned',
        statusText: '計劃中',
        description: '測試喚醒詞偵測功能，支援自定義喚醒詞和敏感度調整。',
        path: 'wakeword-test/',
        features: ['自定義喚醒詞', '敏感度調整', '多語言支援', '誤觸發測試'],
        expectedDate: '2024 Q3'
    },
    {
        id: 'batch-test',
        title: '批次處理測試',
        status: 'planned',
        statusText: '計劃中',
        description: '測試批次音訊檔案處理功能，支援多檔案上傳和並行處理。',
        path: 'batch-test/',
        features: ['多檔案上傳', '並行處理', '進度追蹤', '結果匯出'],
        expectedDate: '2024 Q3'
    },
    {
        id: 'fsm-test',
        title: 'FCM 狀態機測試',
        status: 'ready',
        statusText: '可用',
        description: '測試 FCM 狀態機的完整流程，包含狀態轉換、事件觸發、歷史記錄和視覺化圖表。',
        path: 'fsm-test/',
        features: ['狀態轉換', '事件觸發', '歷史追蹤', '流程圖視覺化', '測試場景']
    }
];

// Status configuration
const statusConfig = {
    ready: {
        class: 'bg-green-100 text-green-800',
        icon: 'fa-check-circle',
        iconColor: 'text-green-500',
        clickable: true
    },
    development: {
        class: 'bg-orange-100 text-orange-800',
        icon: 'fa-code',
        iconColor: 'text-orange-500',
        clickable: true
    },
    planned: {
        class: 'bg-gray-100 text-gray-800',
        icon: 'fa-calendar',
        iconColor: 'text-gray-500',
        clickable: true
    }
};

// Create a single test card element
function createTestCard(cardData) {
    const card = document.createElement('div');
    card.className = 'bg-white dark:bg-gray-800 rounded-xl shadow-lg hover:shadow-xl dark:shadow-gray-900 transition-all duration-300 p-6 cursor-pointer transform hover:scale-105 animate-fade-in';
    card.dataset.testId = cardData.id;
    card.dataset.status = cardData.status;
    
    const statusConfig = getStatusConfig(cardData.status);
    const statusBadge = `
        <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${statusConfig.class}">
            <i class="fas ${statusConfig.icon} mr-1"></i>
            ${cardData.statusText}
        </span>
    `;
    
    const featuresHtml = cardData.features ? 
        `<div class="flex flex-wrap gap-2 mt-3">
            ${cardData.features.map(f => `<span class="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-md text-xs font-medium">${f}</span>`).join('')}
        </div>` : '';
    
    const expectedDateHtml = cardData.expectedDate ? 
        `<div class="text-sm text-gray-500 dark:text-gray-400 mt-3 italic">
            <i class="far fa-clock mr-1"></i>預計時間：${cardData.expectedDate}
        </div>` : '';
    
    card.innerHTML = `
        <div class="flex justify-between items-start mb-3">
            <h3 class="text-xl font-bold text-gray-800 dark:text-gray-200">${cardData.title}</h3>
            ${statusBadge}
        </div>
        <p class="text-gray-600 dark:text-gray-400 mb-4">${cardData.description}</p>
        ${featuresHtml}
        ${expectedDateHtml}
        <div class="mt-4 text-blue-600 dark:text-blue-400 font-semibold flex items-center">
            進入測試 <i class="fas fa-arrow-right ml-2"></i>
        </div>
        <a href="${cardData.path}" class="hidden"></a>
    `;
    
    // Add click handler
    card.addEventListener('click', (e) => {
        if (e.target.tagName === 'A') return;
        
        // Add click animation
        card.style.transform = 'scale(0.98)';
        setTimeout(() => {
            card.style.transform = '';
            window.location.href = cardData.path;
        }, 100);
    });
    
    return card;
}

// Get status configuration
function getStatusConfig(status) {
    return statusConfig[status] || statusConfig.planned;
}

// Render all test cards
function renderTestCards(containerId = 'test-grid', cards = testCards) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    // Clear existing content
    container.innerHTML = '';
    
    // Sort cards by status (ready first, then development, then planned)
    const statusOrder = ['ready', 'development', 'planned'];
    const sortedCards = [...cards].sort((a, b) => {
        return statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status);
    });
    
    // Create and append cards
    sortedCards.forEach(cardData => {
        const card = createTestCard(cardData);
        container.appendChild(card);
        
        // Add entrance animation with stagger effect
        card.style.animationDelay = `${50 * sortedCards.indexOf(cardData)}ms`;
    });
}

// Filter cards by status
function filterTestCards(status) {
    const filteredCards = status === 'all' ? testCards : testCards.filter(card => card.status === status);
    renderTestCards('test-grid', filteredCards);
}

// Search cards by keyword
function searchTestCards(keyword) {
    const lowerKeyword = keyword.toLowerCase();
    const filteredCards = testCards.filter(card => 
        card.title.toLowerCase().includes(lowerKeyword) ||
        card.description.toLowerCase().includes(lowerKeyword) ||
        card.features?.some(f => f.toLowerCase().includes(lowerKeyword))
    );
    renderTestCards('test-grid', filteredCards);
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => renderTestCards());
} else {
    renderTestCards();
}

// Export for use in other scripts
window.TestCards = {
    testCards,
    renderTestCards,
    filterTestCards,
    searchTestCards,
    createTestCard
};