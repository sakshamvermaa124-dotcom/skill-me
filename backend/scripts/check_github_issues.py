import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from services.github_service import github_service
    
    # First check what org/user is configured
    print(f'GitHub org/user: {github_service.org}')
    
    # Check all issues in python-batch-1 (all assignees) to see what's there
    resp = await github_service.client.get(
        f'/repos/{github_service.org}/python-batch-1/issues',
        params={'state': 'all', 'per_page': 50}
    )
    print(f'\nAll issues in python-batch-1 (HTTP {resp.status_code}):')
    data = resp.json()
    if isinstance(data, list):
        real = [i for i in data if 'pull_request' not in i]
        for i in real:
            assignees = [a['login'] for a in i.get('assignees', [])]
            print(f"  #{i['number']} [{i['state']}] {i['title']} — assignees: {assignees}")
    else:
        print(data)

asyncio.run(main())
