import sqlite3

conn = sqlite3.connect('backend/data/skillme.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 1. Restore sakshamverma124@gmail.com
c.execute("UPDATE students SET github_username = 'sakshammverma', domain = 'web-dev' WHERE email = 'sakshamverma124@gmail.com'")
real_id = c.execute("SELECT id FROM students WHERE email = 'sakshamverma124@gmail.com'").fetchone()[0]

# 2. Create the new user bsaksham191@gmail.com
c.execute("""
    INSERT INTO students (first_name, last_name, email, github_username, domain, status)
    VALUES ('Saksham', 'Verma', 'bsaksham191@gmail.com', 'n8nsaksham-web', 'python', 'enrolled')
""")
new_id = c.lastrowid

# 3. Move the python PRs and progress from real_id to new_id
# We only move the one for python-batch-1
c.execute("SELECT id FROM batches WHERE repo_name = 'python-batch-1'")
python_batch_id = c.fetchone()[0]

c.execute("UPDATE submissions SET student_id = ? WHERE student_id = ? AND batch_id = ?", (new_id, real_id, python_batch_id))
c.execute("UPDATE progress SET student_id = ? WHERE student_id = ? AND batch_id = ?", (new_id, real_id, python_batch_id))

conn.commit()
print('Fixed successfully')
