// ASR Hub Theme Manager - Dark/Light Mode Toggle

class ThemeManager {
    constructor() {
        this.STORAGE_KEY = 'asrhub-theme';
        this.currentTheme = this.loadTheme();
        this.init();
    }

    // Initialize theme system
    init() {
        // Apply saved theme immediately to prevent flash
        this.applyTheme(this.currentTheme);
        
        // Create and inject theme toggle button
        this.createThemeToggle();
        
        // Listen for theme changes from other tabs
        window.addEventListener('storage', (e) => {
            if (e.key === this.STORAGE_KEY) {
                this.currentTheme = e.newValue || 'light';
                this.applyTheme(this.currentTheme);
                this.updateToggleButton();
            }
        });
    }

    // Load theme from localStorage or system preference
    loadTheme() {
        const savedTheme = localStorage.getItem(this.STORAGE_KEY);
        if (savedTheme) {
            return savedTheme;
        }
        
        // Check system preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }
        
        return 'light';
    }

    // Apply theme to document
    applyTheme(theme) {
        const html = document.documentElement;
        
        if (theme === 'dark') {
            html.classList.add('dark');
        } else {
            html.classList.remove('dark');
        }
        
        // Update meta theme-color for mobile browsers
        const metaThemeColor = document.querySelector('meta[name="theme-color"]');
        if (metaThemeColor) {
            metaThemeColor.content = theme === 'dark' ? '#1f2937' : '#ffffff';
        } else {
            const meta = document.createElement('meta');
            meta.name = 'theme-color';
            meta.content = theme === 'dark' ? '#1f2937' : '#ffffff';
            document.head.appendChild(meta);
        }
    }

    // Toggle between themes
    toggleTheme() {
        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.applyTheme(this.currentTheme);
        localStorage.setItem(this.STORAGE_KEY, this.currentTheme);
        this.updateToggleButton();
        
        // Dispatch custom event for other components
        window.dispatchEvent(new CustomEvent('themeChanged', { 
            detail: { theme: this.currentTheme } 
        }));
    }

    // Create floating theme toggle button
    createThemeToggle() {
        // Check if toggle already exists
        if (document.getElementById('theme-toggle')) return;
        
        // Create toggle button container
        const toggleContainer = document.createElement('div');
        toggleContainer.id = 'theme-toggle-container';
        toggleContainer.className = 'fixed top-4 right-4 z-50';
        
        // Create toggle button
        const toggleButton = document.createElement('button');
        toggleButton.id = 'theme-toggle';
        toggleButton.className = `
            p-3 rounded-full bg-white dark:bg-gray-800 
            shadow-lg hover:shadow-xl transition-all duration-300
            text-gray-800 dark:text-gray-200
            hover:scale-110 transform
            border-2 border-gray-200 dark:border-gray-600
        `;
        toggleButton.setAttribute('aria-label', 'Toggle theme');
        toggleButton.setAttribute('title', 'Toggle dark/light mode');
        
        // Set initial icon
        this.updateToggleButton(toggleButton);
        
        // Add click handler
        toggleButton.addEventListener('click', () => this.toggleTheme());
        
        // Add keyboard support
        toggleButton.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.toggleTheme();
            }
        });
        
        toggleContainer.appendChild(toggleButton);
        document.body.appendChild(toggleContainer);
        
        // Add entrance animation
        requestAnimationFrame(() => {
            toggleButton.style.animation = 'slideIn 0.3s ease-out';
        });
    }

    // Update toggle button icon
    updateToggleButton(button = null) {
        const toggleButton = button || document.getElementById('theme-toggle');
        if (!toggleButton) return;
        
        const isDark = this.currentTheme === 'dark';
        
        toggleButton.innerHTML = isDark ? `
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                    d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z">
                </path>
            </svg>
        ` : `
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                    d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z">
                </path>
            </svg>
        `;
        
        // Add rotation animation
        toggleButton.style.transform = 'rotate(360deg)';
        setTimeout(() => {
            toggleButton.style.transform = '';
        }, 300);
    }

    // Get current theme
    getTheme() {
        return this.currentTheme;
    }

    // Set theme programmatically
    setTheme(theme) {
        if (theme === 'light' || theme === 'dark') {
            this.currentTheme = theme;
            this.applyTheme(theme);
            localStorage.setItem(this.STORAGE_KEY, theme);
            this.updateToggleButton();
        }
    }
}

// Initialize theme manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.themeManager = new ThemeManager();
    });
} else {
    window.themeManager = new ThemeManager();
}

// Export for use in other scripts
window.ThemeManager = ThemeManager;