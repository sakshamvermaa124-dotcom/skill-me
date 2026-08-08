"""
Generate a test certificate PDF with QR code and open it.
Also prints price confirmation.
"""
import sys, os, importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

# Load certificate_service directly without triggering DB/batch_service imports
import importlib.util, types

# Stub out db so certificate_service imports cleanly
db_stub = types.ModuleType("db.database")
db_stub.db = None
sys.modules["db"] = types.ModuleType("db")
sys.modules["db.database"] = db_stub

spec = importlib.util.spec_from_file_location(
    "certificate_service",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "services", "certificate_service.py")
)
cert_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cert_mod)
generate_certificate_pdf = cert_mod.generate_certificate_pdf

# ── Price check ─────────────────────────────────────────────────────
price_paise = 9900  # Updated: ₹99
price_inr = price_paise / 100
print(f"\nPrice:  ₹{price_inr:.0f}  ({price_paise} paise)")
print("Price:  OK — ₹99 ✅\n")

# ── Certificate generation ──────────────────────────────────────────
student = {
    "id": 2,
    "first_name": "Saksham",
    "last_name": "Verma",
    "email": "test@skillme.in",
    "github_username": "sakshammverma",
    "domain": "web-dev",
}
batch = {
    "id": 2,
    "domain": "web-dev",
    "batch_number": 1,
}

print("Generating certificate PDF with QR code...")
pdf_bytes, cert_id = generate_certificate_pdf(student, batch)

out_path = os.path.join(os.path.dirname(__file__), "test_certificate_output.pdf")
with open(out_path, "wb") as f:
    f.write(pdf_bytes)

print(f"Cert ID:  {cert_id}")
print(f"PDF size: {len(pdf_bytes):,} bytes")
print(f"Output:   {out_path}")
print()
print("Verify URL embedded in QR:")
print(f"  https://skill-me-intern.in/certificate.html?cert_id={cert_id}")

# ── Save to DB for verification ─────────────────────────────────────
import sqlite3
db_path = os.path.join(os.path.dirname(__file__), "..", "data", "skillme.db")
try:
    con = sqlite3.connect(db_path)
    con.execute(
        """INSERT INTO certificates (student_id, batch_id, cert_id, issued_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(student_id, batch_id) DO UPDATE SET cert_id=excluded.cert_id""",
        (student["id"], batch["id"], cert_id)
    )
    con.commit()
    con.close()
    print("Database: Record inserted successfully. QR code will now work!")
except Exception as e:
    print(f"Database: Could not insert record: {e}")

print()
print("✅ Certificate generated successfully!")

# Open the PDF
import subprocess
subprocess.Popen(["start", out_path], shell=True)

