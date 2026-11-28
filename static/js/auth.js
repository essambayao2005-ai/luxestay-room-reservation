/**
 * Auth pages (Login & Register) plain JavaScript:
 * - Background image preload with 1.5 s fallback before starting intro
 * - Session-once intro animation with skip on keydown/click & reduced-motion support
 * - Password show/hide toggle
 * - Submit button loading spinner (prevents double submission)
 */

(function () {
  const SESSION_KEY = 'msu_auth_intro_done';
  const PRELOAD_TIMEOUT_MS = 1500;
  const root = document.documentElement;

  function focusFirstInput() {
    const first = document.querySelector('.auth-card input:not([type="hidden"]):not([disabled])');
    if (first) {
      first.focus({ preventScroll: true });
    }
  }

  function finishIntro(skipImmediate) {
    try {
      sessionStorage.setItem(SESSION_KEY, '1');
    } catch (e) {
      // Ignore storage errors in private mode
    }
    root.classList.remove('auth-intro-pending', 'auth-intro-running');
    if (skipImmediate) {
      root.classList.add('auth-intro-quick');
    }
    document.querySelectorAll('.auth-brand, .auth-card').forEach((el) => {
      el.style.willChange = 'auto';
    });
    focusFirstInput();
  }

  function startIntro() {
    const brand = document.querySelector('.auth-brand');
    if (brand) {
      const rect = brand.getBoundingClientRect();
      const brandCenter = rect.top + rect.height / 2;
      const viewportCenter = window.innerHeight / 2;
      const shift = Math.round(viewportCenter - brandCenter);
      root.style.setProperty('--brand-shift', `${shift}px`);
    }

    root.classList.remove('auth-intro-pending');
    root.classList.add('auth-intro-running');

    // Total intro duration: fade (0.6s) + hold (0.6s) + move (0.8s) - 0.2s + card (0.7s) = ~2.5s
    const totalMs = 2550;
    const endTimer = setTimeout(() => finishIntro(false), totalMs);

    function skipOnInteract() {
      clearTimeout(endTimer);
      document.removeEventListener('keydown', skipOnInteract);
      document.removeEventListener('pointerdown', skipOnInteract);
      finishIntro(false);
    }

    document.addEventListener('keydown', skipOnInteract, { once: true });
    document.addEventListener('pointerdown', skipOnInteract, { once: true });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const skipIntroAttr = root.getAttribute('data-skip-intro') === '1';
    let alreadyPlayed = false;
    try {
      alreadyPlayed = sessionStorage.getItem(SESSION_KEY) === '1';
    } catch (e) {
      alreadyPlayed = false;
    }

    if (prefersReduced || skipIntroAttr || alreadyPlayed) {
      root.classList.remove('auth-intro-pending');
      if (!prefersReduced) {
        root.classList.add('auth-intro-quick');
      }
      focusFirstInput();
    } else {
      const bgUrl = root.getAttribute('data-auth-bg');
      if (!bgUrl) {
        startIntro();
      } else {
        let started = false;
        const trigger = () => {
          if (started) return;
          started = true;
          startIntro();
        };
        const img = new Image();
        img.onload = trigger;
        img.onerror = trigger;
        img.src = bgUrl;
        setTimeout(trigger, PRELOAD_TIMEOUT_MS);
      }
    }

    // Submit loading state: disable button & show spinner
    const authForm = document.querySelector('.auth-card form');
    if (authForm) {
      authForm.addEventListener('submit', () => {
        const submitBtn = authForm.querySelector('button[type="submit"]');
        if (submitBtn && !submitBtn.disabled) {
          submitBtn.disabled = true;
          submitBtn.innerHTML =
            '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Please wait...';
        }
      });
    }
  });
})();

/**
 * Toggle password visibility (used by inline onclick handlers).
 */
function togglePassword(fieldId, btn) {
  const field = document.getElementById(fieldId);
  const icon = btn ? btn.querySelector('i') : null;
  if (!field) return;
  if (field.type === 'password') {
    field.type = 'text';
    if (icon) icon.className = 'bi bi-eye-slash';
    if (btn) btn.setAttribute('aria-label', 'Hide password');
  } else {
    field.type = 'password';
    if (icon) icon.className = 'bi bi-eye';
    if (btn) btn.setAttribute('aria-label', 'Show password');
  }
}
