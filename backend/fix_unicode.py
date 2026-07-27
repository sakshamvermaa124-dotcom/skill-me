import codecs

with codecs.open('cli.py', 'r', 'utf-8') as f:
    text = f.read()

text = text.replace('✓', 'OK').replace('✗', 'X').replace('—', '-').replace('─', '=')

with codecs.open('cli.py', 'w', 'utf-8') as f:
    f.write(text)
