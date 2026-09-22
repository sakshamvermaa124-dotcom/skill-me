import os
import re
from datetime import datetime

html_files = [f for f in os.listdir('.') if f.endswith('.html')]

# We'll use today's date and time for versioning: YYYYMMDD_HHMMSS
today = datetime.now().strftime("%Y%m%d_%H%M%S")
new_version = f"{today}"

script_pattern = re.compile(r'(\.js\?v=)[a-zA-Z0-9_]+')
css_pattern = re.compile(r'(\.css\?v=)[a-zA-Z0-9_]+')

for file in html_files:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        updated = script_pattern.sub(r'\g<1>' + new_version, content)
        updated = css_pattern.sub(r'\g<1>' + new_version, updated)
        
        if updated != content:
            with open(file, 'w', encoding='utf-8') as f:
                f.write(updated)
            print(f"Updated {file}")
    except UnicodeDecodeError:
        print(f"Skipping {file} due to encoding issue")
