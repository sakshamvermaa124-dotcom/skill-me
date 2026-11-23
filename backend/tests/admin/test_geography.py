"""
Admin geography: country count, per-country conversion and revenue, India vs international,
new markets, and the country filter on analytics and the students list.

World:
  in1  IN  enrolled, paid ₹129
  in2  IN  applied only
  ng1  NG  enrolled, paid ₹99
  ng2  NG  applied only
  br1  BR  applied (first Brazilian applicant, applied recently → new market)
  xx1  no country
  tst  AE  TEST account (excluded)
"""
from datetime import datetime, timedelta

import pytest

from tests.conftest import seed_batch, test_db


async def _world():
    recent = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

    async def student(email, country, created="2026-02-01 10:00:00", **cols):
        f = {"first_name": email, "last_name": "T", "email": f"{email}@x.com", "domain": "web-dev",
             "country": country, "created_at": created, **cols}
        return await test_db.insert(
            f"INSERT INTO students ({', '.join(f)}) VALUES ({', '.join('?' for _ in f)})", tuple(f.values()))

    n = iter(range(1, 50))

    async def enroll_and_pay(sid, amount):
        b = await seed_batch(test_db, batch_number=next(n))
        await test_db.insert("INSERT INTO enrollments (student_id, batch_id, joined_at) VALUES (?, ?, '2026-02-03 10:00:00')", (sid, b))
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status,"
            " initiated_at, completed_at, created_at, updated_at) VALUES (?,?,?,?,?, 'paid', ?, ?, ?, ?)",
            (sid, b, f"order_{sid}", f"pay_live_{sid}", amount, recent, recent, recent, recent))

    await enroll_and_pay(await student("in1", "IN"), 12900)
    await student("in2", "IN")
    await enroll_and_pay(await student("ng1", "NG"), 9900)
    await student("ng2", "NG")
    await student("br1", "BR", created=recent)
    await student("xx1", None)
    await student("tst", "AE", is_test=1)


@pytest.mark.admin
class TestGeography:
    async def test_analytics_geography(self, client, admin_headers):
        await _world()
        r = await client.get("/api/admin/analytics?fresh=true", headers=admin_headers)
        assert r.status_code == 200
        g = r.json()["geography"]
        assert g["country_count"] == 3                      # IN, NG, BR (test AE excluded)
        assert g["unknown"] == 1
        by = {c["key"]: c for c in g["countries"]}
        assert [c["key"] for c in g["countries"]][:2] == ["IN", "NG"]
        assert by["IN"]["label"] == "India"
        assert (by["IN"]["applications"], by["IN"]["enrolled"], by["IN"]["paid"]) == (2, 1, 1)
        assert by["IN"]["revenue_rupees"] == 129.0 and by["IN"]["enroll_rate"] == 50.0
        assert by["NG"]["revenue_rupees"] == 99.0
        assert g["india"]["applications"] == 2 and g["international"]["applications"] == 3
        assert g["india"]["share_revenue"] == round(129 * 100 / 228, 1)
        assert g["international"]["paid"] == 1
        assert [c["key"] for c in g["new_30d"]] == ["BR"]
        assert ["BR", "Brazil"] in r.json()["options"]["countries"]

    async def test_country_filter_narrows_everything(self, client, admin_headers):
        await _world()
        r = await client.get("/api/admin/analytics?fresh=true&country=ng", headers=admin_headers)
        d = r.json()
        assert d["overview"]["applicants"] == 2
        assert d["overview"]["revenue_rupees"] == 99.0
        assert d["geography"]["country_count"] == 1

    async def test_stats_carries_business_kpis_and_geo(self, client, admin_headers):
        await _world()
        await client.get("/api/admin/analytics?fresh=true", headers=admin_headers)  # warm the shared rollup
        s = (await client.get("/api/admin/stats", headers=admin_headers)).json()
        assert s["revenue_rupees"] == 228.0
        assert s["revenue_30d_rupees"] == 228.0 and s["revenue_prev_30d_rupees"] == 0
        assert s["paying_30d"] == 2
        assert s["paid_rate_of_enrolled"] == 100.0
        assert s["geo"]["country_count"] == 3

    async def test_students_list_filters_by_country(self, client, admin_headers):
        await _world()
        r = await client.get("/api/admin/students?country=in", headers=admin_headers)
        rows = r.json()["students"]
        assert {x["email"] for x in rows} == {"in1@x.com", "in2@x.com"}
        assert all(x["country"] == "IN" for x in rows)
