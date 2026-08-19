# SkillMe Internship Flex - Implementation Plan

## 1. Existing Architecture Summary
SkillMe uses a robust stack:
- **Backend:** Python/FastAPI with SQLite (via `databases` and `aiosqlite`).
- **Frontend:** Vanilla HTML/CSS/JavaScript with responsive, custom grid-based layouts.
- **Payment Integration:** Razorpay is implemented securely in `backend/routes/payments.py` with server-side signature verification.
- **Task Management:** Tasks are stored in the `issues` table and mapped to students via `batch_id` and `student_id`.
- **Certificate/LOR System:** Certificates are tracked in the `certificates` table and generated dynamically using `reportlab` (`certificate_service.py`) and HTML/CSS (`certificate.html`, `lor.html`).

## 2. Relevant Frontend Files
- `dashboard.html`: Needs the 3 new Flex feature cards (Task PDF, Portfolio, Instant Certificate) integrated directly into the dashboard layout at the very top (just below the progress stats). They will be aligned in a responsive 3-column CSS Grid. To ensure they are highly visible, each card will feature a distinct glowing border, elevated background contrast, and prominent action buttons so they immediately catch the eye without blending into the rest of the tasks.
- `dashboard.js`: Needs logic to trigger the payment modal without requiring 100% completion, and links to download Task PDFs and view the Portfolio.
- `style.css`: Ensure styling for the new cards aligns with existing dashboard components.

## 3. Relevant Backend Files
- `backend/routes/students.py`: Add an endpoint to generate and download Task PDFs.
- `backend/routes/payments.py`: Modify order creation to support the ₹129 Instant Certificate + LOR flow without requiring `pct === 100`.
- `backend/services/certificate_service.py`: Verify that issuing a certificate does not accidentally mutate `enrollments.status` to `completed`.
- `backend/routes/admin.py`: Add flags to distinguish between "Certificate Issued" (via `certificates` table presence) and "Internship Completed" (via `enrollments.status`).

## 4. Database/Schema Changes Required
**No schema changes are required.** 
The existing schema perfectly supports this feature:
- **Payment tracking:** The `payments` table securely links `razorpay_order_id` to `student_id` and `batch_id`.
- **Certificate tracking:** The `certificates` table tracks issued certs without modifying the `enrollments.status` table. 
- We can simply check `SELECT id FROM certificates WHERE student_id = ?` to determine if `certificate_issued = true`, leaving their actual internship status intact.

## 5. Existing Payment Integration
Razorpay is already fully integrated (`/api/payments/create-order` and `/api/payments/verify`). The frontend utilizes `window.Razorpay`.
- **Change needed:** Update `/create-order` to accept a parameter for the "Flex Plan" (₹129) or update the global pricing strategy.

## 6. Existing Certificate/LOR Implementation
- `backend/services/certificate_service.py` safely issues certificates without mutating `enrollments` status.
- `backend/routes/certificates.py` provides secure download links.
- `lor.html` provides dynamic web-based LORs using URL parameters.

## 7. Existing Task/PDF Implementation
- Tasks are stored in the `issues` table (fields: `title`, `description`, `difficulty`, etc.).
- **Change needed:** There is currently no PDF generator for Tasks. We will implement a new endpoint (e.g. `/api/students/tasks/{issue_id}/pdf`) that utilizes Python's `reportlab` to dynamically generate a branded PDF containing the issue's title, description, and GitHub submission instructions.

## 8. Existing Portfolio Implementation
- `portfolio.html` exists and appears to pull GitHub data based on URL params (`?gh=...` or `?student_id=...`).
- **Change needed:** We will add a button in the dashboard that routes the intern securely to their personal `portfolio.html` link.

## 9. GitHub Integration
- The system heavily integrates with GitHub via `backend/services/github_service.py` to track PRs (`submissions` table). 
- The Instant Certificate flow will not disrupt this. Students will still see their assigned tasks and submit PRs normally.

## 10. Recommended Implementation Order
- **Phase 1:** Update frontend `dashboard.html` and `dashboard.js` to render the three new Flex Option cards directly into the dashboard layout (UI only).
- **Phase 2:** Implement the Task PDF generation endpoint in Python (`reportlab`) and connect the "Download Task PDF" button.
- **Phase 3:** Update `payments.py` to process the ₹129 fee and remove the 100% completion requirement from `dashboard.js` for this specific card. Connect the "Get Certificate + LOR" button.
- **Phase 4:** Link the "Build Your Portfolio" button to the existing `portfolio.html`.
- **Phase 5:** Update `admin.py` to visually flag students who bought the certificate early vs. those who organically completed 100% of tasks.
- **Phase 6:** End-to-end testing of all flows.

## 11. Risks and Edge Cases
- **Risk:** A student might accidentally purchase the ₹129 certificate twice. 
  - *Mitigation:* The `payments.py` and frontend must query the `certificates` table and disable the buy button if the certificate is already issued.
- **Risk:** Rendering markdown/HTML task descriptions in a PDF.
  - *Mitigation:* We will use `reportlab.platypus` to cleanly wrap long paragraphs and render standard text without markdown parsing crashes.
- **Risk:** Admin confusion over who actually finished the internship.
  - *Mitigation:* Explicitly label Admin UI with "Status: Active | Certificate: Issued".
