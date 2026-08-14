import sqlite3

conn = sqlite3.connect('backend/data/skillme.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT * FROM students WHERE email = 'bsaksham191@gmail.com'")
rows = c.fetchall()
print([dict(r) for r in rows])
