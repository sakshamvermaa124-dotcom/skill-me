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
                "sql": "SELECT id, email, github_username FROM students"
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
