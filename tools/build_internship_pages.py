"""
Build one landing page per internship track, plus the /internships hub, from the real curriculum.

    python tools/build_internship_pages.py          # (re)write everything
    python tools/build_internship_pages.py --check  # exit 1 if anything is out of date

Source of truth: backend/services/curriculum.json (the same file the student dashboard reads), so a
page can never describe milestones the programme does not have. Re-run after editing the curriculum,
theme.css, internship.css or the TRACKS table below.

Writes:
    internships/index.html            hub listing every track
    internships/<slug>.html           one page per track  ->  /internships/<slug> (vercel cleanUrls)
and refreshes the generated blocks (between BEGIN/END markers) in:
    index.html      the internship cards in the homepage grid
    sitemap.xml     one <url> per page
    llms.txt        link list for AI answer engines
    llms-full.txt   per-track detail for AI answer engines
"""
import hashlib
import html
import json
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://www.skill-me-intern.in'
OUT_DIR = os.path.join(ROOT, 'internships')
CURRICULUM = os.path.join(ROOT, 'backend', 'services', 'curriculum.json')

STIPEND = 'up to $100 a month'
REVIEWERS = 'Walmart, Google and LinkedIn'

# quiz key (the ?domain= value the homepage cards use), curriculum key, card label, keyword noun
# used in titles/headings, URL slug, tech stack line.
TRACKS = [
    ('webdev', 'web-dev', 'Full Stack Engineer', 'Full Stack Web Development', 'full-stack-web-development', 'HTML5 · CSS3 · JavaScript'),
    ('python', 'python', 'Python Engineering', 'Python', 'python', 'Python 3 · OOP · APIs'),
    ('react', 'react', 'Frontend Engineer', 'React Frontend', 'react-frontend', 'React 18 · Next.js · TypeScript'),
    ('node', 'node', 'Backend Engineer', 'Node.js Backend', 'nodejs-backend', 'Node · Express · REST APIs'),
    ('ai-engineer', 'ai-engineer', 'AI Engineer', 'AI Engineer', 'ai-engineer', 'LLM APIs · RAG · Agents'),
    ('genai', 'genai', 'Generative AI', 'Generative AI', 'generative-ai', 'LLM APIs · Prompting · RAG'),
    ('ml', 'ml', 'Machine Learning', 'Machine Learning', 'machine-learning', 'PyTorch · Scikit-Learn · Pandas'),
    ('datascience', 'data-science', 'Data Science', 'Data Science', 'data-science', 'Python · SQL · Data Viz'),
    ('sde', 'sde', 'SDE / SWE', 'Software Engineering (SDE)', 'software-engineering', 'Data Structures · System Design · Testing'),
    ('java', 'java', 'Java / Spring Boot', 'Java Spring Boot', 'java-spring-boot', 'Java 17 · Spring Boot · Maven'),
    ('cpp', 'cpp', 'C++ / Algorithms', 'C++ and DSA', 'cpp-dsa', 'C++20 · DSA · Problem Solving'),
    ('devops', 'devops', 'DevOps / CI-CD', 'DevOps', 'devops', 'Docker · GitHub Actions · CI/CD'),
    ('cloud', 'cloud', 'Cloud / AWS', 'Cloud and AWS', 'cloud-aws', 'AWS · Serverless · Storage'),
    ('flutter', 'flutter', 'App Developer', 'Flutter App Development', 'flutter-app-development', 'Dart · Flutter · Cross-Platform'),
    ('cyber', 'cyber', 'Cybersecurity', 'Cybersecurity', 'cybersecurity', 'Web Security · Python · OWASP'),
    ('sql', 'sql', 'SQL / Databases', 'SQL and Databases', 'sql-databases', 'SQL · PostgreSQL · Data Modeling'),
    ('uiux', 'uiux', 'UI/UX Design', 'UI/UX Design', 'ui-ux-design', 'Figma · Research · Prototyping'),
    ('ai-pm', 'ai-pm', 'AI Product Management', 'AI Product Management', 'ai-product-management', 'PRDs · AI Evals · Roadmapping'),
    ('fde', 'fde', 'Forward Deployed Engineer', 'Forward Deployed Engineer', 'forward-deployed-engineer', 'API Integration · Client Tools · Docs'),
    ('qa', 'qa', 'Software Quality', 'Software Testing and QA', 'software-testing-qa', 'Test Automation · Selenium · Bug Reports'),
]

# Homepage filter category for each track (quiz key -> category id used by the filter chips).
CATEGORY = {
    'webdev': 'fullstack', 'react': 'fullstack', 'node': 'fullstack', 'uiux': 'fullstack',
    'python': 'ai', 'ai-engineer': 'ai', 'genai': 'ai', 'ml': 'ai', 'datascience': 'ai', 'ai-pm': 'ai',
    'cloud': 'mobile', 'flutter': 'mobile',
}
CATEGORY_LABEL = {'fullstack': 'Web & design', 'ai': 'AI, data & Python', 'systems': 'Systems & core', 'mobile': 'Mobile & cloud'}


# ── helpers ──────────────────────────────────────────────────────────────────

def esc(text):
    return html.escape(str(text), quote=True)


def plain(md):
    """Markdown inline -> plain text (for meta tags, JSON-LD and the llms files)."""
    md = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', md)
    md = md.replace('**', '').replace('`', '')
    return re.sub(r'\s+', ' ', md).strip()


def inline(md):
    """Markdown inline -> safe HTML (code, bold; links become their text)."""
    md = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', md)
    out = esc(md)
    out = re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    out = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', out)
    return out


def section(desc, heading_word):
    """Body of the '### <emoji> <heading>' section of a week description."""
    m = re.search(r'^###[^\n]*' + re.escape(heading_word) + r'[^\n]*\n(.*?)(?=^###|\Z)', desc, re.S | re.M)
    return m.group(1).strip() if m else ''


def week_goal(desc):
    body = section(desc, "This Week's Goal")
    body = body.split('**Level:**')[0]
    body = re.sub(r'This week builds on your Week \d work[^\n.]*\.', '', body)
    return re.sub(r'\s+', ' ', body).strip()


def week_learn(desc):
    return [ln[2:].strip() for ln in section(desc, "What You'll Learn").splitlines() if ln.startswith('- ')]


def asset(name):
    with open(os.path.join(ROOT, name), 'rb') as f:
        return f'/{name}?v={hashlib.sha256(f.read()).hexdigest()[:10]}'


def jsonld(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2).replace('</', '<\\/')


def url_for(slug=None):
    return f'{SITE}/internships' + (f'/{slug}' if slug else '')


# ── shared page chrome ───────────────────────────────────────────────────────

THEME_BOOT = """  <script>
    (function () {
      var t;
      try { t = localStorage.getItem('skillme-theme'); } catch (e) {}
      if (t !== 'light' && t !== 'dark') { t = 'light'; }
      document.documentElement.setAttribute('data-theme', t);
      document.documentElement.classList.remove('no-js');
      var tc = document.querySelector('meta[name="theme-color"]');
      if (tc) tc.setAttribute('content', t === 'dark' ? '#09090a' : '#ffffff');
    })();
  </script>"""

ARROW = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>'


def head(title, description, canonical, graph):
    return f"""<!DOCTYPE html>
<!-- Generated by tools/build_internship_pages.py from backend/services/curriculum.json. Do not edit by hand. -->
<html lang="en" data-theme="light" class="no-js">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">

  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <meta name="author" content="SkillMe">
  <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
  <meta name="theme-color" content="#ffffff">
  <link rel="canonical" href="{canonical}">

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="SkillMe">
  <meta property="og:url" content="{canonical}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:image" content="{SITE}/assets/og-image.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:domain" content="skill-me-intern.in">
  <meta name="twitter:title" content="{esc(title)}">
  <meta name="twitter:description" content="{esc(description)}">
  <meta name="twitter:image" content="{SITE}/assets/og-image.png">

  <link rel="icon" href="/favicon.ico" sizes="48x48">
  <link rel="icon" href="/assets/favicon-48.png" type="image/png" sizes="48x48">
  <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
  <link rel="manifest" href="/site.webmanifest">

{THEME_BOOT}

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@300..800&family=Geist+Mono:wght@400..600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{asset('theme.css')}">
  <link rel="stylesheet" href="{asset('internship.css')}">
  <script src="{asset('theme.js')}" defer></script>
  <script src="{asset('config.js')}" defer></script>
  <script src="{asset('attribution.js')}" defer></script>

  <script type="application/ld+json">
{jsonld({'@context': 'https://schema.org', '@graph': graph})}
  </script>
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="site-nav" id="site-nav">
    <div class="container">
      <a href="/" class="brand" aria-label="SkillMe home">
        <img src="/assets/logo-96.webp" alt="" width="32" height="32">
        <span>SkillMe</span>
      </a>
      <nav class="nav-links" aria-label="Primary">
        <a href="/#how-it-works">How it works</a>
        <a href="/internships">Internships</a>
        <a href="/#faq">FAQ</a>
        <a href="/verify">Verify</a>
      </nav>
      <div class="nav-actions">
        <button type="button" class="theme-toggle" data-theme-toggle aria-label="Toggle theme">
          <svg class="ti-sun" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
          <svg class="ti-moon" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
        </button>
        <a href="/dashboard" class="btn btn-ghost btn-sm nav-hide-sm">Log in</a>
        <a href="/internships" class="btn btn-primary btn-sm nav-hide-sm">Apply now</a>
        <button type="button" class="nav-menu-btn" data-nav-toggle aria-label="Open menu">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
        </button>
      </div>
    </div>
  </header>
  <div class="nav-drawer" id="nav-drawer">
    <a href="/#how-it-works">How it works</a>
    <a href="/internships">Internships</a>
    <a href="/#faq">FAQ</a>
    <a href="/verify">Verify a certificate</a>
    <a href="/dashboard">Student login</a>
    <a href="/internships" class="btn btn-primary">Apply now</a>
  </div>
"""


FOOTER = """
  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div>
          <a href="/" class="brand"><img src="/assets/logo-96.webp" alt="" width="32" height="32"><span>SkillMe</span></a>
          <p class="footer-about">Remote internships with real weekly milestones, human review, verifiable credentials and a stipend of up to $100 a month for top performers.</p>
        </div>
        <div class="footer-col">
          <h4>Program</h4>
          <a href="/#how-it-works">How it works</a>
          <a href="/internships">All internships</a>
          <a href="/internships">Apply now</a>
          <a href="/#faq">FAQ</a>
        </div>
        <div class="footer-col">
          <h4>Students</h4>
          <a href="/dashboard">Student dashboard</a>
          <a href="/verify">Verify a certificate</a>
          <a href="https://www.linkedin.com/company/skill-me-intern/" target="_blank" rel="noopener noreferrer">LinkedIn</a>
          <a href="/contact">Contact us</a>
        </div>
        <div class="footer-col">
          <h4>Legal</h4>
          <a href="/privacy">Privacy policy</a>
          <a href="/terms">Terms of service</a>
          <a href="/refunds">Cancellation &amp; refunds</a>
          <a href="/llms.txt">Agent instructions</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© <span data-year>2026</span> SkillMe · MSME registered · UDYAM-UP-50-0294192</span>
        <span>Remote internships for students worldwide</span>
      </div>
    </div>
  </footer>
</body>
</html>
"""

TRUST = """
    <section class="section ip-section" aria-labelledby="trust-title">
      <div class="container">
        <div class="section-head">
          <span class="eyebrow">Is it legit?</span>
          <h2 class="h2" id="trust-title">Check SkillMe yourself before you apply</h2>
        </div>
        <ul class="ip-trust" role="list">
          <li><strong>A registered business.</strong> Registered with the Ministry of MSME, Government of India. Udyam number <span class="mono">UDYAM-UP-50-0294192</span>. <a href="/contact">Business details</a></li>
          <li><strong>Certificates anyone can verify.</strong> Each has a unique ID and QR code that a recruiter can check in seconds. <a href="/verify">Verify a certificate</a></li>
          <li><strong>Interns' work is public.</strong> Every milestone is posted on the intern's own LinkedIn, so you can see real work. <a href="https://www.linkedin.com/company/skill-me-intern/" target="_blank" rel="noopener noreferrer">SkillMe on LinkedIn</a></li>
          <li><strong>Honest about what we promise.</strong> Not everyone is selected. The stipend and job offers, from our hiring partners or at SkillMe, go to top performers only. <a href="/terms">Terms of service</a></li>
          <li><strong>Real people you can reach.</strong> Ask us anything before you apply. <a href="mailto:admin@skill-me-intern.in">admin@skill-me-intern.in</a></li>
        </ul>
      </div>
    </section>
"""

ORG = {'@type': 'EducationalOrganization', '@id': f'{SITE}/#organization', 'name': 'SkillMe', 'url': SITE}


def breadcrumbs(*items):
    return {
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': i, 'name': name, 'item': url}
            for i, (name, url) in enumerate(items, 1)
        ],
    }


# ── track page ───────────────────────────────────────────────────────────────

def track_faq(t, projects):
    noun, tech = t['noun'], t['tech']
    first = projects[0]
    hours = first['weeks']['1']['est_hours']
    if len(projects) == 1:
        build = (f"You build {plain(first['project_name'])}. {plain(first['tagline'])} "
                 "It is one project built up over four weekly milestones, so each week adds to the last.")
    else:
        names = ', '.join(plain(p['project_name']) for p in projects[:-1]) + f" or {plain(projects[-1]['project_name'])}"
        build = (f"You are assigned one of {len(projects)} projects: {names}. Each is a single project built up over "
                 "four weekly milestones, so each week adds to the last.")
    return [
        (f'What will I build in the {noun} internship?', build),
        (f'Is the {noun} internship paid? Is there a stipend?',
         f'Top performers earn a stipend of {STIPEND}. The stipend is performance-based and is not paid to every intern: '
         'it goes to the interns whose reviewed work stands out in their cohort.'),
        ('Who reviews my work?',
         f'Every weekly submission is reviewed against that week\'s acceptance criteria by the SkillMe team, which includes '
         f'engineers who work at {REVIEWERS}. Work that misses the bar comes back with notes on what to fix.'),
        (f'Do I need experience to apply for the {noun} internship?',
         f'You need the basics of {tech.replace(" · ", ", ")}, not prior internship experience. Week 1 starts at '
         f'{first["weeks"]["1"]["difficulty"]} level and week 4 reaches {first["weeks"]["4"]["difficulty"]}. '
         'A short screening quiz (8 questions, about 5 minutes) checks you are ready to start.'),
        ('How long is the internship and how much time does it take?',
         f'It runs for 4 weeks with one milestone a week. Each milestone is planned for about {hours} hours, and it is '
         'fully remote, so you work at your own pace around college or a job.'),
        ('Who can apply? Is it open outside India?',
         'Anyone can apply, from any country, college or year, and we encourage you to. Selection is competitive: every '
         'application is read by a person, and shortlisted applicants hear back within 48 hours.'),
        ('What do I get when I finish?',
         'An offer letter when you are selected, a public portfolio page with every approved milestone, and a QR-verified '
         'certificate and Letter of Recommendation once 3 of your 4 milestones are approved. Top performers also earn the '
         'stipend and are referred to hiring partners.'),
    ]


def render_track(t, projects, all_tracks):
    noun, label, slug, tech = t['noun'], t['label'], t['slug'], t['tech']
    canonical = url_for(slug)
    first = projects[0]
    apply_url = f"/quiz?domain={t['quiz']}"
    title = f'{noun} Remote Internship, Stipend for Top Performers | SkillMe'
    description = (f"4-week remote {noun} internship, open worldwide. Top performers earn a stipend of {STIPEND}. "
                   f"Work reviewed by engineers who work at {REVIEWERS}.")
    faq = track_faq(t, projects)

    graph = [
        breadcrumbs(('SkillMe', SITE + '/'), ('Internships', url_for()), (f'{noun} internship', canonical)),
        {
            '@type': 'EducationalOccupationalProgram',
            '@id': canonical + '#program',
            'name': f'SkillMe {noun} Remote Internship',
            'url': canonical,
            'description': description,
            'provider': ORG,
            'timeToComplete': 'P4W',
            'educationalProgramMode': 'online',
            'programType': 'Internship',
            'educationalCredentialAwarded': 'Verified Certificate of Completion and Letter of Recommendation (LOR)',
            'hasCourse': [
                {'@type': 'Course', 'name': f"Week {n}: {plain(first['weeks'][n]['title'])}",
                 'description': plain(week_goal(first['weeks'][n]['description']))[:300],
                 'provider': ORG}
                for n in sorted(first['weeks'])
            ],
        },
        {
            '@type': 'FAQPage',
            '@id': canonical + '#faq',
            'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in faq],
        },
    ]

    p = [head(title, description, canonical, graph)]
    chips = ''.join(f'<li>{esc(x)}</li>' for x in tech.split(' · '))
    if len(projects) == 1:
        summary_build = f"you build <strong>{inline(first['project_name'])}</strong>"
    else:
        summary_build = f"you build one of {len(projects)} projects, such as <strong>{inline(first['project_name'])}</strong>"

    p.append(f"""
  <main id="main">
    <section class="ip-hero">
      <div class="container">
        <nav class="ip-crumbs" aria-label="Breadcrumb"><a href="/">SkillMe</a><span aria-hidden="true">/</span><a href="/internships">Internships</a><span aria-hidden="true">/</span><span aria-current="page">{esc(noun)}</span></nav>
        <span class="eyebrow">Remote internship · 4 weeks · open worldwide</span>
        <h1 class="h1 ip-title">{esc(noun)} remote internship with stipend</h1>
        <p class="lead ip-lead">A 4-week remote {esc(noun)} internship with one reviewed milestone a week. Top performers earn a stipend of {STIPEND}, and your work is reviewed by engineers who work at {REVIEWERS}.</p>
        <ul class="ip-chips" role="list" aria-label="Tech stack">{chips}</ul>
        <div class="ip-actions">
          <a href="{apply_url}" class="btn btn-primary btn-lg">Apply for this internship {ARROW}</a>
          <a href="#weeks" class="btn btn-secondary btn-lg">See the 4 weeks</a>
        </div>
        <ul class="ip-facts" role="list" aria-label="Internship at a glance">
          <li><span class="ip-fact-value mono">4 weeks</span><span class="ip-fact-label">one milestone a week</span></li>
          <li><span class="ip-fact-value mono">{esc(first['weeks']['1']['est_hours'])} hrs</span><span class="ip-fact-label">per weekly milestone</span></li>
          <li><span class="ip-fact-value mono">Remote</span><span class="ip-fact-label">apply from any country</span></li>
          <li><span class="ip-fact-value mono">Up to $100</span><span class="ip-fact-label">a month, for top performers</span></li>
        </ul>
      </div>
    </section>

    <section class="section section-soft ip-section" aria-labelledby="summary-title">
      <div class="container ip-narrow">
        <h2 class="h2" id="summary-title">The {esc(noun)} internship in short</h2>
        <p class="ip-answer">The SkillMe {esc(noun)} internship is a 4-week, fully remote programme open to students worldwide. Over four weekly milestones {summary_build}, post each milestone publicly on LinkedIn, and have it reviewed against clear acceptance criteria. Reviewers include engineers who work at {REVIEWERS}. Top performers earn a stipend of {STIPEND}, and interns who get 3 of 4 milestones approved earn a QR-verified certificate and a Letter of Recommendation.</p>
      </div>
    </section>

    <section class="section ip-section" aria-labelledby="project-title">
      <div class="container">
        <div class="section-head">
          <span class="eyebrow">What you build</span>
          <h2 class="h2" id="project-title">{'One real project, built over four weeks' if len(projects) == 1 else f'One of {len(projects)} real projects, built over four weeks'}</h2>
          <p class="lead">{'Every intern on this track builds the same project, milestone by milestone.' if len(projects) == 1 else 'You are assigned one of these projects when you start, and build it milestone by milestone.'}</p>
        </div>
        <div class="ip-projects">""")
    for proj in projects:
        weeks = ''.join(f"<li><span class=\"mono\">W{n}</span>{inline(proj['weeks'][n]['title'])}</li>" for n in sorted(proj['weeks']))
        p.append(f"""
          <article class="card card-pad ip-project">
            <h3 class="h3">{inline(proj['project_name'])}</h3>
            <p>{inline(proj['tagline'])}</p>
            <ol class="ip-project-weeks" role="list">{weeks}</ol>
          </article>""")
    p.append(f"""
        </div>
      </div>
    </section>

    <section class="section section-soft ip-section" id="weeks" aria-labelledby="weeks-title">
      <div class="container">
        <div class="section-head">
          <span class="eyebrow">Week by week</span>
          <h2 class="h2" id="weeks-title">What each week of the {esc(noun)} internship covers</h2>
          <p class="lead">{'The four milestones of ' if len(projects) == 1 else 'Shown for '}{inline(first['project_name'])}{'.' if len(projects) == 1 else '. The other projects follow the same four-week shape.'}</p>
        </div>
        <ol class="ip-weeks" role="list">""")
    for n in sorted(first['weeks']):
        w = first['weeks'][n]
        learn = ''.join(f'<li>{inline(x)}</li>' for x in week_learn(w['description']))
        deliver = ''.join(f'<li>{inline(x)}</li>' for x in w['deliverables'])
        p.append(f"""
          <li class="card ip-week">
            <div class="ip-week-head">
              <span class="ip-week-num mono">Week {n} of 4</span>
              <h3 class="h3">{inline(w['title'])}</h3>
              <div class="ip-week-meta"><span class="badge">{esc(w['difficulty'])}</span><span class="badge">{esc(w['est_hours'])} hours</span></div>
            </div>
            <p class="ip-week-goal">{inline(week_goal(w['description']))}</p>
            <div class="ip-week-cols">
              <div><h4>What you learn</h4><ul>{learn}</ul></div>
              <div><h4>What you submit</h4><ul>{deliver}</ul></div>
            </div>
          </li>""")
    p.append(f"""
        </ol>
      </div>
    </section>

    <section class="section ip-section" aria-labelledby="get-title">
      <div class="container">
        <div class="section-head">
          <span class="eyebrow">What you get</span>
          <h2 class="h2" id="get-title">What the {esc(noun)} internship gives you</h2>
        </div>
        <div class="ip-benefits">
          <article class="card card-pad"><h3 class="h3">Stipend for top performers</h3><p>Up to $100 a month for the interns whose reviewed work stands out in their cohort. It is earned, not handed out.</p></article>
          <article class="card card-pad"><h3 class="h3">Review by working engineers</h3><p>Engineers who work at {REVIEWERS} review submissions, so submit mindfully. Work that misses the bar comes back with notes.</p></article>
          <article class="card card-pad"><h3 class="h3">Offer letter on day one</h3><p>A proper internship offer letter with your track and joining date, for your resume and college records.</p></article>
          <article class="card card-pad"><h3 class="h3">Certificate recruiters can check</h3><p>A certificate with a unique ID and QR code that anyone can verify, plus a Letter of Recommendation based on your approved work.</p></article>
          <article class="card card-pad"><h3 class="h3">Public proof of work</h3><p>Four public LinkedIn posts and a portfolio page listing every approved milestone, in one link for your resume.</p></article>
          <article class="card card-pad"><h3 class="h3">Referrals for top performers</h3><p>Top interns are referred to openings at startups and product companies in our hiring partner network.</p></article>
        </div>
        <p class="ip-note">Reviewers take part in a personal capacity. Company names belong to their owners and do not imply a partnership or endorsement.</p>
      </div>
    </section>

    <section class="section section-soft ip-section" aria-labelledby="apply-title">
      <div class="container ip-narrow">
        <h2 class="h2" id="apply-title">How to apply</h2>
        <ol class="ip-steps">
          <li><strong>Take the 5-minute quiz.</strong> Eight questions on the basics of {esc(tech.replace(' · ', ', '))}.</li>
          <li><strong>Tell us why you want in.</strong> A person reads every application. Anyone can apply, but selection is competitive.</li>
          <li><strong>Get shortlisted.</strong> If you are selected you hear back within 48 hours and receive your offer letter.</li>
          <li><strong>Build and submit weekly.</strong> One milestone a week for four weeks, each one reviewed.</li>
        </ol>
        <a href="{apply_url}" class="btn btn-primary btn-lg">Apply for the {esc(noun)} internship {ARROW}</a>
      </div>
    </section>

    <!--TRUST-->
    <section class="section section-soft ip-section" aria-labelledby="faq-title">
      <div class="container ip-narrow">
        <h2 class="h2" id="faq-title">{esc(noun)} internship: questions and answers</h2>
        <div class="accordion ip-faq">""")
    for i, (q, a) in enumerate(faq):
        p.append(f"""
          <details{' open' if i == 0 else ''}>
            <summary>{esc(q)}</summary>
            <div class="acc-body"><p>{esc(a)}</p></div>
          </details>""")
    others = ''.join(f'<li><a href="/internships/{o["slug"]}">{esc(o["noun"])} internship</a></li>' for o in all_tracks if o['slug'] != slug)
    p.append(f"""
        </div>
      </div>
    </section>

    <section class="section ip-section" aria-labelledby="more-title">
      <div class="container">
        <h2 class="h2" id="more-title">Other remote internships at SkillMe</h2>
        <ul class="ip-links" role="list">{others}</ul>
        <p class="ip-more"><a href="/internships" class="btn-link">See all {len(all_tracks)} internships &rarr;</a></p>
      </div>
    </section>
  </main>
""")
    p.append(FOOTER)
    return ''.join(p).replace('    <!--TRUST-->\n', TRUST.lstrip('\n'))


# ── hub page ─────────────────────────────────────────────────────────────────

CATEGORY_ORDER = ['fullstack', 'ai', 'systems', 'mobile']
CATEGORY_BLURB = {
    'fullstack': 'Build what people see and use: websites, interfaces, APIs and product design.',
    'ai': 'Work with data, models and LLMs, from analysis to agents.',
    'systems': 'The engineering core: languages, algorithms, databases, testing, security and delivery.',
    'mobile': 'Ship apps to phones and services to the cloud.',
}

HUB_SCRIPT = """
  <script>
    // Category filter + search for the internship list. Without JS every internship is simply shown.
    (function () {
      var chips = document.querySelectorAll('.ih-chip');
      var groups = document.querySelectorAll('.ih-group');
      var cards = document.querySelectorAll('.ih-card');
      var search = document.getElementById('ih-search');
      var empty = document.getElementById('ih-empty');
      var count = document.getElementById('ih-count');
      var cat = 'all', q = '';
      function update() {
        var shown = 0;
        groups.forEach(function (g) {
          var inCat = cat === 'all' || g.getAttribute('data-category') === cat;
          var any = false;
          g.querySelectorAll('.ih-card').forEach(function (c) {
            var ok = inCat && (!q || c.getAttribute('data-search').indexOf(q) !== -1);
            c.hidden = !ok;
            if (ok) { any = true; shown++; }
          });
          g.hidden = !any;
        });
        empty.hidden = shown > 0;
        count.textContent = shown + (shown === 1 ? ' internship' : ' internships');
      }
      chips.forEach(function (chip) {
        chip.addEventListener('click', function () {
          chips.forEach(function (c) { c.setAttribute('aria-pressed', 'false'); });
          chip.setAttribute('aria-pressed', 'true');
          cat = chip.getAttribute('data-category');
          update();
        });
      });
      search.addEventListener('input', function () { q = search.value.trim().toLowerCase(); update(); });
      document.getElementById('ih-reset').addEventListener('click', function () {
        search.value = ''; q = ''; chips[0].click(); search.focus();
      });
      document.querySelector('.ih-toolbar').hidden = false;
      update();
    })();
  </script>
"""


def render_hub(tracks, curriculum):
    canonical = url_for()
    title = 'Remote Internships with Stipend for Top Performers | SkillMe'
    description = (f'{len(tracks)} remote internships open to students worldwide, from AI to DevOps. Four weeks, one reviewed '
                   f'milestone a week, and a stipend of {STIPEND} for top performers.')
    graph = [
        breadcrumbs(('SkillMe', SITE + '/'), ('Internships', canonical)),
        {
            '@type': 'ItemList',
            '@id': canonical + '#list',
            'name': 'SkillMe remote internships',
            'numberOfItems': len(tracks),
            'itemListElement': [
                {'@type': 'ListItem', 'position': i, 'name': f"{t['noun']} remote internship", 'url': url_for(t['slug'])}
                for i, t in enumerate(tracks, 1)
            ],
        },
    ]
    by_cat = {c: [t for t in tracks if CATEGORY.get(t['quiz'], 'systems') == c] for c in CATEGORY_ORDER}
    chips = f'<button type="button" class="chip ih-chip" data-category="all" aria-pressed="true">All <span class="ih-chip-n mono">{len(tracks)}</span></button>'
    chips += ''.join(
        f'<button type="button" class="chip ih-chip" data-category="{c}" aria-pressed="false"><span class="ih-dot" data-cat="{c}" aria-hidden="true"></span>'
        f'{esc(CATEGORY_LABEL[c])} <span class="ih-chip-n mono">{len(by_cat[c])}</span></button>'
        for c in CATEGORY_ORDER)

    p = [head(title, description, canonical, graph)]
    p.append(f"""
  <main id="main">
    <section class="ip-hero ih-hero">
      <div class="container">
        <nav class="ip-crumbs" aria-label="Breadcrumb"><a href="/">SkillMe</a><span aria-hidden="true">/</span><span aria-current="page">Internships</span></nav>
        <span class="eyebrow">{len(tracks)} internships · 4 weeks each · open worldwide</span>
        <h1 class="h1 ip-title">Choose your internship and apply</h1>
        <p class="lead ip-lead">Remote internships with a stipend of {STIPEND} for top performers. Pick one below, take a 5-minute quiz, and a person reads your application.</p>
        <ol class="ih-steps" role="list">
          <li><span class="ih-step-n mono">1</span><span><strong>Choose an internship</strong>Each one has its own real project</span></li>
          <li><span class="ih-step-n mono">2</span><span><strong>Take the 5-minute quiz</strong>Eight questions on the basics</span></li>
          <li><span class="ih-step-n mono">3</span><span><strong>Hear back in 48 hours</strong>Shortlisted applicants get an offer letter</span></li>
        </ol>
      </div>
    </section>

    <section class="section section-soft ip-section ih-list" aria-labelledby="all-title">
      <div class="container">
        <h2 class="sr-only" id="all-title">All internships</h2>
        <div class="ih-toolbar" hidden>
          <div class="ih-chips" role="group" aria-label="Filter internships by category">{chips}</div>
          <div class="ih-search">
            <label for="ih-search" class="sr-only">Search internships</label>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
            <input type="search" class="input" id="ih-search" placeholder="Search, e.g. React, AWS, AI" autocomplete="off">
          </div>
        </div>
        <p class="sr-only" id="ih-count" aria-live="polite"></p>
        <p class="ih-empty" id="ih-empty" hidden>No internship matches that. <button type="button" class="btn-link" id="ih-reset">Clear filters</button></p>
""")
    for c in CATEGORY_ORDER:
        p.append(f"""
        <section class="ih-group" data-category="{c}" aria-labelledby="ih-{c}">
          <div class="ih-group-head">
            <h3 class="h3" id="ih-{c}"><span class="ih-dot" data-cat="{c}" aria-hidden="true"></span>{esc(CATEGORY_LABEL[c])}</h3>
            <p>{esc(CATEGORY_BLURB[c])}</p>
          </div>
          <div class="ih-grid">""")
        for t in by_cat[c]:
            projects = curriculum[t['cur']]
            first = projects[0]
            more = f' <span class="ih-more">+{len(projects) - 1} more</span>' if len(projects) > 1 else ''
            tech = ''.join(f'<li>{esc(x)}</li>' for x in t['tech'].split(' · '))
            search = ' '.join([t['label'], t['noun'], t['tech'], CATEGORY_LABEL[c]] + [plain(x['project_name']) for x in projects]).lower()
            p.append(f"""
            <article class="card ih-card" data-search="{esc(search)}">
              <h4 class="ih-card-title"><a href="/internships/{t['slug']}">{esc(t['label'])}</a></h4>
              <p class="ih-build"><span class="ih-label mono">You build</span>{inline(first['project_name'])}{more}</p>
              <ul class="ih-tech" role="list" aria-label="Tech stack">{tech}</ul>
              <ul class="ih-meta" role="list">
                <li>4 weeks</li><li>{esc(first['weeks']['1']['est_hours'])} hrs/week</li><li>Starts at {esc(first['weeks']['1']['difficulty'].lower())}</li>
              </ul>
              <div class="ih-actions">
                <a href="/quiz?domain={t['quiz']}" class="btn btn-primary" aria-label="Apply for the {esc(t['noun'])} internship">Apply {ARROW}</a>
                <a href="/internships/{t['slug']}" class="btn btn-ghost" aria-label="View details of the {esc(t['noun'])} internship">View details</a>
              </div>
            </article>""")
        p.append("""
          </div>
        </section>""")
    p.append("""
        <p class="ip-note">Reviewers take part in a personal capacity. Company names belong to their owners and do not imply a partnership or endorsement.</p>
      </div>
    </section>
""" + TRUST + """  </main>
""" + HUB_SCRIPT)
    p.append(FOOTER)
    return ''.join(p)


# ── generated blocks in existing files ───────────────────────────────────────

def replace_block(path, begin, end, body, anchor, before=True):
    """Replace the text between the begin/end markers, inserting the block at `anchor` the first time."""
    with open(path, encoding='utf-8', newline='') as f:
        content = f.read()
    nl = '\r\n' if '\r\n' in content else '\n'
    block = (begin + '\n' + body.strip('\n') + '\n' + end).replace('\n', nl)
    if begin in content:
        updated = re.sub(re.escape(begin) + r'.*?' + re.escape(end), lambda _: block, content, flags=re.S)
    else:
        if anchor not in content:
            raise SystemExit(f'{os.path.basename(path)}: anchor not found: {anchor!r}')
        piece = block + nl + anchor if before else anchor + nl + block
        updated = content.replace(anchor, piece, 1)
    return path, content, updated


def build_blocks(tracks, curriculum, lastmod):
    out = []

    cards = []
    for t in tracks:
        projects = curriculum[t['cur']]
        cat = CATEGORY.get(t['quiz'], 'systems')
        more = f' <span class="domain-build-more">+{len(projects) - 1} more</span>' if len(projects) > 1 else ''
        cards.append(
            f'          <a href="/internships/{t["slug"]}" class="domain-card" id="domain-{t["quiz"]}" data-category="{cat}">'
            f'<span class="domain-cat"><span class="cat-dot" aria-hidden="true"></span>{esc(CATEGORY_LABEL[cat])}</span>'
            f'<h3>{esc(t["label"])}</h3>'
            f'<p class="domain-build"><span class="domain-build-label mono">You build</span>{inline(projects[0]["project_name"])}{more}</p>'
            f'<span class="domain-tech mono">{esc(t["tech"])}</span>'
            f'<span class="domain-foot"><span class="domain-cta">4 weeks · Remote</span>'
            f'<span class="domain-arrow" aria-hidden="true">&rarr;</span></span></a>')
    out.append(replace_block(
        os.path.join(ROOT, 'index.html'),
        '          <!-- BEGIN internship cards (generated by tools/build_internship_pages.py) -->',
        '          <!-- END internship cards -->',
        '\n'.join(cards),
        '          <!-- internship cards -->', before=True))

    def run(hidden):
        attrs = ' aria-hidden="true"' if hidden else ''
        tab = ' tabindex="-1"' if hidden else ''
        items = ''.join(f'<li><a href="/internships/{t["slug"]}"{tab}>{esc(t["label"])}</a></li>' for t in tracks)
        return f'          <ul class="marquee-run" role="list"{attrs}>{items}</ul>'
    out.append(replace_block(
        os.path.join(ROOT, 'index.html'),
        '          <!-- BEGIN internship marquee (generated by tools/build_internship_pages.py) -->',
        '          <!-- END internship marquee -->',
        run(False) + '\n' + run(True),
        '          <!-- internship marquee -->', before=True))

    urls = [f'  <url>\n    <loc>{url_for()}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.90</priority>\n  </url>']
    urls += [f'  <url>\n    <loc>{url_for(t["slug"])}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.80</priority>\n  </url>' for t in tracks]
    out.append(replace_block(
        os.path.join(ROOT, 'sitemap.xml'),
        '  <!-- BEGIN internship pages (generated by tools/build_internship_pages.py) -->',
        '  <!-- END internship pages -->',
        '\n'.join(urls), '</urlset>', before=True))

    lines = ['## Internship pages', '',
             f'Each track has its own page with the weekly milestones, the project built, and answers to common questions. '
             f'All tracks are 4 weeks, remote, open worldwide, and pay a stipend of {STIPEND} to top performers only.', '',
             f'- [All internships]({url_for()}): Hub page listing every track.']
    for t in tracks:
        first = curriculum[t['cur']][0]
        lines.append(f'- [{t["noun"]} internship]({url_for(t["slug"])}): {t["tech"]}. Project: {plain(first["project_name"])}.')
    out.append(replace_block(
        os.path.join(ROOT, 'llms.txt'),
        '<!-- BEGIN internship pages (generated by tools/build_internship_pages.py) -->',
        '<!-- END internship pages -->',
        '\n'.join(lines) + '\n', '## Key Differentiators & Value Proposition', before=True))

    full = ['## 3a. Internship Track Details', '',
            f'Every track below is a 4-week remote internship, open to students worldwide, with one reviewed milestone per week. '
            f'Top performers earn a stipend of {STIPEND}; it is not paid to every intern. Submissions are reviewed by the SkillMe '
            f'team, which includes engineers who work at {REVIEWERS} in a personal capacity.', '']
    for t in tracks:
        projects = curriculum[t['cur']]
        full += [f'### {t["noun"]} internship', '',
                 f'- **URL**: {url_for(t["slug"])}',
                 f'- **Apply**: {SITE}/quiz?domain={t["quiz"]}',
                 f'- **Stack**: {t["tech"]}']
        for proj in projects:
            weeks = '; '.join(f'Week {n}: {plain(proj["weeks"][n]["title"])}' for n in sorted(proj['weeks']))
            full.append(f'- **Project — {plain(proj["project_name"])}**: {plain(proj["tagline"])} {weeks}.')
        full.append('')
    out.append(replace_block(
        os.path.join(ROOT, 'llms-full.txt'),
        '<!-- BEGIN internship track details (generated by tools/build_internship_pages.py) -->',
        '<!-- END internship track details -->',
        '\n'.join(full), '## 4. Credential Verification & Authenticity', before=True))
    return out


# ── main ─────────────────────────────────────────────────────────────────────

def existing_lastmod(path):
    """Keep the sitemap date stable unless something actually changed (so --check is deterministic)."""
    try:
        with open(path, encoding='utf-8') as f:
            m = re.search(r'BEGIN internship pages.*?<lastmod>([^<]+)</lastmod>', f.read(), re.S)
        return m.group(1) if m else None
    except OSError:
        return None


def main():
    check = '--check' in sys.argv
    with open(CURRICULUM, encoding='utf-8') as f:
        curriculum = json.load(f)
    tracks = [dict(quiz=q, cur=c, label=l, noun=n, slug=s, tech=tech) for q, c, l, n, s, tech in TRACKS]
    missing = [t['cur'] for t in tracks if not curriculum.get(t['cur'])]
    if missing:
        raise SystemExit(f'No curriculum for: {", ".join(missing)}')
    unlisted = sorted(set(curriculum) - {t['cur'] for t in tracks})
    if unlisted:
        raise SystemExit(f'Curriculum tracks with no page (add them to TRACKS): {", ".join(unlisted)}')

    files = {os.path.join(OUT_DIR, 'index.html'): render_hub(tracks, curriculum)}
    for t in tracks:
        files[os.path.join(OUT_DIR, t['slug'] + '.html')] = render_track(t, curriculum[t['cur']], tracks)

    stale = []
    for path, content in files.items():
        old = None
        if os.path.isfile(path):
            with open(path, encoding='utf-8', newline='') as f:
                old = f.read()
        if old != content:
            stale.append(os.path.relpath(path, ROOT))
            if not check:
                os.makedirs(OUT_DIR, exist_ok=True)
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(content)

    sitemap = os.path.join(ROOT, 'sitemap.xml')
    lastmod = existing_lastmod(sitemap)
    if stale or not lastmod:
        lastmod = lastmod if check and lastmod else date.today().isoformat()
    for path, old, new in build_blocks(tracks, curriculum, lastmod):
        if old != new:
            stale.append(os.path.relpath(path, ROOT))
            if not check:
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(new)

    if check and stale:
        print('Internship pages are out of date (run python tools/build_internship_pages.py): ' + ', '.join(sorted(set(stale))))
        sys.exit(1)
    print(f'{"Checked" if check else "Built"} {len(files)} pages; {len(set(stale))} file(s) {"stale" if check else "written"}.')


if __name__ == '__main__':
    main()
