"""
Student Tests — Wall of work
Tests GET /api/students/wall.
"""
import pytest
from tests.conftest import test_db, seed_student, seed_batch


async def _approved(student_id: int, batch_id: int, week: int, url: str, status: str = "approved"):
    await test_db.insert(
        """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, reviewed_at)
           VALUES (?, ?, ?, ?, ?, datetime('now', ?))""",
        (student_id, batch_id, week, url, status, f"-{10 - week} minutes"),
    )


@pytest.mark.students
class TestWallOfWork:
    async def test_only_real_posts_one_per_student(self, client):
        batch = await seed_batch(test_db)
        a = await seed_student(test_db, email="a@x.com", first_name="asha", last_name="rao")
        b = await seed_student(test_db, email="b@x.com", first_name="Bilal", last_name="Khan")
        c = await seed_student(test_db, email="c@x.com", first_name="Chidi", last_name="Okafor")
        # a: two real posts -> only the latest shown
        await _approved(a, batch, 1, "https://www.linkedin.com/posts/asha_skillme-activity-7512880925748408320-abcd")
        await _approved(a, batch, 2, "https://www.linkedin.com/feed/update/urn:li:activity:7512880925748408321")
        # b: profile / feed links are not posts -> hidden
        await _approved(b, batch, 1, "https://www.linkedin.com/in/bilal-khan?utm_source=share")
        await _approved(b, batch, 2, "https://www.linkedin.com/feed/?shareActive=true")
        # c: real post but not approved -> hidden
        await _approved(c, batch, 1, "https://www.linkedin.com/posts/chidi_x-activity-1-a", status="pending")

        r = await client.get("/api/students/wall")
        assert r.status_code == 200
        posts = r.json()["posts"]
        assert len(posts) == 1
        assert posts[0]["name"] == "Asha R."
        assert posts[0]["week"] == 2
        assert "urn:li:activity:7512880925748408321" in posts[0]["url"]

    async def test_empty_wall(self, client):
        r = await client.get("/api/students/wall")
        assert r.status_code == 200
        assert r.json() == {"posts": []}
