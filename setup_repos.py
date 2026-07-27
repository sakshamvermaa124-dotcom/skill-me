import os
import subprocess
import shutil
import stat

def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def setup_repo(repo_name, title):
    token = os.getenv("SKILLME_GITHUB_TOKEN")
    org = "sakshamvermaa124-dotcom"
    clone_url = f"https://{token}@github.com/{org}/{repo_name}.git"
    
    # Clean up old dir if exists
    if os.path.exists(repo_name):
        shutil.rmtree(repo_name, onerror=remove_readonly)
        
    print(f"Cloning {repo_name}...")
    subprocess.run(["git", "clone", clone_url], check=True)
    
    print(f"Pushing {repo_name}...")
    # Git commands
    env = os.environ.copy()
    subprocess.run(["git", "config", "user.name", "SkillMe Bot"], cwd=repo_name, env=env)
    subprocess.run(["git", "config", "user.email", "bot@skillme.local"], cwd=repo_name, env=env)
    subprocess.run(["git", "add", "."], cwd=repo_name, env=env)
    subprocess.run(["git", "commit", "-m", "Initial setup"], cwd=repo_name, env=env)
    subprocess.run(["git", "push"], cwd=repo_name, env=env)
    
    # Clean up
    shutil.rmtree(repo_name, onerror=remove_readonly)
    print(f"[OK] {repo_name} setup complete!")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv("backend/.env")
    
    setup_repo("web-dev-template", "Web Development")
    setup_repo("python-template", "Python")
