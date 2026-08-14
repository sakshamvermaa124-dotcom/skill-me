import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'skillme.db')

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def simulate_get_portfolio(github_username):
    print(f"\n--- Simulating GET /api/portfolio/{github_username} ---")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    # 1. Look up student
    cursor.execute(
        "SELECT id, first_name, last_name, github_username, email, college, domain FROM students WHERE LOWER(github_username) = LOWER(?)",
        (github_username,)
    )
    student = cursor.fetchone()
    if not student:
        print("Result: 404 Not Found (Student not found)")
        conn.close()
        return

    student_id = student["id"]

    # 2. Check payment
    cursor.execute(
        "SELECT id FROM payments WHERE student_id = ? AND status = 'paid' LIMIT 1",
        (student_id,)
    )
    payment = cursor.fetchone()
    
    if not payment:
        print("Result: 403 Forbidden (payment_required)")
        conn.close()
        return

    # 3. Stats
    cursor.execute(
        """SELECT 
             COALESCE(SUM(issues_completed), 0) as total_tasks_completed,
             COALESCE(SUM(prs_merged), 0) as total_prs_merged,
             COALESCE(SUM(score), 0) as total_score
           FROM progress WHERE student_id = ?""",
        (student_id,)
    )
    stats = cursor.fetchone()

    # 4. Domains
    cursor.execute(
        """SELECT b.domain, b.batch_number, e.status 
           FROM enrollments e 
           JOIN batches b ON e.batch_id = b.id 
           WHERE e.student_id = ? AND e.status IN ('enrolled', 'active', 'completed')""",
        (student_id,)
    )
    batches = cursor.fetchall()

    # 5. Submissions
    cursor.execute(
        """SELECT s.pr_url, s.pr_number, s.merged_at, i.title, b.domain 
           FROM submissions s
           JOIN issues i ON s.issue_id = i.id
           JOIN batches b ON s.batch_id = b.id
           WHERE s.student_id = ? AND s.status = 'merged'
           ORDER BY s.merged_at DESC
           LIMIT 10""",
        (student_id,)
    )
    submissions = cursor.fetchall()
    
    conn.close()

    print("Result: 200 OK")
    print("Profile:", f"{student['first_name']} {student['last_name']}")
    print("Stats:", stats)
    print("Domains:", [b["domain"] for b in batches])
    print(f"Submissions Count: {len(submissions)}")

def test_logic():
    print("Testing Portfolio DB Logic...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    # Paid
    cursor.execute("""
        SELECT s.github_username 
        FROM students s 
        JOIN payments p ON s.id = p.student_id 
        WHERE p.status = 'paid' AND s.github_username IS NOT NULL
        LIMIT 1
    """)
    paid = cursor.fetchone()
    
    # Unpaid
    cursor.execute("""
        SELECT s.github_username 
        FROM students s 
        LEFT JOIN payments p ON s.id = p.student_id AND p.status = 'paid'
        WHERE p.id IS NULL AND s.github_username IS NOT NULL
        LIMIT 1
    """)
    unpaid = cursor.fetchone()
    conn.close()
    
    if paid:
        simulate_get_portfolio(paid['github_username'])
    else:
        print("\nNo paid student found in DB")
        
    if unpaid:
        simulate_get_portfolio(unpaid['github_username'])
    else:
        print("\nNo unpaid student found in DB")
        
    simulate_get_portfolio("nonexistent_ghost_123")

if __name__ == "__main__":
    test_logic()
