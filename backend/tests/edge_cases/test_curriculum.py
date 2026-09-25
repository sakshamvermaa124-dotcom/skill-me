"""
Curriculum Tests — every domain serves 3 real 4-week tracks and domain labels resolve correctly
"""
import pytest

from services.project_curriculum import PROJECT_CURRICULUM, resolve_domain_key, get_project_track_for_student

EXPECTED_DOMAINS = {
    "web-dev", "python", "react", "node", "java", "ml", "data-science", "flutter",
    "devops", "cpp", "cloud", "cyber", "uiux", "genai", "sql",
}


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
    ])
    def test_resolves(self, label, key):
        assert resolve_domain_key(label) == key

    def test_track_assignment_is_stable(self):
        assert get_project_track_for_student("sql", 7) is PROJECT_CURRICULUM["sql"][7 % 3]
