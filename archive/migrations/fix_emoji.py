with open('dashboard.js', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('dY"S', '📄')
content = content.replace('// ?? Dynamic', '// 🚀 Dynamic')

with open('dashboard.js', 'w', encoding='utf-8') as f:
    f.write(content)
