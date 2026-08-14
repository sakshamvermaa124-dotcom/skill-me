import sqlite3

conn = sqlite3.connect('backend/data/skillme.db')
c = conn.cursor()

c.execute("UPDATE students SET email = 'n8n.saksham@gmail.com' WHERE github_username = 'n8nsaksham-web'")
conn.commit()

print(f"Updated {c.rowcount} rows to use email n8n.saksham@gmail.com")
conn.close()
