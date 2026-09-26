"""
Curriculum Tests — every domain serves 3 real 4-week tracks and domain labels resolve correctly
"""
import pytest

from services.project_curriculum import PROJECT_CURRICULUM, resolve_domain_key, get_project_track_for_student

EXPECTED_DOMAINS = {
    "web-dev", "python", "react", "node", "java", "ml", "data-science", "flutter",
    "devops", "cpp", "cloud", "cyber", "uiux", "genai", "sql",
}

# New domains launch with a single project track (see TRACK_COUNT_OVERRIDES in build_curriculum.py)
NEW_SINGLE_TRACK_DOMAINS = {"ai-engineer", "fde", "sde", "ai-pm", "qa"}


@pytest.mark.edge
class TestCurriculumContent:
    def test_all_domains_present(self):
        assert EXPECTED_DOMAINS <= set(PROJECT_CURRICULUM)

    @pytest.mark.parametrize("domain", sorted(EXPECTED_DOMAINS))
    def test_domain_has_three_distinct_tracks(self, domain):
        tracks = PROJECT_CURRICULUM[domain]
        # Track assignment is student_id % len(tracks) — changing the count reshuffles enrolled students
        assert len(tracks) == 3
        assert len({t["project_name"] for t in tracks}) == 3
        assert not any("Scale Application" in t["project_name"] for t in tracks)

    @pytest.mark.parametrize("domain", sorted(EXPECTED_DOMAINS))
    def test_weeks_ramp_up_in_difficulty(self, domain):
        for track in PROJECT_CURRICULUM[domain]:
            weeks = track["weeks"]
            assert [weeks[w]["difficulty"] for w in "1234"] == ["Beginner", "Beginner+", "Intermediate", "Intermediate+"]
            for w in "1234":
                assert weeks[w]["description"].strip()
                assert len(weeks[w]["deliverables"]) >= 3
                assert len(weeks[w]["post_highlights"]) == 3


@pytest.mark.edge
class TestNewDomainCurriculum:
    def test_all_new_domains_present(self):
        assert NEW_SINGLE_TRACK_DOMAINS <= set(PROJECT_CURRICULUM)

    @pytest.mark.parametrize("domain", sorted(NEW_SINGLE_TRACK_DOMAINS))
    def test_domain_has_one_track(self, domain):
        tracks = PROJECT_CURRICULUM[domain]
        assert len(tracks) == 1

    @pytest.mark.parametrize("domain", sorted(NEW_SINGLE_TRACK_DOMAINS))
    def test_weeks_ramp_up_in_difficulty(self, domain):
        for track in PROJECT_CURRICULUM[domain]:
            weeks = track["weeks"]
            assert [weeks[w]["difficulty"] for w in "1234"] == ["Beginner", "Beginner+", "Intermediate", "Intermediate+"]
            for w in "1234":
                assert weeks[w]["description"].strip()
                assert len(weeks[w]["deliverables"]) >= 3
                assert len(weeks[w]["post_highlights"]) == 3

    @pytest.mark.parametrize("domain", sorted(NEW_SINGLE_TRACK_DOMAINS))
    def test_feedback_builds_for_every_week(self, domain):
        from services.feedback_service import build_feedback
        for week in range(1, 5):
            fb = build_feedback(domain, 1, week)
            assert fb["checklist"]
            assert fb["domain_tips"], f"{domain} is missing a DOMAIN_TIPS entry"

    def test_ai_pm_footer_is_non_code(self):
        desc = PROJECT_CURRICULUM["ai-pm"][0]["weeks"]["1"]["description"]
        assert "No code needed" in desc

    def test_qa_footer_mentions_test_results(self):
        desc = PROJECT_CURRICULUM["qa"][0]["weeks"]["1"]["description"]
        assert "test results" in desc.lower() or "test suite" in desc.lower()

    def test_swe_aliases_to_sde(self):
        assert resolve_domain_key("SWE") == "sde"
        assert resolve_domain_key("swe") == "sde"


@pytest.mark.edge
class TestDomainResolution:
    @pytest.mark.parametrize("label,key", [
        ("web-dev", "web-dev"),
        ("Web Development", "web-dev"),
        ("nodejs", "node"),
        ("Data Science", "data-science"),
        ("datascience", "data-science"),
        ("Cybersecurity", "cyber"),
        ("cybersecurity", "cyber"),
        ("Cloud / AWS", "cloud"),
        ("ui-ux", "uiux"),
        ("UI/UX Design", "uiux"),
        ("Generative AI", "genai"),
        ("genai", "genai"),
        ("SQL / Databases", "sql"),
        ("Android / Kotlin", "flutter"),
        ("DSA / Competitive", "cpp"),
        ("Blockchain / Web3", "web-dev"),
        ("", "web-dev"),
        (None, "web-dev"),
        # Role-based renames
        ("Full Stack Engineer", "web-dev"),
        ("Frontend Engineer", "react"),
        ("Backend Engineer", "node"),
        ("App Developer", "flutter"),
        # New domains
        ("AI Engineer", "ai-engineer"),
        ("ai-engineer", "ai-engineer"),
        ("Forward Deployed Engineer", "fde"),
        ("fde", "fde"),
        ("SDE", "sde"),
        ("SWE", "sde"),
        ("AI Product Management", "ai-pm"),
        ("ai-pm", "ai-pm"),
        ("Software Quality", "qa"),
        ("qa", "qa"),
    ])
    def test_resolves(self, label, key):
        assert resolve_domain_key(label) == key

    def test_track_assignment_is_stable(self):
        assert get_project_track_for_student("sql", 7) is PROJECT_CURRICULUM["sql"][7 % 3]


@pytest.mark.edge
class TestNonCodingShowcase:
    """UI/UX and Cloud interns submit the same LinkedIn post, but must never be told to push code / use localhost."""

    CODE_ONLY = ("push your code", "localhost", "vs code", "same repo", "commits small", "debug code")

    @pytest.mark.parametrize("domain", ["uiux", "cloud", "ml", "data-science"])
    def test_task_footer_matches_domain(self, domain):
        for track in PROJECT_CURRICULUM[domain]:
            for week in track["weeks"].values():
                text = week["description"].lower()
                footer = text.split("### 📤 submission")[1]
                assert not any(p in footer for p in self.CODE_ONLY), footer
                assert "same repo" not in text

    def test_uiux_footer_says_no_code_and_figma(self):
        desc = PROJECT_CURRICULUM["uiux"][0]["weeks"]["1"]["description"]
        assert "No code needed" in desc and "Figma" in desc

    def test_cloud_footer_warns_about_secrets(self):
        desc = PROJECT_CURRICULUM["cloud"][0]["weeks"]["1"]["description"]
        assert "access keys" in desc

    @pytest.mark.parametrize("domain", ["uiux", "cloud", "ml", "data-science"])
    @pytest.mark.parametrize("week", [1, 2, 3, 4])
    def test_feedback_has_no_code_only_tips(self, domain, week):
        # Only the generic tips — a task's own checklist may legitimately ask for a repo (e.g. cloud site code)
        from services.feedback_service import build_feedback
        fb = build_feedback(domain, 1, week)
        text = " ".join([fb["stage_tip"], *fb["domain_tips"], *fb["general_tips"]]).lower()
        assert "github repo" not in text and "commits" not in text and "debug code" not in text

    @pytest.mark.parametrize("domain", ["ml", "data-science"])
    def test_notebook_footer_explains_sharing(self, domain):
        desc = PROJECT_CURRICULUM[domain][0]["weeks"]["1"]["description"]
        assert "Colab" in desc and "Kaggle" in desc and "notebook link" in desc

    def test_coding_domains_keep_repo_guidance(self):
        from services.feedback_service import build_feedback
        tips = [t for w in range(1, 5) for t in build_feedback("python", 1, w)["general_tips"]]
        assert any("GitHub" in t for t in tips)


@pytest.mark.edge
class TestLinkedInCaption:
    async def _caption(self, client, admin_headers, domain):
        r = await client.post("/api/students/apply", json={
            "first_name": "Cap", "last_name": "Test", "email": f"cap-{domain}@example.com", "domain": domain,
        })
        sid = r.json()["student_id"]
        e = await client.post(f"/api/admin/students/{sid}/enroll", headers=admin_headers)
        bid = e.json()["batch_id"]
        data = (await client.get(f"/api/tasks/current/{sid}/{bid}")).json()
        return data["linkedin_templates"]["1"]

    @pytest.mark.parametrize("domain", ["UI/UX Design", "Cloud / AWS", "python"])
    async def test_caption_never_mentions_localhost(self, client, admin_headers, domain):
        caption = await self._caption(client, admin_headers, domain)
        assert "localhost" not in caption.lower() and "vs code" not in caption.lower()
        assert "#SkillMe" in caption

    async def test_data_science_caption_is_notebook_worded(self, client, admin_headers):
        caption = await self._caption(client, admin_headers, "Data Science")
        assert "notebook link" in caption and "#DataScience" in caption and "Data Science Virtual Internship" in caption

    async def test_uiux_caption_is_design_worded(self, client, admin_headers):
        caption = await self._caption(client, admin_headers, "UI/UX Design")
        assert "Figma" in caption and "#UXDesign" in caption and "#Coding" not in caption
        assert "UI/UX Design Virtual Internship" in caption
