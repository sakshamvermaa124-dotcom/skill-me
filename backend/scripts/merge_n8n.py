import sqlite3
conn = sqlite3.connect('backend/data/skillme.db')
c = conn.cursor()
c.execute("SELECT id FROM students WHERE email = 'sakshamverma124@gmail.com'")
real_id = c.fetchone()[0]

c.execute("SELECT id FROM students WHERE github_username = 'n8nsaksham-web'")
fake_id = c.fetchone()[0]

if real_id != fake_id:
    # point the PRs and progress to real_id
    c.execute("UPDATE submissions SET student_id = ? WHERE student_id = ?", (real_id, fake_id))
    c.execute("UPDATE progress SET student_id = ? WHERE student_id = ?", (real_id, fake_id))
    # update real_id github username and domain
    c.execute("UPDATE students SET github_username = 'n8nsaksham-web', domain = 'python' WHERE id = ?", (real_id,))
    # delete fake_id
    c.execute("DELETE FROM students WHERE id = ?", (fake_id,))
    conn.commit()
    print('Merged successfully')
else:
    print('Already merged')
