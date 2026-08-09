import os
import re

current_dir = os.path.dirname(os.path.abspath(__file__))
filepath = os.path.join(current_dir, "..", "..", "style.css")

if os.path.exists(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Update aurora-blob
    content = content.replace('filter: blur(80px); opacity: 0.18;', 'filter: blur(60px); opacity: 0.18; will-change: transform; transform: translateZ(0);')
    content = content.replace('filter: blur(80px);', 'filter: blur(60px); will-change: transform; transform: translateZ(0);')
    
    # Update backdrop-filter globals if they exist in standard blur sizes
    content = content.replace('backdrop-filter: blur(28px);', 'backdrop-filter: blur(16px);')
    content = content.replace('-webkit-backdrop-filter: blur(28px);', '-webkit-backdrop-filter: blur(16px);')
    content = content.replace('backdrop-filter: blur(24px);', 'backdrop-filter: blur(16px);')
    content = content.replace('-webkit-backdrop-filter: blur(24px);', '-webkit-backdrop-filter: blur(16px);')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Updated style.css')
