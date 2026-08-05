import urllib.request, json

TURSO_URL = 'https://skillme-db-saksahm.aws-ap-south-1.turso.io'
AUTH_TOKEN = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODU1MTg5NjksImlkIjoiMDE5ZmI5MzctYWQwMS03YjM3LTgyZTctZjJmOWIyMzg3NDUzIiwia2lkIjoiSDdIWkFQenRlbTMzNVMwNS1CNzNjYU5XNUUtNmVsb1BXaEtyalhpcF9TNCIsInJpZCI6IjNiNWI5MWE3LWRkMzEtNDBlMi05ZmRmLWVlNjk3MzM0MjNlNiJ9.IkHKCZPMUTZv9jygU0QWGsVrhUIGpudJ9DECxaBH5TEa7uX44LtIXhCfCGbcpxsC7V-eIHvsyC6QyMKj8Lt_Ag'

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
for r in query('SELECT id, domain, batch_number, status, max_students FROM batches ORDER BY id'):
    print(r)

print()
print('=== ENROLLMENTS ===')
for r in query('SELECT id, student_id, batch_id, status FROM enrollments ORDER BY id'):
    print(r)

print()
print('=== ENROLLMENT COUNTS PER BATCH (not dropped) ===')
for r in query("SELECT batch_id, COUNT(*) as count FROM enrollments WHERE status != 'dropped' GROUP BY batch_id"):
    print(r)
