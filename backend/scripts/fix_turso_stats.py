import json
import urllib.request
from dotenv import dotenv_values

env = dotenv_values('backend/.env')
url = env['TURSO_DB_URL'].replace('libsql://', 'https://') + '/v2/pipeline'
token = env['TURSO_AUTH_TOKEN']

body = json.dumps({
    "requests": [
        {
            "type": "execute",
            "stmt": {
                "sql": "UPDATE progress SET issues_completed=1, prs_merged=1, score=25 WHERE student_id=11 AND batch_id=4 AND week=1"
            }
        },
        {
            "type": "execute",
            "stmt": {
                "sql": "INSERT INTO submissions (student_id, batch_id, issue_id, pr_number, pr_url, status) VALUES (11, 4, 1, 1, 'https://github.com/sakshamvermaa124-dotcom/python-batch-1/pull/1', 'merged')"
            }
        },
        {"type": "close"}
    ]
}).encode('utf-8')

req = urllib.request.Request(url, data=body, headers={
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
})

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8'))
except Exception as e:
    print(e)
    if hasattr(e, 'read'):
        print(e.read().decode('utf-8'))
