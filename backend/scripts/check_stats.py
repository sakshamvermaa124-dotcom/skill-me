import sqlite3
import json

conn = sqlite3.connect('backend/data/skillme.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT * FROM students WHERE email = 'n8n.saksham@gmail.com'")
student = cursor.fetchone()

if student:
    print('--- Student ---')
    print(dict(student))
    
    print('\n--- Progress ---')
    cursor.execute('SELECT * FROM progress WHERE student_id = ?', (student['id'],))
    progress = cursor.fetchall()
    for p in progress:
        print(dict(p))

    print('\n--- Submissions ---')
    cursor.execute('SELECT * FROM submissions WHERE student_id = ?', (student['id'],))
    submissions = cursor.fetchall()
    for s in submissions:
        print(dict(s))
else:
    print('Student not found')
