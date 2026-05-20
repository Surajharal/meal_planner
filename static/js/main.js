// Main JavaScript file for Meal Planner

function csrfHeaders() {
    var m = document.querySelector('meta[name="csrf-token"]');
    if (!m || !m.content) return {};
    return { 'X-CSRFToken': m.content };
}

// Utility function to show loading state
function showLoading(element) {
    if (element) {
        element.disabled = true;
        const originalText = element.textContent;
        element.dataset.originalText = originalText;
        element.textContent = 'Loading...';
    }
}

// Utility function to hide loading state
function hideLoading(element) {
    if (element && element.dataset.originalText) {
        element.disabled = false;
        element.textContent = element.dataset.originalText;
        delete element.dataset.originalText;
    }
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(function() { toast.classList.add('show'); }, 100);
    setTimeout(function() {
        toast.classList.remove('show');
        setTimeout(function() { toast.remove(); }, 300);
    }, 3000);
}

function toggleFavorite(recipeId, button) {
    fetch('/toggle_favorite/' + recipeId, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, csrfHeaders())
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.success) {
            if (button.classList.contains('favorite-btn-large')) {
                if (data.is_favorite) {
                    button.classList.add('favorited');
                    button.innerHTML = '⭐ Favorite';
                } else {
                    button.classList.remove('favorited');
                    button.innerHTML = '⭐ Add to Favorites';
                }
            } else {
                if (data.is_favorite) {
                    button.classList.add('favorited');
                    const card = button.closest('.recipe-card-small');
                    if (card) card.classList.add('favorite-recipe');
                } else {
                    button.classList.remove('favorited');
                    const card = button.closest('.recipe-card-small');
                    if (card) card.classList.remove('favorite-recipe');
                }
                button.title = data.is_favorite ? 'Remove from favorites' : 'Add to favorites';
            }
            showToast(data.message, 'success');
        } else {
            showToast(data.message || 'Error updating favorite', 'error');
        }
    })
    .catch(function(error) {
        console.error('Error:', error);
        showToast('An error occurred', 'error');
    });
}

(function initMobileNav() {
    document.addEventListener('DOMContentLoaded', function() {
        var toggle = document.getElementById('nav-toggle');
        var menu = document.getElementById('nav-menu');
        if (!toggle || !menu) return;
        toggle.addEventListener('click', function() {
            var open = menu.classList.toggle('is-open');
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
            toggle.textContent = open ? '✕' : '☰';
        });
        menu.querySelectorAll('a').forEach(function(link) {
            link.addEventListener('click', function() {
                if (window.innerWidth <= 900) {
                    menu.classList.remove('is-open');
                    toggle.setAttribute('aria-expanded', 'false');
                    toggle.setAttribute('aria-label', 'Open menu');
                    toggle.textContent = '☰';
                }
            });
        });
    });
})();

(function initThemeToggle() {
    var STORAGE_KEY = 'mealplanner-theme';
    function applyIcon() {
        var btn = document.getElementById('theme-toggle-btn');
        if (!btn) return;
        var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        btn.textContent = isDark ? '☀️' : '🌙';
        btn.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
        btn.setAttribute('aria-label', btn.title);
    }
    document.addEventListener('DOMContentLoaded', function() {
        var btn = document.getElementById('theme-toggle-btn');
        applyIcon();
        if (!btn) return;
        btn.addEventListener('click', function() {
            var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            try { localStorage.setItem(STORAGE_KEY, next); } catch (e) { /* ignore */ }
            applyIcon();
        });
    });
})();

// Auto-hide flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(function(message) {
        setTimeout(function() {
            message.style.transition = 'opacity 0.5s';
            message.style.opacity = '0';
            setTimeout(function() {
                message.remove();
            }, 500);
        }, 5000);
    });
});

// Form validation helper
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return false;
    
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(function(field) {
        if (!field.value.trim()) {
            isValid = false;
            field.style.borderColor = '#dc3545';
        } else {
            field.style.borderColor = '#e0e0e0';
        }
    });
    
    return isValid;
}

// API call helper
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || 'An error occurred');
        }
        
        return data;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}
