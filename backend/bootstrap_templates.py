import asyncio
import httpx
import os
from config import settings

async def setup_templates():
    org = settings.github_org
    token = settings.skillme_github_token
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    templates = ["web-dev-template", "python-template"]
    
    async with httpx.AsyncClient(base_url="https://api.github.com", headers=headers) as client:
        # Check if we are a user or an org context
        user_res = await client.get("/user")
        user = user_res.json()
        
        create_url = f"/user/repos"
        
        for name in templates:
            print(f"Creating {name}...")
            # Create repo
            res = await client.post(
                create_url,
                json={
                    "name": name,
                    "description": f"SkillMe {name.replace('-template', '').replace('-', ' ').title()} Internship Template",
                    "private": False,
                    "is_template": True,
                    "auto_init": True,
                }
            )
            
            if res.status_code == 201:
                print(f"[OK] Created {name}")
            elif res.status_code == 422:
                print(f"[WARN] Repo {name} might already exist or validation failed: {res.json()}")
                
                patch_res = await client.patch(
                    f"/repos/{org}/{name}",
                    json={"is_template": True}
                )
                if patch_res.status_code == 200:
                    print(f"[OK] Updated {name} to be a template")
            else:
                print(f"[ERROR] Failed to create {name}: {res.status_code} {res.text}")

if __name__ == "__main__":
    asyncio.run(setup_templates())
