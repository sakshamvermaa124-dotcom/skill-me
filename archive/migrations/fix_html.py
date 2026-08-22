with open('dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix Lenis scroll issue
content = content.replace(
    '<div class="milestone-preview-box" id="milestone-post-preview"></div>',
    '<div class="milestone-preview-box" id="milestone-post-preview" data-lenis-prevent></div>'
)

# Fix corrupted emojis in buttons
content = content.replace('Share on LinkedIn ?', 'Share on LinkedIn &#x2197;')
content = content.replace('Copy Text ??', 'Copy Text &#128203;')

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)
