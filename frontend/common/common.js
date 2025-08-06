// ASR Hub Common JavaScript Functions

// Make entire card clickable
function initializeClickableCards() {
    const testCards = document.querySelectorAll('.test-card');
    
    testCards.forEach(card => {
        // Find the link within the card
        const link = card.querySelector('a');
        if (!link) return;
        
        // Make the entire card clickable
        card.style.cursor = 'pointer';
        
        card.addEventListener('click', (e) => {
            // Prevent clicking the link from triggering the card click
            if (e.target.tagName === 'A') return;
            
            // Navigate to the link's href
            window.location.href = link.href;
        });
        
        // Add hover effect
        card.addEventListener('mouseenter', () => {
            card.style.transform = 'translateY(-4px)';
            card.style.boxShadow = '0 6px 12px rgba(0,0,0,0.15)';
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.transform = 'translateY(-2px)';
            card.style.boxShadow = '0 4px 8px rgba(0,0,0,0.15)';
        });
    });
}

// Add log entry with type
function addLogEntry(logContainer, message, type = 'info') {
    const entry = document.createElement('div');
    const timestamp = new Date().toLocaleTimeString('zh-TW');
    
    // Set color based on type
    const colorClasses = {
        info: 'text-blue-400',
        success: 'text-green-400',
        warning: 'text-yellow-400',
        error: 'text-red-400'
    };
    
    entry.className = `mb-1 ${colorClasses[type] || colorClasses.info}`;
    entry.textContent = `[${timestamp}] ${message}`;
    logContainer.appendChild(entry);
    logContainer.scrollTop = logContainer.scrollHeight;
}

// Update status text with animation - IMPROVED VERSION
function updateStatus(statusElement, text, statusClass = '') {
    statusElement.textContent = text;
    
    // Remove all color-related classes but keep structural classes
    const baseClasses = ['text-lg', 'mb-2'];
    
    // Define color classes for each status
    const statusColors = {
        uploading: ['text-orange-600', 'dark:text-orange-400'],
        processing: ['text-blue-600', 'dark:text-blue-400'],
        complete: ['text-green-600', 'dark:text-green-400'],
        error: ['text-red-600', 'dark:text-red-400'],
        recording: ['text-red-600', 'dark:text-red-400'],
        connecting: ['text-gray-500', 'dark:text-gray-400'],
        ready: ['text-gray-600', 'dark:text-gray-400']
    };
    
    // Get the color classes for this status, or use default
    const colorClasses = statusColors[statusClass] || ['text-gray-600', 'dark:text-gray-400'];
    
    // Combine all classes
    const allClasses = [...baseClasses, ...colorClasses];
    
    // Apply all classes at once
    statusElement.className = allClasses.join(' ');
    
    // Add fade effect
    statusElement.style.opacity = '0';
    setTimeout(() => {
        statusElement.style.transition = 'opacity 0.3s ease';
        statusElement.style.opacity = '1';
    }, 10);
}

// Alternative approach: Use data attributes for status
function updateStatusWithData(statusElement, text, statusClass = '') {
    statusElement.textContent = text;
    
    // Store the status in a data attribute
    statusElement.dataset.status = statusClass || 'ready';
    
    // Ensure the element has the status-dynamic class without removing other classes
    if (!statusElement.classList.contains('status-dynamic')) {
        statusElement.classList.add('status-dynamic');
    }
    
    // Add fade effect
    statusElement.style.opacity = '0';
    setTimeout(() => {
        statusElement.style.transition = 'opacity 0.3s ease';
        statusElement.style.opacity = '1';
    }, 10);
}

// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Format duration
function formatDuration(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

// Show notification
function showNotification(message, type = 'info', duration = 3000) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Add styles
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        border-radius: 6px;
        background: white;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 1000;
        transform: translateX(400px);
        transition: transform 0.3s ease;
    `;
    
    // Type-specific colors
    const colors = {
        info: '#3498db',
        success: '#27ae60',
        warning: '#f39c12',
        error: '#e74c3c'
    };
    
    notification.style.borderLeft = `4px solid ${colors[type] || colors.info}`;
    
    // Dark mode support for notifications
    if (document.documentElement.classList.contains('dark')) {
        notification.style.background = '#374151';
        notification.style.color = '#f3f4f6';
    }
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 10);
    
    // Auto remove
    setTimeout(() => {
        notification.style.transform = 'translateX(400px)';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, duration);
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Copy to clipboard
function copyToClipboard(text, successMessage = '已複製到剪貼簿') {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showNotification(successMessage, 'success');
        }).catch(() => {
            fallbackCopyToClipboard(text, successMessage);
        });
    } else {
        fallbackCopyToClipboard(text, successMessage);
    }
}

function fallbackCopyToClipboard(text, successMessage) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
        document.execCommand('copy');
        showNotification(successMessage, 'success');
    } catch (err) {
        showNotification('複製失敗', 'error');
    }
    
    document.body.removeChild(textArea);
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeClickableCards);
} else {
    initializeClickableCards();
}

// Export functions for use in other scripts
window.ASRHubCommon = {
    addLogEntry,
    updateStatus,
    updateStatusWithData,
    formatFileSize,
    formatDuration,
    showNotification,
    debounce,
    copyToClipboard
};