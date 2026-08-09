import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'skillme.db')

def bump_to_100():
    print("Mocking a student to 100% completion...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get a student
    cursor.execute("SELECT id, email, github_username FROM students WHERE github_username IS NOT NULL LIMIT 1")
    student = cursor.fetchone()
    
    if not student:
        print("No student found. Please login at least once to create a student record.")
        conn.close()
        return

    student_id = student[0]
    email = student[1]
    github = student[2]
    print(f"Target Student: {email} (GitHub: {github})")

    # Enroll in a batch if not already
    cursor.execute("SELECT id FROM batches LIMIT 1")
    batch = cursor.fetchone()
    if not batch:
        print("No batches found in DB.")
        conn.close()
        return
    batch_id = batch[0]
    
    cursor.execute("INSERT OR IGNORE INTO enrollments (student_id, batch_id, status) VALUES (?, ?, 'enrolled')", (student_id, batch_id))
    
    # Bump progress to 100% (issues_completed = 4)
    # The frontend calculates pct = Math.min(100, Math.round((issues_completed / 4) * 100))
    cursor.execute("""
        INSERT INTO progress (student_id, batch_id, issues_completed, prs_merged, score)
        VALUES (?, ?, 4, 4, 100)
        ON CONFLICT(student_id, batch_id) DO UPDATE SET 
            issues_completed = 4,
            prs_merged = 4,
            score = 100
    """, (student_id, batch_id))
    
    # Insert some fake merged submissions so the portfolio looks good
    cursor.execute("SELECT id FROM issues WHERE batch_id = ? LIMIT 2", (batch_id,))
    issues = cursor.fetchall()
    
    for i, issue in enumerate(issues):
        issue_id = issue[0]
        cursor.execute("""
            INSERT OR REPLACE INTO submissions (student_id, issue_id, batch_id, pr_url, pr_number, status, merged_at)
            VALUES (?, ?, ?, ?, ?, 'merged', CURRENT_TIMESTAMP)
        """, (student_id, issue_id, batch_id, f"https://github.com/mock/repo/pull/{100+i}", 100+i))

    # DELETE ANY EXISTING PAYMENT SO THEY SEE THE BANNER FIRST
    cursor.execute("DELETE FROM payments WHERE student_id = ? AND batch_id = ?", (student_id, batch_id))
    
    conn.commit()
    conn.close()
    
    print("\nSUCCESS! ✅")
    print(f"Log into the dashboard with: {email}")
    print("You will see the 100% completion payment banner.")
    print("\nTo see the 'Paid' state and Portfolio UI, run this again after uncommenting the payment line in this script, or just complete the mock payment on the dashboard!")

if __name__ == "__main__":
    bump_to_100()
