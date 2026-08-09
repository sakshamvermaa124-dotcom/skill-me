import sys

with open('dashboard.js', encoding='utf-8') as f:
    text = f.read()

def find_unbalanced():
    stack = []
    i = 0
    while i < len(text):
        c = text[i]
        if c in '({[':
            stack.append((c, i))
        elif c in ')}]':
            if not stack:
                print('Unmatched', c, 'at', i, 'line', text[:i].count('\n') + 1)
                return
            last_c, last_i = stack.pop()
            if (c == ')' and last_c != '(') or (c == '}' and last_c != '{') or (c == ']' and last_c != '['):
                print('Mismatched', c, 'at', i, 'line', text[:i].count('\n') + 1, 'expected to match', last_c, 'from line', text[:last_i].count('\n') + 1)
                return
        elif c in '\"\'`':
            quote = c
            i += 1
            while i < len(text):
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == quote:
                    break
                i += 1
        elif text[i:i+2] == '//':
            while i < len(text) and text[i] != '\n':
                i += 1
        elif text[i:i+2] == '/*':
            while i < len(text) and text[i:i+2] != '*/':
                i += 1
        i += 1
    
    if stack:
        print('Unclosed', stack[-1][0], 'from line', text[:stack[-1][1]].count('\n') + 1)
    else:
        print('Balanced!')

find_unbalanced()
