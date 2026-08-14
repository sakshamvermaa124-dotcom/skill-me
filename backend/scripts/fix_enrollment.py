import sqlite3
conn = sqlite3.connect('backend/data/skillme.db')
c = conn.cursor()
c.execute("SELECT id FROM students WHERE github_username = 'n8nsaksham-web'")
student_id = c.fetchone()[0]

c.execute("SELECT id FROM batches WHERE repo_name = 'python-batch-1'")
batch_id = c.fetchone()[0]

c.execute("INSERT INTO enrollments (student_id, batch_id, status) VALUES (?, ?, 'active')", (student_id, batch_id))
conn.commit()
print("Enrolled!")
