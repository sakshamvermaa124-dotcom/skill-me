# SkillMe Monitoring System — What Was Built & How to Use It

---

## What Problem This Solves

Before this, if something broke on SkillMe — a certificate email failed to send, a payment got stuck, a button stopped working for students — you'd only find out when a student complained. By then they'd already had a bad experience.

Now the platform checks itself, automatically, around the clock. If something breaks or looks wrong, you get notified before a student notices.

---

## What Was Actually Built

Think of it as three things working together:

### 1. The Health Check Engine (runs in the background, always on)

Every few minutes, the backend runs a series of automated checks on itself:

| How often | What it checks |
|-----------|---------------|
| Every 5 min | Is the server up? Can it reach the database? Is GitHub API working? Is email (Brevo) working? |
| Every 15 min | Can a student apply? Can a certificate be looked up? Is the LOR system reading the right data? Are the payment endpoints responding? |
| Every 30 min | Are there any broken/orphaned records in the database? Are any students stuck at a stage they should have moved past? |
| Every 2 hours | Full end-to-end walkthrough of every major flow |

None of this requires you to do anything. It runs automatically as long as the server is running.

---

### 2. The Monitoring Dashboard (`/monitor`)

A private admin page at **`skill-me-intern.in/monitor`** where you can see everything at a glance.

**What you see on the dashboard:**

- 🟢/🟡/🔴 **Health cards** — one card per check, showing pass/fail and response time
- **Active alerts** — any current problems, sorted by severity (critical first)
- **Stuck students** — students who haven't progressed past a stage in too long
- **Student lookup** — type any student's email to see their complete journey (application → payment → certificate → emails sent)
- **Frontend errors** — JS errors real students hit on their browsers, in real time
- **Check history** — a log of every automated check result
- **Regression detection** — if a check that was passing yesterday is now failing, it's flagged separately

**How to log in:** Enter your admin API key (`sakshamm`) when prompted. The dashboard auto-refreshes every 30 seconds.

---

### 3. Frontend Error Tracking (on every student page)

A small JavaScript snippet is now loaded on every page students visit (quiz, dashboard, certificate, LOR, apply, etc.). It silently captures:

- Any JavaScript crash
- Any API call that fails (e.g. `/api/students/apply` returning an error)
- Any API call that takes longer than 3 seconds

These errors are sent to the monitoring dashboard automatically. You can see them under the **Frontend Errors** tab, including which page the student was on and their email if they were logged in.

---

## What It Found on Day One (Initial Audit)

When the system ran its first scan of your live database, it found:

| Issue | What happened | Status |
|-------|--------------|--------|
| 3 students had certificates but were never emailed | The certificate was created, but the notification email was skipped because of a bug in the download flow | **Fixed + emails sent retroactively** |
| 4 abandoned payment orders (₹636 total) | Students opened the Razorpay payment popup but closed it without paying | No action needed — these expire automatically |
| 2 students enrolled for 13 days with zero progress (ML Batch 1) | SATYAM and SAKSHAM bisht have not completed any tasks | **Manual follow-up recommended** |
| 1 student enrolled 7 days with zero progress | DEBANJAN HATI (Data Science) | **Manual follow-up recommended** |

The bug that caused the missed certificate emails has been permanently fixed. Going forward, it is impossible for a certificate to be recorded in the database without the student getting the email.

---

## The Auto-Check After Every Deployment

Every time you push code to GitHub and Render deploys it, the system now automatically:

1. Waits 3 minutes for Render to finish deploying
2. Checks that the server is healthy
3. Runs all monitoring checks immediately

You don't have to click anything. You can watch it happen in the **Actions** tab of your GitHub repository.

**One setup step required before this works:**

Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret** and add:

```
Name:   SKILLME_ADMIN_KEY
Value:  sakshamm
```

Without this, the GitHub Action can't authenticate to call the trigger endpoint.

---

## How to Use the Dashboard Day-to-Day

**Normal routine (takes 30 seconds):**
1. Open `skill-me-intern.in/monitor`
2. Enter your admin key
3. Check the health cards — all green = everything is fine
4. Check the active alerts count — if it's 0, nothing needs attention
5. Done

**When something goes wrong:**
- The dashboard will show a red health card or a critical alert
- Click into the alert to see exactly what failed and which code file is involved
- Use **Student Lookup** to investigate a specific student's journey end-to-end

**After any code change / deployment:**
- The GitHub Action handles running checks automatically
- Or you can click **"Run All Checks"** on the dashboard manually to get immediate results

**Resolving alerts:**
- Once you've investigated and fixed an issue, click **Resolve** next to the alert
- The alert disappears from the active list

---

## Files That Were Added or Changed

| File | What it does |
|------|-------------|
| `backend/services/monitor_service.py` | The core brain — all health checks, integrity scans, stuck-student logic |
| `backend/services/monitor_scheduler.py` | Schedules everything to run automatically |
| `backend/routes/monitor.py` | The API that the dashboard talks to |
| `skillme-monitor.js` | The snippet on every student page that captures frontend errors |
| `monitor.html` | The monitoring dashboard itself |
| `.github/workflows/post-deploy-monitor.yml` | The GitHub Action that triggers checks after each deploy |
| `backend/services/certificate_service.py` | **Fixed** — now always sends email when a certificate is first issued |
| `backend/db/schema.sql` | Added 3 new tables for storing alerts, check results, and frontend errors |

---

## What You Don't Need to Do

- **No monitoring service to manage** — it's embedded in the existing FastAPI server
- **No external paid service required** — everything runs inside Render
- **No manual triggering** — checks run on schedule and after every deploy automatically
- **No database changes to apply manually** — tables are created automatically when the server starts

The only thing that requires your action is adding the GitHub secret above.
