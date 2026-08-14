import sqlite3
import json

conn = sqlite3.connect('backend/data/skillme.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get schema for students table
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='students'")
print("Students schema:", cursor.fetchone()[0])

cursor.execute("SELECT * FROM students WHERE github_username = 'n8nsaksham-web'")
student = cursor.fetchone()

if student:
    print('Student found:', dict(student))
    cursor.execute('SELECT * FROM submissions WHERE student_id = ?', (student['id'],))
    submissions = cursor.fetchall()
    print('\nSubmissions:')
    for sub in submissions:
        print(dict(sub))
        
    cursor.execute('SELECT * FROM weekly_progress WHERE student_id = ?', (student['id'],))
    progress = cursor.fetchall()
    print('\nProgress:')
    for p in progress:
        print(dict(p))
else:
    print('Student not found')
