// theme.js - Global Theme Manager
(function() {
  const savedTheme = localStorage.getItem('skillme-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
})();
