/**
 * Smart Career Navigator - Main JavaScript
 * ==========================================
 * Client-side utilities and interactive features.
 */

// ── Password Toggle ──
// Called from login.html and register.html
function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    const icon = input.parentElement.querySelector('i');

    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.remove('bi-eye');
        icon.classList.add('bi-eye-slash');
    } else {
        input.type = 'password';
        icon.classList.remove('bi-eye-slash');
        icon.classList.add('bi-eye');
    }
}


// ── Auto-dismiss alerts after 5 seconds ──
document.addEventListener('DOMContentLoaded', function () {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 5000);
    });
});


// ── Confirm delete actions ──
document.addEventListener('DOMContentLoaded', function () {
    const deleteForms = document.querySelectorAll('form[data-confirm]');
    deleteForms.forEach(function (form) {
        form.addEventListener('submit', function (e) {
            if (!confirm(form.dataset.confirm || 'Are you sure?')) {
                e.preventDefault();
            }
        });
    });
});


// ── Smooth scroll for anchor links ──
document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});


// ── Skill tag input helper ──
// Auto-formats comma-separated skills in textareas
document.addEventListener('DOMContentLoaded', function () {
    const skillInputs = document.querySelectorAll('#technical_skills, #soft_skills');
    skillInputs.forEach(function (input) {
        input.addEventListener('blur', function () {
            // Clean up extra spaces and formatting
            let skills = this.value.split(',')
                .map(s => s.trim())
                .filter(s => s.length > 0);
            this.value = skills.join(', ');
        });
    });
});
