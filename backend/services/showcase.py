"""
SkillMe — How students show their work, per domain

Every domain submits the same thing (a LinkedIn post URL), but what goes *in* the post
differs: a coder shares a demo and a repo, a designer shares a Figma prototype, a cloud
intern shares a live URL and an architecture diagram, an ML / data intern shares a notebook
and charts. This module is the single place
that wording lives, so the task page, LinkedIn caption and submission feedback agree.
"""

DEFAULT = {
    # Footer shown under every week's task (markdown)
    "submission": (
        "Push your code to GitHub with a short README, then share a LinkedIn post with a "
        "30–60 second demo video or 2–3 screenshots and submit the post link on your dashboard."
    ),
    # Shown from week 2 onwards
    "continue": "keep working in the same repo",
    # LinkedIn caption pieces
    "caption_did": "What I did in Week {week}:",
    "caption_demo": "Here's a quick demo of it running 👇",
    "hashtags": ["BuildInPublic", "LearningByDoing", "TechInternship"],
    # General tips attached to every submission's feedback
    "tips": [
        "Push your code to a public GitHub repo with a README (what it does, how to run it, screenshots) and share the link in your post or its comments.",
        "Keep commits small with clear messages — it shows how you work, not just what you shipped.",
    ],
    "week1_tip": "Keep a clean folder structure and a README with setup steps now — it saves you time in weeks 2–4.",
    "week4_tip": "Do a full end-to-end run, remove leftover debug code, and update your README with final screenshots.",
}

SHOWCASE = {
    "uiux": {
        "submission": (
            "No code needed. Set your Figma file's share access to **Anyone with the link can view**, then share a "
            "LinkedIn post with 2–4 screens (or a 30–60 second prototype walkthrough), a line on the problem you're "
            "solving and the Figma link, and submit the post link on your dashboard."
        ),
        "continue": "keep working in the same Figma file",
        "caption_demo": "Here are the screens and my design process 👇 (Figma link in the comments)",
        "hashtags": ["UXDesign", "UIDesign", "Figma", "DesignProcess"],
        "tips": [
            "Share your Figma link with view access and open it in a private browser window to check it works before posting.",
            "Show before-and-after screens when you change something after feedback — reviewers love seeing iteration.",
        ],
        "week1_tip": "Keep your research notes, personas and flows in clearly named Figma pages now — it makes your week 4 case study much easier.",
        "week4_tip": "Click through your whole prototype one last time, tidy up page and layer names, and make sure your case study tells the story from problem to solution.",
    },
    "cloud": {
        "submission": (
            "Share a LinkedIn post with your live URL (if the week has one), a simple architecture diagram or "
            "2–3 console screenshots, and a 30–60 second demo, then submit the post link on your dashboard. "
            "Before posting, hide your account ID, access keys and billing details in every screenshot. "
            "Push any code you wrote to GitHub with a short README."
        ),
        "continue": "keep building on the same setup",
        "caption_demo": "Here's the architecture and a quick demo of it live 👇",
        "hashtags": ["CloudComputing", "AWS", "Serverless", "LearningByDoing"],
        "tips": [
            "Blur or crop your account ID, access keys and billing page out of every screenshot before you post it.",
            "A simple architecture diagram (boxes and arrows is fine) explains your setup faster than a paragraph of text.",
        ],
        "week1_tip": "Set up your budget alert and an admin IAM user first, and keep a notes file of every resource you create — you'll need it for cleanup.",
        "week4_tip": "Test the full flow end to end, update your architecture diagram and README, and delete any resources you no longer need.",
    },
}

# ML and Data Science work mostly happens in Colab / Kaggle notebooks, and weeks 3–4 add a Streamlit/Gradio app
NOTEBOOK = {
    "submission": (
        "Run all cells so every output and chart is visible, then share your notebook: in Colab use "
        "**Share → Anyone with the link**, on Kaggle set it to **Public** (or save it to GitHub with a short README). "
        "Share a LinkedIn post with 2–3 key charts or results (or a 30–60 second demo once you have an app), "
        "put the notebook link in the post or its first comment, and submit the post link on your dashboard."
    ),
    "continue": "keep working in the same notebook or project",
    "caption_demo": "Here are my key results and charts 👇 (notebook link in the comments)",
    "tips": [
        "Open your notebook link in a private browser window before posting to check that anyone can view it with the outputs showing.",
        "Lead with one result in plain words (e.g. '92% accuracy on unseen data') and one chart — most people won't open the notebook.",
    ],
    "week1_tip": "Use markdown cells to add a short heading and one line of explanation above each step — it turns your notebook into something others can follow.",
    "week4_tip": "Restart and run all cells from top to bottom to make sure it works cleanly, delete scratch cells, and finish with a short summary of what you found.",
}
SHOWCASE["ml"] = {**NOTEBOOK, "hashtags": ["DataScience", "Python", "LearningByDoing"]}
SHOWCASE["data-science"] = {**NOTEBOOK, "hashtags": ["DataAnalytics", "Python", "LearningByDoing"]}


# The main hashtag people in each field actually follow
DOMAIN_HASHTAG = {
    "web-dev": "WebDevelopment", "python": "Python", "react": "ReactJS", "node": "NodeJS",
    "java": "Java", "ml": "MachineLearning", "data-science": "DataScience", "flutter": "Flutter",
    "devops": "DevOps", "cpp": "CPlusPlus", "cloud": "AWS", "cyber": "CyberSecurity",
    "uiux": "UIUX", "genai": "GenerativeAI", "sql": "SQL",
}


def hashtags_for(domain_key: str) -> str:
    """'#SkillMe #SkillMeInternship #Python #BuildInPublic ...' without duplicates."""
    tags = ["SkillMe", "SkillMeInternship", DOMAIN_HASHTAG.get(domain_key, "TechInternship"), *showcase_for(domain_key)["hashtags"]]
    return " ".join(f"#{t}" for t in dict.fromkeys(tags))


def showcase_for(domain_key: str) -> dict:
    """Wording for a curriculum domain key (e.g. 'uiux', 'cloud'); falls back to the coding default."""
    return {**DEFAULT, **SHOWCASE.get(domain_key, {})}
