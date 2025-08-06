// ASR Hub Frontend - Main Application

// Initialize the application
function initializeApp() {
    initializeFilters();
    initializeSearch();
    initializeEmptyStateObserver();
}

// Initialize filter buttons
function initializeFilters() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // Update active state
            filterButtons.forEach(b => {
                b.classList.remove('bg-blue-500', 'text-white');
                b.classList.add('text-gray-600');
            });
            btn.classList.remove('text-gray-600');
            btn.classList.add('bg-blue-500', 'text-white');
            
            // Apply filter
            const filter = btn.dataset.filter;
            TestCards.filterTestCards(filter);
            
            // Update URL hash
            window.location.hash = filter === 'all' ? '' : filter;
        });
    });
    
    // Check URL hash on load
    const hash = window.location.hash.slice(1);
    if (hash && ['ready', 'development', 'planned'].includes(hash)) {
        const targetBtn = document.querySelector(`[data-filter="${hash}"]`);
        if (targetBtn) {
            targetBtn.click();
        }
    }
}

// Initialize search functionality
function initializeSearch() {
    const searchInput = document.getElementById('searchInput');
    
    // Create debounced search function
    const debounceSearch = ASRHubCommon.debounce((value) => {
        if (value.trim()) {
            TestCards.searchTestCards(value);
            updateSearchState(true);
        } else {
            TestCards.renderTestCards();
            updateSearchState(false);
        }
    }, 300);
    
    // Attach event listener
    searchInput.addEventListener('input', (e) => {
        debounceSearch(e.target.value);
    });
    
    // Clear search on ESC key
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            searchInput.value = '';
            TestCards.renderTestCards();
            updateSearchState(false);
        }
    });
}

// Update search state
function updateSearchState(isSearching) {
    const filterContainer = document.querySelector('.filter-controls > div');
    if (isSearching) {
        filterContainer.style.opacity = '0.5';
        filterContainer.style.pointerEvents = 'none';
    } else {
        filterContainer.style.opacity = '1';
        filterContainer.style.pointerEvents = 'auto';
    }
}

// Initialize empty state observer
function initializeEmptyStateObserver() {
    const grid = document.getElementById('test-grid');
    
    // Create observer
    const observer = new MutationObserver(() => {
        if (grid.children.length === 0) {
            showEmptyState();
        }
    });
    
    // Start observing
    observer.observe(grid, { childList: true });
}

// Show empty state message
function showEmptyState() {
    const grid = document.getElementById('test-grid');
    grid.innerHTML = `
        <div class="col-span-full text-center py-20">
            <i class="fas fa-search text-6xl text-gray-300 mb-4"></i>
            <h3 class="text-xl font-semibold text-gray-500 mb-2">沒有找到相符的測試</h3>
            <p class="text-gray-400">請嘗試其他搜尋關鍵字或篩選條件</p>
        </div>
    `;
}

// Keyboard shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Focus search on '/' key
        if (e.key === '/' && document.activeElement !== document.getElementById('searchInput')) {
            e.preventDefault();
            document.getElementById('searchInput').focus();
        }
        
        // Navigate filters with number keys
        if (e.key >= '1' && e.key <= '4' && !e.ctrlKey && !e.altKey && !e.metaKey) {
            const filterButtons = document.querySelectorAll('.filter-btn');
            const index = parseInt(e.key) - 1;
            if (filterButtons[index]) {
                filterButtons[index].click();
            }
        }
    });
}

// Add loading indicator
function showLoading() {
    const grid = document.getElementById('test-grid');
    grid.innerHTML = `
        <div class="col-span-full text-center py-20">
            <i class="fas fa-spinner fa-spin text-6xl text-blue-500 mb-4"></i>
            <h3 class="text-xl font-semibold text-gray-600">載入中...</h3>
        </div>
    `;
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        initializeApp();
        initializeKeyboardShortcuts();
    });
} else {
    initializeApp();
    initializeKeyboardShortcuts();
}

// Export for potential external use
window.ASRHubApp = {
    initializeApp,
    showEmptyState,
    showLoading
};