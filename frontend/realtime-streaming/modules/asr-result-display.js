/**
 * ASR Result Display Manager
 * 管理 ASR 轉錄結果的顯示和歷史記錄
 */

class ASRResultDisplayManager {
    constructor() {
        // 狀態管理
        this.isActive = false;
        this.results = [];
        this.maxResults = 50;
        
        // UI 元素引用
        this.resultsContainer = null;
        this.clearResultsBtn = null;
        
        // 結果計數
        this.totalResultsReceived = 0;
        this.sessionResultsCount = 0;
        
        // 顯示配置
        this.showTimestamps = true;
        this.showConfidence = true;
        this.autoScroll = true;
        this.highlightNewResults = true;
        
        // 回調函數
        this.onNewResult = null;        // 新結果回調
        this.onResultsClear = null;     // 清空結果回調
        this.onResultClick = null;      // 結果點擊回調
        
        // 動畫配置
        this.newResultTimeout = 3000; // 新結果高亮持續時間
        
        // 搜尋和過濾
        this.searchTerm = '';
        this.confidenceFilter = 0.0;
    }
    
    /**
     * 初始化 ASR 結果顯示管理器
     */
    initialize() {
        console.log('ASRResultDisplayManager: 初始化 ASR 結果顯示管理器...');
        
        try {
            // 獲取 UI 元素
            this.resultsContainer = document.getElementById('asrResults');
            this.clearResultsBtn = document.getElementById('clearResults');
            
            // 設置事件監聽器
            this.setupEventListeners();
            
            // 初始化 UI 狀態
            this.updateUI();
            
            console.log('✓ ASRResultDisplayManager: ASR 結果顯示管理器初始化完成');
            
        } catch (error) {
            console.error('ASRResultDisplayManager: 初始化失敗', error);
        }
    }
    
    /**
     * 設置事件監聽器
     */
    setupEventListeners() {
        // 清空結果按鈕
        if (this.clearResultsBtn) {
            this.clearResultsBtn.addEventListener('click', () => {
                this.clearResults();
            });
        }
        
        // 結果容器滾動事件
        if (this.resultsContainer) {
            this.resultsContainer.addEventListener('scroll', () => {
                this.handleScroll();
            });
        }
    }
    
    /**
     * 處理滾動事件
     */
    handleScroll() {
        if (!this.resultsContainer) return;
        
        const { scrollTop, scrollHeight, clientHeight } = this.resultsContainer;
        const isAtBottom = scrollTop + clientHeight >= scrollHeight - 10;
        
        // 如果用戶滾動到底部，啟用自動滾動
        this.autoScroll = isAtBottom;
    }
    
    /**
     * 添加新的 ASR 結果
     */
    addResult(resultData) {
        try {
            const {
                transcript,
                confidence = 1.0,
                session_id = null,
                timestamp = Date.now(),
                language = 'zh-TW',
                provider = 'unknown',
                duration = null,
                is_final = true
            } = resultData;
            
            // 創建結果對象
            const result = {
                id: this.generateResultId(),
                transcript: transcript.trim(),
                confidence: confidence,
                session_id: session_id,
                timestamp: timestamp,
                language: language,
                provider: provider,
                duration: duration,
                is_final: is_final,
                created_at: Date.now()
            };
            
            // 檢查是否為空結果
            if (!result.transcript) {
                console.log('ASRResultDisplayManager: 忽略空轉錄結果');
                return;
            }
            
            // 添加到結果列表
            this.results.unshift(result);
            this.totalResultsReceived++;
            this.sessionResultsCount++;
            
            // 限制結果數量
            if (this.results.length > this.maxResults) {
                this.results = this.results.slice(0, this.maxResults);
            }
            
            console.log(`✓ ASRResultDisplayManager: 新增轉錄結果 - "${result.transcript}" (信心度: ${(confidence * 100).toFixed(1)}%)`);
            
            // 更新 UI 顯示
            this.updateResultsDisplay();
            
            // 觸發新結果回調
            if (this.onNewResult) {
                this.onNewResult(result);
            }
            
            return result;
            
        } catch (error) {
            console.error('ASRResultDisplayManager: 添加結果失敗', error);
        }
    }
    
    /**
     * 更新結果顯示
     */
    updateResultsDisplay() {
        if (!this.resultsContainer) return;
        
        try {
            // 清空容器
            this.resultsContainer.innerHTML = '';
            
            // 如果沒有結果，顯示空狀態
            if (this.results.length === 0) {
                this.showEmptyState();
                return;
            }
            
            // 過濾結果
            const filteredResults = this.filterResults();
            
            // 渲染結果
            filteredResults.forEach((result, index) => {
                const resultElement = this.createResultElement(result, index === 0);
                this.resultsContainer.appendChild(resultElement);
            });
            
            // 自動滾動到底部
            if (this.autoScroll) {
                this.scrollToBottom();
            }
            
        } catch (error) {
            console.error('ASRResultDisplayManager: 更新結果顯示失敗', error);
        }
    }
    
    /**
     * 創建結果元素
     */
    createResultElement(result, isNewest = false) {
        const element = document.createElement('div');
        element.className = `asr-result-item p-4 mb-3 bg-gray-50 dark:bg-gray-700 rounded-lg transition-all duration-300 ${isNewest && this.highlightNewResults ? 'new' : ''}`;
        element.dataset.resultId = result.id;
        
        // 時間戳格式化
        const timeStr = new Date(result.timestamp).toLocaleTimeString('zh-TW', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        
        // 信心度顏色
        const confidenceClass = this.getConfidenceClass(result.confidence);
        
        // 構建 HTML
        element.innerHTML = `
            <div class="flex items-start justify-between mb-2">
                <div class="flex items-center space-x-2">
                    ${this.showTimestamps ? `<span class="text-xs text-gray-500 dark:text-gray-400">${timeStr}</span>` : ''}
                    ${this.showConfidence ? `<span class="text-xs px-2 py-1 rounded-full ${confidenceClass}">${(result.confidence * 100).toFixed(0)}%</span>` : ''}
                    <span class="text-xs text-gray-400 dark:text-gray-500">${result.provider}</span>
                </div>
                <button class="text-gray-400 hover:text-red-500 transition-colors" onclick="asrResultDisplay.removeResult('${result.id}')">
                    <i class="fas fa-times text-xs"></i>
                </button>
            </div>
            
            <div class="text-gray-800 dark:text-gray-200 leading-relaxed">
                ${this.highlightSearchTerm(result.transcript)}
            </div>
            
            ${result.duration ? `<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">錄音時長: ${result.duration.toFixed(1)}秒</div>` : ''}
        `;
        
        // 添加點擊事件
        element.addEventListener('click', () => {
            if (this.onResultClick) {
                this.onResultClick(result);
            }
        });
        
        // 移除新結果高亮
        if (isNewest && this.highlightNewResults) {
            setTimeout(() => {
                element.classList.remove('new');
            }, this.newResultTimeout);
        }
        
        return element;
    }
    
    /**
     * 獲取信心度樣式類別
     */
    getConfidenceClass(confidence) {
        if (confidence >= 0.8) {
            return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
        } else if (confidence >= 0.6) {
            return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
        } else {
            return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
        }
    }
    
    /**
     * 高亮搜尋關鍵字
     */
    highlightSearchTerm(text) {
        if (!this.searchTerm) {
            return text;
        }
        
        const regex = new RegExp(`(${this.escapeRegExp(this.searchTerm)})`, 'gi');
        return text.replace(regex, '<mark class="bg-yellow-200 dark:bg-yellow-800">$1</mark>');
    }
    
    /**
     * 轉義正則表達式特殊字符
     */
    escapeRegExp(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
    
    /**
     * 過濾結果
     */
    filterResults() {
        let filtered = this.results;
        
        // 信心度過濾
        if (this.confidenceFilter > 0) {
            filtered = filtered.filter(result => result.confidence >= this.confidenceFilter);
        }
        
        // 搜尋過濾
        if (this.searchTerm) {
            const searchLower = this.searchTerm.toLowerCase();
            filtered = filtered.filter(result => 
                result.transcript.toLowerCase().includes(searchLower)
            );
        }
        
        return filtered;
    }
    
    /**
     * 顯示空狀態
     */
    showEmptyState() {
        if (!this.resultsContainer) return;
        
        this.resultsContainer.innerHTML = `
            <div class="text-center text-gray-500 dark:text-gray-400 py-8">
                <i class="fas fa-microphone-slash text-4xl mb-2"></i>
                <p>開始說話以查看轉錄結果</p>
                ${this.totalResultsReceived > 0 ? '<p class="text-sm mt-1">或調整過濾條件</p>' : ''}
            </div>
        `;
    }
    
    /**
     * 滾動到底部
     */
    scrollToBottom() {
        if (this.resultsContainer) {
            this.resultsContainer.scrollTop = this.resultsContainer.scrollHeight;
        }
    }
    
    /**
     * 移除特定結果
     */
    removeResult(resultId) {
        try {
            const index = this.results.findIndex(result => result.id === resultId);
            if (index !== -1) {
                const removedResult = this.results.splice(index, 1)[0];
                console.log(`ASRResultDisplayManager: 移除結果 - "${removedResult.transcript}"`);
                
                // 更新顯示
                this.updateResultsDisplay();
                
                return removedResult;
            }
        } catch (error) {
            console.error('ASRResultDisplayManager: 移除結果失敗', error);
        }
    }
    
    /**
     * 清空所有結果
     */
    clearResults() {
        try {
            const resultCount = this.results.length;
            this.results = [];
            this.sessionResultsCount = 0;
            
            console.log(`ASRResultDisplayManager: 已清空 ${resultCount} 個結果`);
            
            // 更新顯示
            this.updateResultsDisplay();
            
            // 觸發清空回調
            if (this.onResultsClear) {
                this.onResultsClear({
                    clearedCount: resultCount,
                    timestamp: Date.now()
                });
            }
            
        } catch (error) {
            console.error('ASRResultDisplayManager: 清空結果失敗', error);
        }
    }
    
    /**
     * 設置搜尋關鍵字
     */
    setSearchTerm(searchTerm) {
        this.searchTerm = searchTerm;
        this.updateResultsDisplay();
    }
    
    /**
     * 設置信心度過濾
     */
    setConfidenceFilter(minConfidence) {
        this.confidenceFilter = minConfidence;
        this.updateResultsDisplay();
    }
    
    /**
     * 導出結果為文本
     */
    exportResults(format = 'text') {
        try {
            const filteredResults = this.filterResults();
            
            if (format === 'text') {
                return filteredResults.map(result => {
                    const timeStr = new Date(result.timestamp).toLocaleString('zh-TW');
                    const confidenceStr = (result.confidence * 100).toFixed(1);
                    return `[${timeStr}] (${confidenceStr}%) ${result.transcript}`;
                }).join('\n');
                
            } else if (format === 'json') {
                return JSON.stringify(filteredResults, null, 2);
                
            } else if (format === 'csv') {
                const headers = 'Timestamp,Transcript,Confidence,Provider,Duration\n';
                const rows = filteredResults.map(result => {
                    const timeStr = new Date(result.timestamp).toISOString();
                    const transcript = `"${result.transcript.replace(/"/g, '""')}"`;
                    return `${timeStr},${transcript},${result.confidence},${result.provider},${result.duration || ''}`;
                }).join('\n');
                return headers + rows;
            }
            
        } catch (error) {
            console.error('ASRResultDisplayManager: 導出結果失敗', error);
            return '';
        }
    }
    
    /**
     * 生成結果 ID
     */
    generateResultId() {
        return `result_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }
    
    /**
     * 更新 UI 狀態
     */
    updateUI() {
        this.updateResultsDisplay();
    }
    
    /**
     * 設置回調函數
     */
    setCallbacks({
        onNewResult = null,
        onResultsClear = null,
        onResultClick = null
    } = {}) {
        this.onNewResult = onNewResult;
        this.onResultsClear = onResultsClear;
        this.onResultClick = onResultClick;
    }
    
    /**
     * 更新配置
     */
    updateConfig({
        showTimestamps = null,
        showConfidence = null,
        autoScroll = null,
        highlightNewResults = null,
        maxResults = null
    } = {}) {
        let needsUpdate = false;
        
        if (showTimestamps !== null) {
            this.showTimestamps = showTimestamps;
            needsUpdate = true;
        }
        
        if (showConfidence !== null) {
            this.showConfidence = showConfidence;
            needsUpdate = true;
        }
        
        if (autoScroll !== null) {
            this.autoScroll = autoScroll;
        }
        
        if (highlightNewResults !== null) {
            this.highlightNewResults = highlightNewResults;
        }
        
        if (maxResults !== null) {
            this.maxResults = maxResults;
            if (this.results.length > maxResults) {
                this.results = this.results.slice(0, maxResults);
                needsUpdate = true;
            }
        }
        
        if (needsUpdate) {
            this.updateResultsDisplay();
        }
    }
    
    /**
     * 獲取統計資訊
     */
    getStatistics() {
        const filteredResults = this.filterResults();
        
        if (filteredResults.length === 0) {
            return {
                totalResults: this.results.length,
                filteredResults: 0,
                averageConfidence: 0,
                totalDuration: 0,
                providers: {},
                languages: {}
            };
        }
        
        const stats = {
            totalResults: this.results.length,
            filteredResults: filteredResults.length,
            sessionResults: this.sessionResultsCount,
            totalReceived: this.totalResultsReceived
        };
        
        // 計算平均信心度
        stats.averageConfidence = filteredResults.reduce((sum, result) => 
            sum + result.confidence, 0) / filteredResults.length;
        
        // 計算總時長
        stats.totalDuration = filteredResults.reduce((sum, result) => 
            sum + (result.duration || 0), 0);
        
        // 統計提供者
        stats.providers = {};
        filteredResults.forEach(result => {
            stats.providers[result.provider] = (stats.providers[result.provider] || 0) + 1;
        });
        
        // 統計語言
        stats.languages = {};
        filteredResults.forEach(result => {
            stats.languages[result.language] = (stats.languages[result.language] || 0) + 1;
        });
        
        return stats;
    }
    
    /**
     * 獲取所有結果
     */
    getAllResults() {
        return [...this.results];
    }
    
    /**
     * 清理資源
     */
    cleanup() {
        console.log('ASRResultDisplayManager: 清理資源...');
        
        // 移除事件監聽器
        if (this.clearResultsBtn) {
            this.clearResultsBtn.removeEventListener('click', this.clearResults);
        }
        
        if (this.resultsContainer) {
            this.resultsContainer.removeEventListener('scroll', this.handleScroll);
        }
        
        // 清空結果
        this.results = [];
        this.sessionResultsCount = 0;
        
        console.log('✓ ASRResultDisplayManager: 資源清理完成');
    }
}

// 導出到全域
window.ASRResultDisplayManager = ASRResultDisplayManager;