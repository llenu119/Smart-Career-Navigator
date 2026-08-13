/**
 * Smart Career Navigator - Password Strength & Live Validation
 * ==============================================================
 * Attaches a live strength meter + requirement checklist under any
 * <input id="password"> on a page that also contains
 * data-password-strength="true" on the <form>.
 *
 * Rules mirror the server-side check in routes/auth.py::is_strong_password
 *   - at least 8 characters
 *   - at least 1 uppercase letter
 *   - at least 1 lowercase letter
 *   - at least 1 number
 *   - at least 1 special character
 *
 * The submit button is disabled until the password satisfies all rules
 * AND (if a confirm field is present) the confirmation matches.
 */

(function () {
    const RULES = [
        { key: 'length', label: 'At least 8 characters', test: (v) => v.length >= 8 },
        { key: 'upper', label: 'One uppercase letter (A-Z)', test: (v) => /[A-Z]/.test(v) },
        { key: 'lower', label: 'One lowercase letter (a-z)', test: (v) => /[a-z]/.test(v) },
        { key: 'number', label: 'One number (0-9)', test: (v) => /\d/.test(v) },
        { key: 'special', label: 'One special character (!@#$%^&* etc.)', test: (v) => /[!@#$%^&*(),.?":{}|<>]/.test(v) },
    ];

    function evaluate(password) {
        const results = RULES.map(rule => ({ ...rule, passed: rule.test(password) }));
        const score = results.filter(r => r.passed).length;
        return { results, score };
    }

    function scoreMeta(score, hasContent) {
        if (!hasContent) return { label: '', pct: 0, css: 'bg-secondary' };
        if (score <= 2) return { label: 'Weak', pct: 25, css: 'bg-danger' };
        if (score === 3) return { label: 'Fair', pct: 50, css: 'bg-warning' };
        if (score === 4) return { label: 'Good', pct: 75, css: 'bg-info' };
        return { label: 'Strong', pct: 100, css: 'bg-success' };
    }

    function buildMeterUI(passwordField) {
        const wrapper = document.createElement('div');
        wrapper.className = 'password-strength-wrapper mt-2';
        wrapper.innerHTML = `
            <div class="progress" style="height:6px;">
                <div class="progress-bar password-strength-bar" role="progressbar" style="width:0%"></div>
            </div>
            <div class="d-flex justify-content-between align-items-center mt-1">
                <small class="password-strength-label text-muted">Password strength</small>
                <small class="password-strength-text fw-600"></small>
            </div>
            <ul class="password-rule-list list-unstyled small mt-2 mb-0"></ul>
        `;

        const ruleList = wrapper.querySelector('.password-rule-list');
        RULES.forEach(rule => {
            const li = document.createElement('li');
            li.dataset.ruleKey = rule.key;
            li.className = 'password-rule text-muted mb-1';
            li.innerHTML = `<i class="bi bi-circle me-2"></i><span>${rule.label}</span>`;
            ruleList.appendChild(li);
        });

        // Insert right after the password field's closest wrapper
        // (input-group if present, otherwise the input itself).
        const anchor = passwordField.closest('.input-group') || passwordField;
        anchor.insertAdjacentElement('afterend', wrapper);
        return wrapper;
    }

    function updateMeterUI(wrapper, password) {
        const { results, score } = evaluate(password);
        const meta = scoreMeta(score, password.length > 0);
        const bar = wrapper.querySelector('.password-strength-bar');
        const text = wrapper.querySelector('.password-strength-text');

        bar.style.width = meta.pct + '%';
        bar.className = 'progress-bar password-strength-bar ' + meta.css;
        text.textContent = meta.label;
        text.className = 'password-strength-text fw-600 ' + (password.length ? meta.css.replace('bg-', 'text-') : '');

        results.forEach(rule => {
            const li = wrapper.querySelector(`li[data-rule-key="${rule.key}"]`);
            if (!li) return;
            const icon = li.querySelector('i');
            if (rule.passed) {
                li.classList.remove('text-muted');
                li.classList.add('text-success');
                icon.className = 'bi bi-check-circle-fill me-2';
            } else {
                li.classList.remove('text-success');
                li.classList.add('text-muted');
                icon.className = 'bi bi-circle me-2';
            }
        });

        return results.every(r => r.passed);
    }

    function setFieldValidity(field, isValid, message) {
        if (!field) return;
        if (field.value.length === 0) {
            field.classList.remove('is-valid', 'is-invalid');
            return;
        }
        field.classList.toggle('is-valid', isValid);
        field.classList.toggle('is-invalid', !isValid);
        field.setCustomValidity(isValid ? '' : message);
    }

    function initForm(form) {
        const passwordField = form.querySelector('#password');
        if (!passwordField) return;
        const confirmField = form.querySelector('#confirm_password');
        const submitBtn = form.querySelector('button[type="submit"]');

        const meterWrapper = buildMeterUI(passwordField);

        // Confirm-password live feedback message
        let confirmHint = null;
        if (confirmField) {
            confirmHint = document.createElement('div');
            confirmHint.className = 'confirm-password-hint small mt-1';
            confirmField.closest('.mb-3, .input-group')?.insertAdjacentElement('afterend', confirmHint)
                || confirmField.insertAdjacentElement('afterend', confirmHint);
        }

        function revalidate() {
            const password = passwordField.value;
            const strongEnough = updateMeterUI(meterWrapper, password);
            setFieldValidity(passwordField, strongEnough, 'Password does not meet the requirements below.');

            let confirmOk = true;
            if (confirmField) {
                const confirmVal = confirmField.value;
                confirmOk = confirmVal.length > 0 && confirmVal === password;
                setFieldValidity(confirmField, confirmOk, 'Passwords do not match.');
                if (confirmHint) {
                    if (confirmVal.length === 0) {
                        confirmHint.textContent = '';
                    } else if (confirmOk) {
                        confirmHint.innerHTML = '<i class="bi bi-check-circle-fill me-1 text-success"></i><span class="text-success">Passwords match</span>';
                    } else {
                        confirmHint.innerHTML = '<i class="bi bi-x-circle-fill me-1 text-danger"></i><span class="text-danger">Passwords do not match</span>';
                    }
                }
            }

            const formValid = strongEnough && confirmOk;
            if (submitBtn) {
                submitBtn.disabled = !formValid;
                submitBtn.classList.toggle('disabled', !formValid);
            }
            return formValid;
        }

        passwordField.addEventListener('input', revalidate);
        if (confirmField) confirmField.addEventListener('input', revalidate);

        // Start with the submit button disabled until the user types a valid password.
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.classList.add('disabled');
        }

        // Belt-and-suspenders: block submit if somehow still invalid
        // (e.g. browser autofill without firing 'input').
        form.addEventListener('submit', function (e) {
            if (!revalidate()) {
                e.preventDefault();
                e.stopPropagation();
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('form[data-password-strength="true"]').forEach(initForm);
    });
})();
