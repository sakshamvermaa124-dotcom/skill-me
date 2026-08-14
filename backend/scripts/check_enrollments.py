import sqlite3
conn = sqlite3.connect('backend/data/skillme.db')
c = conn.cursor()
c.execute("SELECT id FROM students WHERE github_username = 'n8nsaksham-web'")
student = c.fetchone()
if student:
    c.execute("SELECT * FROM enrollments WHERE student_id = ?", (student[0],))
    print("Enrollments:", c.fetchall())
else:
    print("Student not found")
