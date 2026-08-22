import urllib.request, json, time, os
token = os.environ.get('GITHUB_TOKEN', '')  # Set GITHUB_TOKEN env var before running

missing = [
    'react-template', 'node-template', 'java-template', 
    'datascience-template', 'flutter-template', 'devops-template', 
    'cpp-template', 'cloud-template', 'cyber-template'
]

for repo in missing:
    print(f'Creating {repo}...')
    # 1. Create Repo with auto_init
    req = urllib.request.Request(
        'https://api.github.com/user/repos',
        data=json.dumps({
            'name': repo,
            'description': f'Template for {repo.replace("-", " ")}',
            'auto_init': True
        }).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    )
    try:
        res = urllib.request.urlopen(req, timeout=10)
        print(f'  Created {repo}')
    except Exception as e:
        print(f'  Failed to create {repo}: {e}')
        continue
    
    time.sleep(1) # Wait a bit for GitHub to process auto_init
    
    # 2. Mark as Template
    req_patch = urllib.request.Request(
        f'https://api.github.com/repos/sakshamvermaa124-dotcom/{repo}',
        data=json.dumps({'is_template': True}).encode(),
        headers={
            'Authorization': f'Bearer {token}', 
            'Content-Type': 'application/json',
            'Accept': 'application/vnd.github+json'
        },
        method='PATCH'
    )
    try:
        res_patch = urllib.request.urlopen(req_patch, timeout=10)
        print(f'  Marked {repo} as template')
    except Exception as e:
        print(f'  Failed to mark {repo} as template: {e}')
