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
    return json.loads(res.read())

print(query("UPDATE enrollments SET github_invite_status = 'accepted' WHERE student_id=4 AND batch_id=2"))
print(query("UPDATE batches SET repo_name = 'ml-batch-1' WHERE id=2"))
