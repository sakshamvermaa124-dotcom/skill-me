import re

with open('dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add data-theme="dark" to html tag
content = content.replace('<html lang="en">', '<html lang="en" data-theme="dark">')

# 2. Add theme toggle HTML to the body
theme_toggle_html = '''
  <!-- Theme Toggle -->
  <button class="theme-toggle" id="theme-toggle" aria-label="Toggle light/dark mode" style="position: fixed; top: 24px; right: 24px; z-index: 1000; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--bg-card); border: var(--border-glass); color: var(--text-secondary); cursor: pointer; backdrop-filter: blur(10px); transition: transform 0.3s ease, border-color 0.3s ease, color 0.3s ease;">
    <!-- Sun icon -->
    <svg class="theme-icon" id="sun-icon" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/>
      <line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/>
      <line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
    <!-- Moon icon -->
    <svg class="theme-icon" id="moon-icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
    </svg>
  </button>
'''
content = content.replace('<body>', '<body>' + theme_toggle_html)

# 3. Add script logic at the bottom of the file (before </body>)
script_logic = '''
  <script>
    // Theme toggle logic specific for dashboard
    const themeToggle = document.getElementById('theme-toggle');
    const html = document.documentElement;
    const savedTheme = localStorage.getItem('skillme-theme') || 'dark';
    html.setAttribute('data-theme', savedTheme);
    
    themeToggle.addEventListener('click', () => {
      const current = html.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      localStorage.setItem('skillme-theme', next);
      themeToggle.style.transform = 'rotate(360deg) scale(1.1)';
      setTimeout(() => { themeToggle.style.transform = ''; }, 300);
    });
  </script>
'''
content = content.replace('</body>', script_logic + '\\n</body>')

# 4. Remove Aurora & Grid backgrounds
content = re.sub(r'<div class="aurora-bg".*?</div>', '', content, flags=re.DOTALL)
content = re.sub(r'<div class="grid-overlay".*?</div>', '', content, flags=re.DOTALL)
content = re.sub(r'/\* ======== Aurora Background ======== \*/.*?/\* ======== Dashboard Layout ======== \*/', '/* ======== Dashboard Layout ======== */', content, flags=re.DOTALL)

# 5. Add custom CSS rules inside the <style> block for light/dark
css_additions = '''
    /* Global dashboard background override */
    body { background: var(--bg-primary); color: var(--text-primary); transition: background 0.3s ease, color 0.3s ease; }
    
    /* Sun/Moon hide logic */
    [data-theme="light"] #sun-icon { display: none; }
    [data-theme="dark"] #moon-icon { display: none; }
    
    /* Overrides */
    .theme-toggle:hover { border-color: var(--border-indigo); color: var(--accent-indigo); }
'''
content = content.replace('<style>', '<style>' + css_additions)

# 6. Replace hardcoded colors with CSS variables from style.css
# Backgrounds
content = re.sub(r'background:\s*rgba\(255,\s*255,\s*255,\s*0\.0[34]\);', 'background: var(--bg-card);', content)
content = re.sub(r'background:\s*rgba\(255,\s*255,\s*255,\s*0\.0[56]\);', 'background: var(--bg-card-hover);', content)

# Borders
content = re.sub(r'border:\s*1px solid rgba\(255,\s*255,\s*255,\s*0\.0[68]\);', 'border: var(--border-glass);', content)
content = re.sub(r'border:\s*1px solid rgba\(255,\s*255,\s*255,\s*0\.1[02]\);', 'border: var(--border-subtle);', content)
content = re.sub(r'border-bottom:\s*1px solid rgba\(255,\s*255,\s*255,\s*0\.0[5-9]\);', 'border-bottom: var(--border-glass);', content)
content = re.sub(r'border-top:\s*1px solid rgba\(255,\s*255,\s*255,\s*0\.0[5-9]\);', 'border-top: var(--border-glass);', content)

# Colors
content = re.sub(r'color:\s*#fff;', 'color: var(--text-primary);', content)
content = re.sub(r'color:\s*rgba\(255,\s*255,\s*255,\s*0\.[78]\);', 'color: var(--text-primary);', content)
content = re.sub(r'color:\s*rgba\(255,\s*255,\s*255,\s*0\.[45]\);', 'color: var(--text-secondary);', content)
content = re.sub(r'color:\s*rgba\(255,\s*255,\s*255,\s*0\.3\);', 'color: var(--text-muted);', content)

# Gradients
content = re.sub(r'background:\s*linear-gradient\(135deg,\s*#6366f1,\s*#8b5cf6\);', 'background: var(--gradient-indigo);', content)

# Remove background for html/body if defined
content = re.sub(r'background-color:\s*#0a0a0f;', 'background-color: transparent;', content)
content = re.sub(r'background:\s*#000;', 'background: transparent;', content)

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Dashboard updated successfully!")
