// theme.js - Global Theme Manager
(function() {
  const savedTheme = localStorage.getItem('skillme-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);

  // Automatically attach click listener to any theme-toggle button once DOM is loaded
  document.addEventListener('DOMContentLoaded', () => {
    const toggles = document.querySelectorAll('.theme-toggle');
    toggles.forEach(toggle => {
      toggle.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('skillme-theme', next);
        
        // Notify Three.js scenes if present
        window.dispatchEvent(new CustomEvent('themechange', { detail: { theme: next } }));
      });
    });
  });
})();
