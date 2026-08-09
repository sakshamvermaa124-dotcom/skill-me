import os
import re

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.join(current_dir, "..", "..")

html_files = ['index.html', 'dashboard.html', 'apply.html']
for filename in html_files:
    filepath = os.path.join(root_dir, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace .png with .webp for assets/
        content = re.sub(r'assets/(.*?)\.png', r'assets/\1.webp', content)
        
        # Add defer to scripts that don't have it (excluding inline scripts or already deferred scripts)
        content = re.sub(r'<script src="([^"]+)"(?! defer)></script>', r'<script src="\1" defer></script>', content)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Updated {filename}')
