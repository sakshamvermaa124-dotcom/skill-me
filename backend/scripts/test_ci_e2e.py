"""
SkillMe — End-to-End CI Test
Simulates a real student submission on data-science-batch-1:
  1. Creates a feature branch
  2. Pushes realistic Week 1 data science files (pandas + numpy)
  3. Adds PROGRESS.md
  4. Opens a PR
  5. Polls for the Actions workflow result
  6. Reports the final outcome
"""

import asyncio, base64, httpx, sys, json, time
sys.stdout.reconfigure(encoding="utf-8")

import os
TOKEN    = os.environ.get("SKILLME_GITHUB_TOKEN", "")
ORG      = "sakshamvermaa124-dotcom"
REPO     = "data-science-batch-1"
BRANCH   = "week-1-submission-test"
BASE     = "main"

H = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
API = "https://api.github.com"

PASS = "✅"; FAIL = "❌"; INFO = "ℹ️ "; WAIT = "⏳"

# ── Realistic student code files ─────────────────────────────────────────────

ANALYSIS_PY = '''"""
Week 1 Task: Pandas & NumPy Data Analysis
Student: Test Submission
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load and explore a sample dataset
np.random.seed(42)
n = 200

data = pd.DataFrame({
    "age":     np.random.randint(18, 65, n),
    "salary":  np.random.normal(50000, 15000, n).round(2),
    "score":   np.random.uniform(0, 100, n).round(1),
    "dept":    np.random.choice(["Engineering", "Marketing", "Finance", "HR"], n),
})

# Basic exploration
print("=== Dataset Overview ===")
print(data.head())
print("\\nShape:", data.shape)
print("\\nDescriptive Stats:")
print(data.describe())

# Group analysis
dept_avg = data.groupby("dept")["salary"].mean().sort_values(ascending=False)
print("\\nAverage Salary by Department:")
print(dept_avg)

# Correlation
numeric_cols = data.select_dtypes(include=np.number)
corr = numeric_cols.corr()
print("\\nCorrelation Matrix:")
print(corr)

# Filter high earners
high_earners = data[data["salary"] > data["salary"].mean() + data["salary"].std()]
print(f"\\nHigh earners ({len(high_earners)} people): avg score = {high_earners['score'].mean():.2f}")
'''

DATA_CLEANING_PY = '''"""
Week 1 Task: Data Cleaning with Pandas
"""
import pandas as pd
import numpy as np

def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Clean a raw dataset: handle nulls, fix dtypes, remove duplicates."""
    df = df.copy()

    # 1. Drop duplicates
    before = len(df)
    df.drop_duplicates(inplace=True)
    print(f"Removed {before - len(df)} duplicate rows")

    # 2. Handle missing values
    for col in df.select_dtypes(include=np.number).columns:
        df[col].fillna(df[col].median(), inplace=True)
    for col in df.select_dtypes(include="object").columns:
        df[col].fillna(df[col].mode()[0] if not df[col].mode().empty else "Unknown", inplace=True)

    # 3. Remove outliers (IQR method)
    num_cols = df.select_dtypes(include=np.number).columns
    for col in num_cols:
        Q1, Q3 = df[col].quantile([0.25, 0.75])
        IQR     = Q3 - Q1
        df = df[(df[col] >= Q1 - 1.5*IQR) & (df[col] <= Q3 + 1.5*IQR)]

    print(f"Clean dataset: {len(df)} rows, {len(df.columns)} columns")
    return df


if __name__ == "__main__":
    # Test with synthetic data
    np.random.seed(0)
    raw = pd.DataFrame({
        "x": np.append(np.random.normal(0, 1, 100), [999, -999]),  # outliers
        "y": np.random.choice(["A","B","C", None], 102),
    })
    cleaned = clean_dataset(raw)
    print(cleaned.describe())
'''

PROGRESS_MD = """# Week 1 Progress — Data Science Internship

## Tasks Completed

- [x] **Task 1: Research & Setup** — Installed pandas, numpy, matplotlib. Explored DataFrame operations.
- [x] **Task 2: Core Implementation** — Built data analysis pipeline with groupby, correlation, filtering.
- [x] **Task 3: Data Cleaning** — Implemented IQR outlier removal, null handling, deduplication.

## What I Learned

1. **Pandas GroupBy** — Powerful for aggregate statistics across categories.
2. **NumPy Broadcasting** — Efficient vectorized operations without loops.
3. **Data Cleaning Pipeline** — Real datasets always need preprocessing before analysis.

## Challenges

- Understanding the difference between `loc` and `iloc` for indexing.
- Handling mixed dtypes in DataFrames during cleaning.

## Next Steps (Week 2)

- Implement a more complex ML pipeline using scikit-learn.
- Explore feature engineering techniques.
"""


# ── Git Data API helpers ──────────────────────────────────────────────────────

async def gh(client, method, path, **kw):
    r = await client.request(method, f"{API}{path}", headers=H, **kw)
    try:    body = r.json()
    except: body = r.text
    return r.status_code, body


async def get_ref_sha(client, repo, ref="main"):
    s, b = await gh(client, "GET", f"/repos/{ORG}/{repo}/git/refs/heads/{ref}")
    if s == 200:
        return b["object"]["sha"]
    return None


async def create_branch(client, repo, branch, from_sha):
    s, b = await gh(client, "POST", f"/repos/{ORG}/{repo}/git/refs",
                    json={"ref": f"refs/heads/{branch}", "sha": from_sha})
    if s == 201:
        return True
    if s == 422 and "already exists" in str(b):
        return True   # branch already there from previous run
    print(f"  {FAIL} create_branch HTTP {s}: {b}")
    return False


async def push_file(client, repo, branch, path, content_str, message):
    """Push a single file via Contents API (works now with workflow scope)."""
    # Check if file already exists
    s, existing = await gh(client, "GET", f"/repos/{ORG}/{repo}/contents/{path}",
                           params={"ref": branch})
    sha = existing.get("sha") if s == 200 and isinstance(existing, dict) else None

    payload = {
        "message": message,
        "content": base64.b64encode(content_str.encode()).decode(),
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    s2, b2 = await gh(client, "PUT", f"/repos/{ORG}/{repo}/contents/{path}", json=payload)
    return s2 in (200, 201)


async def create_pr(client, repo, branch, base, title, body):
    s, b = await gh(client, "POST", f"/repos/{ORG}/{repo}/pulls",
                    json={"title": title, "body": body, "head": branch, "base": base})
    if s == 201:
        return b["number"], b["html_url"]
    if s == 422:  # PR might already exist
        # Find existing PR for this branch
        s2, prs = await gh(client, "GET", f"/repos/{ORG}/{repo}/pulls",
                           params={"head": f"{ORG}:{branch}", "state": "open"})
        if s2 == 200 and prs:
            return prs[0]["number"], prs[0]["html_url"]
    print(f"  {FAIL} create_pr HTTP {s}: {b}")
    return None, None


async def poll_workflow(client, repo, pr_number, timeout=300):
    """Poll for the PR's check run result. Returns (conclusion, details_url)."""
    deadline = time.time() + timeout
    last_status = ""
    while time.time() < deadline:
        s, runs = await gh(client, "GET",
            f"/repos/{ORG}/{repo}/commits/{BRANCH}/check-runs")
        if s == 200 and runs.get("check_runs"):
            for run in runs["check_runs"]:
                if "skillme" in run["name"].lower() or "evaluate" in run["name"].lower():
                    status     = run["status"]
                    conclusion = run.get("conclusion")
                    url        = run["html_url"]
                    status_str = f"{status}/{conclusion}"
                    if status_str != last_status:
                        if status == "in_progress":
                            print(f"  {WAIT} Workflow running... ({int(deadline - time.time())}s left)")
                        last_status = status_str
                    if status == "completed":
                        return conclusion, url
        await asyncio.sleep(10)
    return "timeout", ""


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("\n" + "─"*62)
    print("  SkillMe — End-to-End PR Evaluation Test")
    print("─"*62 + "\n")

    async with httpx.AsyncClient(timeout=30) as client:

        # 1. Get main branch SHA
        print("1. Getting base commit SHA...")
        base_sha = await get_ref_sha(client, REPO, BASE)
        if not base_sha:
            print(f"  {FAIL} Could not get main SHA"); return
        print(f"  {PASS} main → {base_sha[:8]}")

        # 2. Create test branch
        print(f"\n2. Creating branch '{BRANCH}'...")
        ok = await create_branch(client, REPO, BRANCH, base_sha)
        print(f"  {PASS} Branch ready" if ok else f"  {FAIL} Branch creation failed")
        if not ok: return

        # 3. Push files
        print("\n3. Pushing student submission files...")
        files = [
            ("week-1/analysis.py",      ANALYSIS_PY,      "feat: add data analysis script"),
            ("week-1/data_cleaning.py", DATA_CLEANING_PY, "feat: add data cleaning pipeline"),
            ("PROGRESS.md",             PROGRESS_MD,      "docs: update week 1 progress"),
        ]
        for path, content, msg in files:
            ok = await push_file(client, REPO, BRANCH, path, content, msg)
            status = PASS if ok else FAIL
            print(f"  {status} {path}")

        # 4. Open PR
        print("\n4. Opening Pull Request...")
        pr_title = "Week 1 Submission — Data Analysis & Cleaning"
        pr_body  = """## Week 1 Submission

Hello! This PR contains my Week 1 work for the Data Science internship.

### What I implemented
- `week-1/analysis.py` — Exploratory data analysis with pandas (groupby, correlation, filtering)  
- `week-1/data_cleaning.py` — Reusable data cleaning pipeline with outlier removal & null handling
- `PROGRESS.md` — Updated with tasks completed and learnings

### Libraries used
- `pandas` — DataFrames, groupby, aggregations
- `numpy` — Array operations, random data generation, IQR calculation
- `matplotlib` — (setup for next task)

Please review! 🙏
"""
        pr_num, pr_url = await create_pr(client, REPO, BRANCH, BASE, pr_title, pr_body)
        if not pr_num:
            print(f"  {FAIL} Could not create PR"); return
        print(f"  {PASS} PR #{pr_num} opened: {pr_url}")

        # 5. Poll for CI result
        print(f"\n5. Waiting for GitHub Actions to evaluate... (up to 5 min)")
        print(f"   Watch live: {pr_url}/checks")
        print()

        conclusion, details_url = await poll_workflow(client, REPO, pr_num, timeout=300)

        print()
        print("─"*62)
        if conclusion == "success":
            print(f"  {PASS} EVALUATION PASSED — PR should be auto-merged!")
            print(f"  Details: {details_url}")
        elif conclusion == "failure":
            print(f"  {FAIL} EVALUATION FAILED")
            print(f"  Details: {details_url}")
        elif conclusion == "timeout":
            print(f"  {WAIT} Timed out waiting for CI. Check manually:")
            print(f"  {pr_url}/checks")
        else:
            print(f"  {INFO} Conclusion: {conclusion}")
            if details_url:
                print(f"  Details: {details_url}")
        print("─"*62)
        print(f"\n  PR URL:  {pr_url}")
        print(f"  Checks:  {pr_url}/checks\n")

if __name__ == "__main__":
    asyncio.run(main())
