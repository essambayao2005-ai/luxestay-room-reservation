/**
 * Campus Scheduler - Core Vanilla JavaScript Utilities
 * Handles sidebar toggling, auto-dismissing alerts, and stat count-up animations.
 * Strictly respects prefers-reduced-motion.
 */

document.addEventListener('DOMContentLoaded', () => {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // -------------------------------------------------------------------------
  // 1. Mobile Sidebar & Offcanvas Toggle
  // -------------------------------------------------------------------------
  const sidebar = document.querySelector('.app-sidebar');
  const backdrop = document.querySelector('.sidebar-backdrop');
  const toggleButtons = document.querySelectorAll('[data-action="toggle-sidebar"], .topbar-menu-toggle');

  function openSidebar() {
    if (sidebar) sidebar.classList.add('show');
    if (backdrop) backdrop.classList.add('show');
  }

  function closeSidebar() {
    if (sidebar) sidebar.classList.remove('show');
    if (backdrop) backdrop.classList.remove('show');
  }

  toggleButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      if (sidebar && sidebar.classList.contains('show')) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });
  });

  if (backdrop) {
    backdrop.addEventListener('click', closeSidebar);
  }

  // Close sidebar on pressing Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sidebar && sidebar.classList.contains('show')) {
      closeSidebar();
    }
  });

  // -------------------------------------------------------------------------
  // 2. Stat Numbers Count-Up Animation
  // -------------------------------------------------------------------------
  const countUpElements = document.querySelectorAll('[data-countup]');

  countUpElements.forEach(el => {
    const target = parseInt(el.getAttribute('data-countup'), 10);
    if (isNaN(target)) return;

    if (prefersReducedMotion) {
      el.textContent = target.toLocaleString();
      return;
    }

    const duration = 650; // milliseconds
    const startTime = performance.now();

    function updateCount(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic calculation
      const easeOut = 1 - Math.pow(1 - progress, 3);
      const currentVal = Math.floor(easeOut * target);

      el.textContent = currentVal.toLocaleString();

      if (progress < 1) {
        requestAnimationFrame(updateCount);
      } else {
        el.textContent = target.toLocaleString();
      }
    }

    requestAnimationFrame(updateCount);
  });

  // -------------------------------------------------------------------------
  // 3. Auto-Dismiss of Floating Messages / Alerts
  // -------------------------------------------------------------------------
  const autoDismissAlerts = document.querySelectorAll('.toast-container-custom .custom-alert');

  autoDismissAlerts.forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity 250ms ease-out, transform 250ms ease-out';
      alert.style.opacity = '0';
      alert.style.transform = 'translateX(20px)';
      setTimeout(() => {
        if (alert.parentNode) alert.parentNode.removeChild(alert);
      }, 260);
    }, 4500);
  });
});

