# LinkedIn autoposter

This is a single-file scheduler for **authorized LinkedIn post publishing**.
It uses LinkedIn's official API and deliberately does not automate connection
requests, DMs, likes, comments, or profile data collection.

## One-time setup

1. Create a LinkedIn developer app at <https://www.linkedin.com/developers/>.
2. In its Products tab, add **Share on LinkedIn** so the app can request
   `w_member_social`. Also enable **Sign In with LinkedIn using OpenID
   Connect**; the script uses it only to identify the profile that authorized
   publishing.
3. In the app's Auth settings, add the exact redirect URL
   `http://localhost:8765/callback`. If LinkedIn requires a different local
   callback URL for your app, use that same URL in both locations.
4. Copy `.linkedin.env.example` to `.linkedin.env` and enter the app's client
   ID and client secret. Do not commit this file.
5. Run the following commands from the repository root:

   ```powershell
   python tools/linkedin_autoposter.py authorize
   python tools/linkedin_autoposter.py seed
   python tools/linkedin_autoposter.py run
   ```

`authorize` opens LinkedIn once for you to grant posting permission.
`seed` reads the curated content library in `linkedin_curated_posts.json` and
creates 15 days of two SkillMe posts per day. Edit the curated library to
replace/add the source posts, or edit `linkedin_posts.json` to alter the
generated wording or timing. `run` stays alive and publishes each due post
automatically in Asia/Kolkata time.

Use `python tools/linkedin_autoposter.py dry-run` to see which due posts would
publish without posting, or `once` if a scheduled task will invoke it every
minute.

The LinkedIn token and post history stay on your machine and are ignored by
git. LinkedIn access tokens are time-limited, so rerun `authorize` if the API
reports an expired or revoked token.
