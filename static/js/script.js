// MedPanda - Main JavaScript File

document.addEventListener('DOMContentLoaded', function() {
    console.log('MedPanda script.js loaded successfully');
    
    // Initialize tooltips
    initTooltips();
    
    // Initialize form validation
    initFormValidation();
    
    // Initialize cart functionality
    initCart();
    
    // Initialize responsive navigation
    initResponsiveNav();
    
    // Auto-hide flash messages after 5 seconds
    autoHideFlashMessages();
    
    // Initialize any modals on the page
    initModals();
});

// Tooltip functionality
function initTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    
    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', showTooltip);
        element.addEventListener('mouseleave', hideTooltip);
    });
}

function showTooltip(e) {
    const tooltipText = this.getAttribute('data-tooltip');
    if (!tooltipText) return;
    
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.textContent = tooltipText;
    tooltip.style.position = 'absolute';
    tooltip.style.background = 'rgba(0, 0, 0, 0.8)';
    tooltip.style.color = 'white';
    tooltip.style.padding = '8px 12px';
    tooltip.style.borderRadius = '4px';
    tooltip.style.fontSize = '14px';
    tooltip.style.zIndex = '10000';
    tooltip.style.maxWidth = '200px';
    tooltip.style.wordWrap = 'break-word';
    
    document.body.appendChild(tooltip);
    
    const rect = this.getBoundingClientRect();
    tooltip.style.top = (rect.top - tooltip.offsetHeight - 10) + 'px';
    tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
    
    this._currentTooltip = tooltip;
}

function hideTooltip() {
    if (this._currentTooltip) {
        this._currentTooltip.remove();
        this._currentTooltip = null;
    }
}

// Form validation
function initFormValidation() {
    const forms = document.querySelectorAll('form[data-validate]');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();
            }
        });
    });
}

function validateForm(form) {
    let isValid = true;
    const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            showInputError(input, 'This field is required');
            isValid = false;
        } else {
            clearInputError(input);
        }
    });
    
    return isValid;
}

function showInputError(input, message) {
    clearInputError(input);
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'input-error';
    errorDiv.style.color = '#e53e3e';
    errorDiv.style.fontSize = '14px';
    errorDiv.style.marginTop = '5px';
    errorDiv.textContent = message;
    
    input.parentNode.appendChild(errorDiv);
    input.style.borderColor = '#e53e3e';
}

function clearInputError(input) {
    const existingError = input.parentNode.querySelector('.input-error');
    if (existingError) {
        existingError.remove();
    }
    input.style.borderColor = '';
}

// Cart functionality
function initCart() {
    const cartButtons = document.querySelectorAll('.add-to-cart');
    
    cartButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const productId = this.getAttribute('data-product-id');
            addToCart(productId);
        });
    });
}

function addToCart(productId) {
    // This would typically make an AJAX call to your backend
    console.log('Adding product to cart:', productId);
    
    // Show temporary feedback
    const button = document.querySelector(`[data-product-id="${productId}"]`);
    const originalText = button.innerHTML;
    
    button.innerHTML = '<i class="fas fa-check"></i> Added!';
    button.style.background = '#48bb78';
    
    setTimeout(() => {
        button.innerHTML = originalText;
        button.style.background = '';
    }, 2000);
}

// Responsive navigation
function initResponsiveNav() {
    const mobileMenuButton = document.createElement('button');
    mobileMenuButton.innerHTML = '<i class="fas fa-bars"></i>';
    mobileMenuButton.className = 'mobile-menu-button';
    mobileMenuButton.style.display = 'none';
    mobileMenuButton.style.background = 'none';
    mobileMenuButton.style.border = 'none';
    mobileMenuButton.style.fontSize = '1.5rem';
    mobileMenuButton.style.cursor = 'pointer';
    mobileMenuButton.style.color = '#4a5568';
    
    const nav = document.querySelector('nav');
    nav.appendChild(mobileMenuButton);
    
    const navLinks = document.querySelector('.nav-links');
    const navAuth = document.querySelector('.nav-auth');
    
    mobileMenuButton.addEventListener('click', function() {
        const isVisible = navLinks.style.display === 'flex';
        navLinks.style.display = isVisible ? 'none' : 'flex';
        navAuth.style.display = isVisible ? 'none' : 'flex';
    });
    
    // Check screen size and adjust accordingly
    function checkScreenSize() {
        if (window.innerWidth <= 768) {
            mobileMenuButton.style.display = 'block';
            navLinks.style.display = 'none';
            navAuth.style.display = 'none';
        } else {
            mobileMenuButton.style.display = 'none';
            navLinks.style.display = 'flex';
            navAuth.style.display = 'flex';
        }
    }
    
    checkScreenSize();
    window.addEventListener('resize', checkScreenSize);
}

// Flash messages
function autoHideFlashMessages() {
    const flashMessages = document.querySelectorAll('.alert');
    
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            message.style.transition = 'opacity 0.5s ease';
            
            setTimeout(() => {
                message.remove();
            }, 500);
        }, 5000);
    });
}

// Modal functionality - SAFE version that won't conflict with your existing modals
function initModals() {
    console.log('Initializing modals...');
    
    // Only initialize modals that don't already have handlers
    const modals = document.querySelectorAll('.modal:not([data-initialized])');
    
    modals.forEach(modal => {
        modal.setAttribute('data-initialized', 'true');
        
        // Close buttons
        const closeButtons = modal.querySelectorAll('.close, [data-dismiss="modal"]');
        closeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                modal.style.display = 'none';
            });
        });
        
        // Close when clicking outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
        
        // Close with Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.style.display === 'block') {
                modal.style.display = 'none';
            }
        });
    });
}

// Safe modal open/close functions that won't override existing ones
window.safeOpenModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'block';
    }
};

window.safeCloseModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
};

// Utility function to show loading state
window.showLoading = function(button) {
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    button.disabled = true;
    return originalText;
};

window.hideLoading = function(button, originalText) {
    button.innerHTML = originalText;
    button.disabled = false;
};

// AJAX helper function
window.ajaxRequest = function(url, options = {}) {
    const { method = 'GET', data = null, onSuccess = null, onError = null } = options;
    
    const xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.setRequestHeader('Content-Type', 'application/json');
    
    xhr.onload = function() {
        if (xhr.status >= 200 && xhr.status < 300) {
            try {
                const response = JSON.parse(xhr.responseText);
                onSuccess && onSuccess(response);
            } catch (e) {
                onSuccess && onSuccess(xhr.responseText);
            }
        } else {
            onError && onError(xhr.status, xhr.statusText);
        }
    };
    
    xhr.onerror = function() {
        onError && onError(0, 'Network error');
    };
    
    xhr.send(data ? JSON.stringify(data) : null);
};

// Quantity controls for cart items
function initQuantityControls() {
    const quantityContainers = document.querySelectorAll('.quantity-control');
    
    quantityContainers.forEach(container => {
        const minusBtn = container.querySelector('.quantity-minus');
        const plusBtn = container.querySelector('.quantity-plus');
        const input = container.querySelector('.quantity-input');
        
        if (minusBtn && plusBtn && input) {
            minusBtn.addEventListener('click', () => {
                const currentValue = parseInt(input.value) || 0;
                if (currentValue > 1) {
                    input.value = currentValue - 1;
                    input.dispatchEvent(new Event('change'));
                }
            });
            
            plusBtn.addEventListener('click', () => {
                const currentValue = parseInt(input.value) || 0;
                input.value = currentValue + 1;
                input.dispatchEvent(new Event('change'));
            });
        }
    });
}

// Initialize when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initQuantityControls);
} else {
    initQuantityControls();
}