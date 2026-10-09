import os
import urllib.request, json

TURSO_URL = 'https://skillme-db-saksahm.aws-ap-south-1.turso.io'
AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]

def query(sql):
    req = urllib.request.Request(
        f'{TURSO_URL}/v2/pipeline',
        data=json.dumps({'requests': [{'type': 'execute', 'stmt': {'sql': sql}}, {'type': 'close'}]}).encode(),
        headers={'Authorization': f'Bearer {AUTH_TOKEN}', 'Content-Type': 'application/json'},
        method='POST'
    )
    res = urllib.request.urlopen(req, timeout=15)
    data = json.loads(res.read())
    result = data['results'][0]['response']['result']
    cols = [c['name'] for c in result['cols']]
    rows = [{cols[i]: cell.get('value') for i, cell in enumerate(row)} for row in result['rows']]
    return rows

print('=== BATCHES ===')
for r in query('SELECT id, domain, batch_number, repo_name, status, max_students FROM batches ORDER BY id'):
    print(r)

print()
print('=== ENROLLMENTS ===')
for r in query('SELECT id, student_id, batch_id, status FROM enrollments ORDER BY id'):
    print(r)

print()
print()
print('=== DELETING ORPHANED ISSUES ===')
query('DELETE FROM issues WHERE github_issue_number IS NULL')
print('Deleted.')
