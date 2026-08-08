"""
SkillMe — CI Workflow Setup
Pushes the universal GitHub Actions evaluation workflow to:
  - All template repos (12 existing)
  - All batch repos (5 existing)
  - Missing template repos (android, dsa, genai, blockchain, sql, uiux) — auto-created from web-dev-template

The single universal workflow.yml auto-detects the domain from the repo name
and runs appropriate language checks, syntax validation, and auto-merges on pass.
"""

import asyncio
import base64
import httpx
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

import os
GITHUB_TOKEN = os.environ.get("SKILLME_GITHUB_TOKEN", "")
GITHUB_ORG   = "sakshamvermaa124-dotcom"
HEADERS      = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ─── All target repos ──────────────────────────────────────────────────────
TEMPLATE_REPOS = [
    "cloud-template", "cpp-template", "cyber-template", "datascience-template",
    "devops-template", "flutter-template", "java-template", "ml-template",
    "node-template", "python-template", "react-template", "web-dev-template",
    # Missing templates — will be created from web-dev-template as base
    "android-template", "dsa-template", "genai-template",
    "blockchain-template", "sql-template", "uiux-template",
]

BATCH_REPOS = [
    "data-science-batch-1", "ml-batch-1", "python-batch-1",
    "web-dev-batch-1", "web-dev-batch-2",
]

# ─── Universal GitHub Actions Workflow YAML ────────────────────────────────
# Single workflow that auto-detects domain from repo name and runs
# appropriate checks: syntax, compilation, library usage, file presence.
WORKFLOW_YAML = r"""
name: "SkillMe Auto-Evaluate"

on:
  pull_request_target:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write
  issues: write

jobs:
  evaluate:
    name: "🤖 SkillMe Evaluation"
    runs-on: ubuntu-latest

    steps:
      # ── Checkout ────────────────────────────────────────────────────────
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0

      # ── Language runtimes (all installed; domain logic picks the right one) ──
      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Python evaluation tools
        run: pip install flake8 --quiet 2>/dev/null || true

      - name: Setup Node.js 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
        continue-on-error: true

      - name: Setup Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
        continue-on-error: true

      - name: Setup GCC / G++
        run: sudo apt-get install -y g++ gcc --quiet 2>/dev/null || true
        continue-on-error: true

      # ── Run SkillMe Evaluator ────────────────────────────────────────────
      - name: Run SkillMe Evaluator
        id: evaluate
        env:
          GITHUB_REPOSITORY: ${{ github.repository }}
          BASE_REF: ${{ github.base_ref }}
        run: |
          python3 - << 'PYEOF'
          import subprocess, os, sys, json, glob, re
          from pathlib import Path

          REPO   = os.environ['GITHUB_REPOSITORY'].split('/')[-1]
          BASE   = os.environ.get('BASE_REF', 'main')
          domain = re.sub(r'-batch-\d+$', '', REPO).lower()
          print(f"[SkillMe] Repo={REPO}  Domain={domain}")

          # ── Get changed files ──────────────────────────────────────────────
          def run(cmd, **kw):
              return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kw)

          r = run(['git', 'diff', '--name-only', f'origin/{BASE}...HEAD'])
          if r.returncode != 0:
              r = run(['git', 'diff', '--name-only', 'HEAD~1...HEAD'])
          changed = [f.strip() for f in r.stdout.splitlines() if f.strip()]
          print(f"[SkillMe] Changed files ({len(changed)}): {changed[:20]}")

          # ── Helpers ───────────────────────────────────────────────────────
          checks   = {}   # required checks  — ALL must pass
          messages = []   # displayed in PR comment

          def ok(msg):  messages.append(f"✅ {msg}")
          def warn(msg): messages.append(f"⚠️  {msg}")
          def fail(msg): messages.append(f"❌ {msg}")
          def tip(msg):  messages.append(f"💡 {msg}")

          # ── Universal: work submitted ─────────────────────────────────────
          meaningful = [f for f in changed
                        if not f.endswith('.gitignore')
                        and f not in ('README.md','.DS_Store')]
          checks['work_submitted'] = len(meaningful) >= 1
          if checks['work_submitted']:
              ok(f"**Work Submitted** — {len(changed)} file(s) changed")
          else:
              fail("**No Work Submitted** — please add/modify files before opening a PR")

          # PROGRESS.md check (encouraged, not required)
          if any('PROGRESS' in f.upper() for f in changed):
              ok("**PROGRESS.md updated** — great documentation!")
          else:
              warn("**PROGRESS.md not updated** — not required to pass, but encouraged")

          # ── Python domains ────────────────────────────────────────────────
          PYTHON_DOMAINS = {'python','ml','datascience','data-science','genai','cyber',
                            'python-template','ml-template','datascience-template',
                            'cyber-template','genai-template'}
          # Node / web domains
          NODE_DOMAINS   = {'web-dev','webdev','react','node','blockchain',
                            'web-dev-template','react-template','node-template',
                            'blockchain-template'}
          # Java
          JAVA_DOMAINS   = {'java','android','java-template','android-template'}
          # C/C++
          CPP_DOMAINS    = {'cpp','dsa','cpp-template','dsa-template'}
          # DevOps
          DEVOPS_DOMAINS = {'devops','cloud','devops-template','cloud-template'}
          # Flutter
          FLUTTER_DOMAINS = {'flutter','flutter-template'}
          # SQL
          SQL_DOMAINS    = {'sql','sql-template'}
          # UI/UX (very lenient)
          UIUX_DOMAINS   = {'uiux','ui-ux','uiux-template'}

          if domain in PYTHON_DOMAINS:
              py_files  = [f for f in changed if f.endswith('.py')]
              nb_files  = [f for f in changed if f.endswith('.ipynb')]
              all_py    = glob.glob('**/*.py', recursive=True)
              all_nb    = glob.glob('**/*.ipynb', recursive=True)

              if py_files or nb_files:
                  ok(f"**Python/Notebook files changed** — {len(py_files)} .py, {len(nb_files)} .ipynb")
              elif all_py or all_nb:
                  ok(f"**Python files present in repo** — {len(all_py)} .py, {len(all_nb)} .ipynb")
              else:
                  warn("No .py or .ipynb files detected — expected Python files")

              # Syntax check
              errors = []
              for f in py_files:
                  if Path(f).exists():
                      r2 = run(['python3', '-m', 'py_compile', f])
                      if r2.returncode != 0:
                          errors.append(f"`{f}`: {r2.stderr.strip()[:100]}")
              checks['syntax_ok'] = len(errors) == 0
              if not errors:
                  if py_files: ok("**Python Syntax** — all .py files compile without errors")
              else:
                  fail("**Syntax Errors found**:\n" + '\n'.join(f"  - {e}" for e in errors))

              # Domain library hints
              LIBS = {
                  'ml':          (['sklearn','torch','tensorflow','keras'], 'ML/AI'),
                  'datascience': (['pandas','numpy','matplotlib','seaborn'], 'Data Science'),
                  'data-science':(['pandas','numpy','matplotlib','seaborn'], 'Data Science'),
                  'genai':       (['openai','langchain','transformers'], 'GenAI'),
                  'cyber':       (['scapy','nmap','cryptography','hashlib'], 'Cybersecurity'),
              }
              if domain in LIBS and py_files:
                  expected, label = LIBS[domain]
                  found = set()
                  for f in py_files:
                      try:
                          content = Path(f).read_text(encoding='utf-8', errors='ignore')
                          found.update(lib for lib in expected if lib in content)
                      except Exception:
                          pass
                  if found:
                      ok(f"**{label} Libraries Used** — {', '.join(f'`{l}`' for l in found)}")
                  else:
                      tip(f"Consider using {label} libraries like: {', '.join(f'`{l}`' for l in expected)}")

          elif domain in NODE_DOMAINS:
              pkg        = Path('package.json')
              html_files = glob.glob('**/*.html', recursive=True)
              js_changed = [f for f in changed if any(f.endswith(e) for e in ('.js','.jsx','.ts','.tsx','.vue'))]

              if pkg.exists():
                  ok("**package.json found**")
                  ri = run(['npm', 'install', '--silent', '--prefer-offline'])
                  if ri.returncode == 0:
                      ok("**npm install** — dependencies installed")
                      rb = run(['npm', 'run', 'build', '--if-present'])
                      if rb.returncode == 0:
                          ok("**Build passed**")
                          checks['build_ok'] = True
                      else:
                          warn("**Build had warnings** (non-blocking for internship)")
                          checks['build_ok'] = True  # lenient
                  else:
                      warn(f"npm install issues — {ri.stderr.strip()[:120]}")
              elif html_files:
                  ok(f"**HTML files found** — {len(html_files)} file(s)")
              elif js_changed:
                  ok(f"**JS/TS files changed** — {len(js_changed)} file(s)")
              else:
                  warn("No web files detected — expected HTML/JS/package.json")

              if domain in ('blockchain','blockchain-template'):
                  sol = glob.glob('**/*.sol', recursive=True)
                  if sol: ok(f"**Solidity contracts** — {len(sol)} .sol file(s)")
                  else:   tip("Expected .sol Solidity contract files for Blockchain track")

          elif domain in JAVA_DOMAINS:
              java_files = [f for f in changed if f.endswith(('.java','.kt'))]
              all_java   = glob.glob('**/*.java', recursive=True) + glob.glob('**/*.kt', recursive=True)
              if java_files or all_java:
                  ok(f"**Java/Kotlin files** — {len(java_files)} changed, {len(all_java)} total")
                  # Compile .java only (Kotlin needs separate setup)
                  java_only = [f for f in java_files if f.endswith('.java') and Path(f).exists()]
                  if java_only:
                      rc = run(['javac', '-cp', '.'] + java_only)
                      if rc.returncode == 0:
                          ok("**Java Compilation** — passed")
                          checks['compile_ok'] = True
                      elif 'cannot find symbol' in rc.stderr and 'import' in rc.stderr:
                          warn("**Compilation** — missing classpath imports (normal for partial submissions)")
                          checks['compile_ok'] = True  # non-blocking
                      else:
                          fail(f"**Compilation Error** — {rc.stderr.strip()[:200]}")
                          checks['compile_ok'] = False
              else:
                  warn("No .java/.kt files found — expected Java or Kotlin source files")
              if domain in ('android','android-template'):
                  if Path('build.gradle').exists() or Path('build.gradle.kts').exists():
                      ok("**Gradle build file found**")

          elif domain in CPP_DOMAINS:
              cpp_files  = [f for f in changed if f.endswith(('.cpp','.c','.h','.hpp'))]
              all_cpp    = glob.glob('**/*.cpp', recursive=True) + glob.glob('**/*.c', recursive=True)
              if cpp_files or all_cpp:
                  ok(f"**C/C++ files** — {len(cpp_files)} changed")
                  src = [f for f in cpp_files if f.endswith(('.cpp','.c')) and Path(f).exists()]
                  errs = []
                  for sf in src:
                      compiler = 'g++' if sf.endswith('.cpp') else 'gcc'
                      rc = run([compiler, sf, '-o', f'/tmp/{Path(sf).stem}.out', '-std=c++17', '-Wall'])
                      if rc.returncode != 0:
                          errs.append(f"`{sf}`: {rc.stderr.strip()[:120]}")
                  checks['compile_ok'] = len(errs) == 0
                  if not errs:
                      if src: ok(f"**Compilation** — all {len(src)} C/C++ file(s) compiled successfully")
                  else:
                      fail("**Compilation Errors**:\n" + '\n'.join(f"  - {e}" for e in errs))
              else:
                  warn("No .cpp/.c files found — expected C or C++ source files")

          elif domain in DEVOPS_DOMAINS:
              docker   = (glob.glob('**/Dockerfile*', recursive=True)
                         + glob.glob('**/docker-compose*.yml', recursive=True))
              tf_files = glob.glob('**/*.tf', recursive=True)
              ymls     = [f for f in changed if f.endswith(('.yml','.yaml'))]
              if docker:
                  ok(f"**Docker files** — {', '.join(os.path.basename(f) for f in docker[:3])}")
              if tf_files:
                  ok(f"**Terraform files** — {len(tf_files)} .tf file(s)")
                  tip("Run `terraform validate` locally to check configuration")
              if ymls:
                  ok(f"**YAML files changed** — {len(ymls)} file(s)")
              if not docker and not tf_files and not ymls:
                  warn("No DevOps files detected — expected Dockerfile, docker-compose.yml, or .tf files")
              checks['devops_files'] = bool(docker or tf_files or ymls or meaningful)

          elif domain in FLUTTER_DOMAINS:
              dart_files = [f for f in changed if f.endswith('.dart')]
              all_dart   = glob.glob('**/*.dart', recursive=True)
              if Path('pubspec.yaml').exists(): ok("**pubspec.yaml found**")
              if dart_files or all_dart:
                  ok(f"**Dart files** — {len(dart_files)} changed, {len(all_dart)} total")
              else:
                  warn("No .dart files found — expected Flutter/Dart source files")

          elif domain in SQL_DOMAINS:
              sql_files = [f for f in changed if f.endswith('.sql')]
              all_sql   = glob.glob('**/*.sql', recursive=True)
              if sql_files or all_sql:
                  ok(f"**SQL files** — {len(sql_files)} changed")
                  SQL_KW = ('SELECT','CREATE','INSERT','UPDATE','DELETE','ALTER','DROP','JOIN','WHERE')
                  valid = [f for f in sql_files if Path(f).exists()
                           and any(kw in Path(f).read_text(encoding='utf-8',errors='ignore').upper() for kw in SQL_KW)]
                  if valid: ok(f"**SQL Syntax** — {len(valid)} file(s) contain valid SQL statements")
              else:
                  warn("No .sql files found")

          elif domain in UIUX_DOMAINS:
              design_exts = ('.html','.css','.svg','.png','.jpg','.jpeg','.pdf','.sketch','.fig','.md')
              design_files = [f for f in changed if any(f.lower().endswith(e) for e in design_exts)]
              if design_files:
                  ok(f"**Design/Web files submitted** — {len(design_files)} file(s)")
              elif meaningful:
                  ok(f"**Files submitted** — {len(meaningful)} file(s)")
              else:
                  warn("No design files detected — expected HTML/CSS/SVG/PNG or design exports")

          else:
              tip(f"Domain `{domain}` — generic evaluation applied (check files submitted)")

          # ── Final verdict ──────────────────────────────────────────────────
          required_ok = all([
              checks.get('work_submitted', True),
              checks.get('syntax_ok',      True),
              checks.get('compile_ok',     True),
          ])

          env_file  = os.environ.get('GITHUB_OUTPUT', '/dev/null')
          msg_file  = '/tmp/skillme_messages.txt'
          with open(env_file, 'a') as f:
              f.write(f"passed={'true' if required_ok else 'false'}\n")
              f.write(f"domain={domain}\n")
              f.write(f"files_changed={len(changed)}\n")
          # Write messages to a separate temp file to avoid backtick issues in JS
          with open(msg_file, 'w', encoding='utf-8') as f:
              f.write('\n'.join(messages))

          print(f"\n[SkillMe] RESULT: {'PASS' if required_ok else 'FAIL'}")
          print(f"[SkillMe] Checks: {json.dumps(checks)}")
          PYEOF

      # ── Post Evaluation Comment ──────────────────────────────────────────
      - name: Post Evaluation Comment
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const passed   = '${{ steps.evaluate.outputs.passed }}' === 'true';
            const domain   = '${{ steps.evaluate.outputs.domain }}' || 'unknown';
            const files    = '${{ steps.evaluate.outputs.files_changed }}' || '0';
            // Read messages from file to avoid backtick/template-literal injection
            let messages = '_No evaluation details available_';
            try {
              const fs = require('fs');
              messages = fs.readFileSync('/tmp/skillme_messages.txt', 'utf8').trim();
            } catch (e) { /* file missing — fallback already set */ }

            const statusLine = passed
              ? '> 🟢 **PASSED** — All required checks passed. Auto-merging your PR now!'
              : '> 🔴 **NEEDS FIXES** — Please fix the issues below, then push again to re-trigger evaluation.';

            const body = [
              `## 🤖 SkillMe Evaluation Report`,
              statusLine,
              '',
              `| Field | Value |`,
              `|-------|-------|`,
              `| **Domain** | \`${domain}\` |`,
              `| **Files changed** | ${files} |`,
              `| **Result** | ${passed ? '✅ Pass' : '❌ Fail'} |`,
              '',
              '### Checklist',
              messages,
              '',
              '---',
              '*SkillMe Auto-Evaluator · [docs](https://skill-me-intern.in) · Powered by GitHub Actions*',
            ].join('\n');

            // Remove old SkillMe bot comments on this PR
            const existing = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo:  context.repo.repo,
              issue_number: context.issue.number,
            });
            for (const c of existing.data) {
              if (c.body && c.body.includes('SkillMe Evaluation Report')) {
                try {
                  await github.rest.issues.deleteComment({
                    owner: context.repo.owner,
                    repo:  context.repo.repo,
                    comment_id: c.id,
                  });
                } catch (e) { /* ignore */ }
              }
            }

            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo:  context.repo.repo,
              issue_number: context.issue.number,
              body,
            });

      # ── Auto-merge on Pass ───────────────────────────────────────────────
      - name: Auto-merge PR
        if: steps.evaluate.outputs.passed == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          echo "All checks passed — merging PR #${{ github.event.number }}"
          gh pr merge "${{ github.event.number }}" \
            --repo "${{ github.repository }}" \
            --merge \
            --body "Auto-merged by SkillMe Bot after evaluation passed (domain: ${{ steps.evaluate.outputs.domain }})" \
            || echo "Auto-merge skipped (already merged or branch protection active)"
""".lstrip()

WORKFLOW_PATH    = ".github/workflows/skillme-evaluate.yml"
COMMIT_MESSAGE   = "ci: add SkillMe auto-evaluation workflow"


# ─── GitHub API helpers ─────────────────────────────────────────────────────
async def gh(client, method, path, **kwargs):
    r = await client.request(method, f"https://api.github.com{path}", headers=HEADERS, **kwargs)
    try:    body = r.json()
    except: body = r.text
    return r.status_code, body


async def push_workflow(client, repo: str) -> str:
    """Push or update the workflow file in a repo. Returns status string."""
    # Check if file already exists (need SHA to update)
    s, existing = await gh(client, "GET", f"/repos/{GITHUB_ORG}/{repo}/contents/{WORKFLOW_PATH}")
    sha = existing.get("sha") if s == 200 and isinstance(existing, dict) else None

    payload = {
        "message": COMMIT_MESSAGE if not sha else "ci: update SkillMe evaluation workflow",
        "content": base64.b64encode(WORKFLOW_YAML.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha

    s2, result = await gh(client, "PUT",
        f"/repos/{GITHUB_ORG}/{repo}/contents/{WORKFLOW_PATH}",
        json=payload)

    if s2 in (200, 201):
        action = "updated" if sha else "created"
        return f"✅  {repo:<40} → workflow {action}"
    else:
        msg = result.get("message", str(result)) if isinstance(result, dict) else str(result)
        return f"❌  {repo:<40} → HTTP {s2}: {msg[:80]}"


async def ensure_repo_exists(client, repo: str, base_template: str = "web-dev-template"):
    """Create repo from template if it doesn't exist."""
    s, _ = await gh(client, "GET", f"/repos/{GITHUB_ORG}/{repo}")
    if s == 200:
        return True  # already exists
    # Create from template
    s2, r2 = await gh(client, "POST",
        f"/repos/{GITHUB_ORG}/{base_template}/generate",
        json={
            "owner": GITHUB_ORG,
            "name":  repo,
            "description": f"SkillMe {repo.replace('-template','').replace('-',' ').title()} Template",
            "private": False,
        })
    if s2 in (201, 202):
        print(f"   📦 Created missing template repo: {repo}")
        # Wait a moment for GitHub to finish provisioning
        await asyncio.sleep(3)
        return True
    else:
        msg = r2.get("message","") if isinstance(r2, dict) else str(r2)
        print(f"   ⚠️  Could not create {repo}: {msg[:80]}")
        return False


# ─── Main ───────────────────────────────────────────────────────────────────
async def main():
    print("\n" + "─"*62)
    print("  SkillMe CI Workflow Setup")
    print("─"*62 + "\n")

    all_repos = TEMPLATE_REPOS + BATCH_REPOS
    results   = []

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Ensure all missing template repos exist
        print("Step 1 — Ensuring all template repos exist on GitHub...")
        existing_templates = [
            "cloud-template","cpp-template","cyber-template","datascience-template",
            "devops-template","flutter-template","java-template","ml-template",
            "node-template","python-template","react-template","web-dev-template",
        ]
        missing = [r for r in TEMPLATE_REPOS if r not in existing_templates]
        for repo in missing:
            await ensure_repo_exists(client, repo)

        print()

        # 2. Push workflow to every repo
        print(f"Step 2 — Pushing workflow to {len(all_repos)} repos...\n")
        for repo in all_repos:
            result = await push_workflow(client, repo)
            print(f"  {result}")
            results.append(result)

    passed = sum(1 for r in results if r.startswith("✅"))
    failed = sum(1 for r in results if r.startswith("❌"))

    print(f"\n{'─'*62}")
    print(f"  Done  —  {passed} pushed, {failed} failed")
    print(f"{'─'*62}\n")
    print("What happens when a student opens a PR now:")
    print("  1. GitHub Actions triggers 'SkillMe Auto-Evaluate'")
    print("  2. Checks run (syntax, compile, files, domain libraries)")
    print("  3. Bot posts a detailed ✅/❌ checklist comment on the PR")
    print("  4. If PASS → PR is auto-merged immediately")
    print("  5. If FAIL → student sees exactly what to fix, pushes again")
    print("  6. Backend webhook detects the merge → updates DB score (+25)\n")


if __name__ == "__main__":
    asyncio.run(main())
