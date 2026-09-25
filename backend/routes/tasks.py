from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from db.database import db
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from services.project_curriculum import get_project_track_for_student, resolve_domain_key
from services.showcase import showcase_for, hashtags_for
from services.email_service import _domain_label
from services.enrollment_service import enrollment_service

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


async def _load_student_enrollment(student_id: int, batch_id: int | None) -> tuple[dict, dict]:
    """Student + their enrollment row (`batch_id` is validated against the student)."""
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    resolved = await enrollment_service.resolve_batch_id(student_id, batch_id)
    enrollment = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (resolved,)) if resolved else None
    if not enrollment:
        raise HTTPException(status_code=404, detail="Student is not enrolled yet")
    return student, enrollment


@router.get("/latest/pdf")
async def generate_task_pdf(student_id: int, batch_id: int | None = None):
    student, batch = await _load_student_enrollment(student_id, batch_id)
    
    project_track = get_project_track_for_student(batch["domain"], student_id)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('MainTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=20, textColor=colors.HexColor('#0f172a'), spaceAfter=8)
    subtitle_style = ParagraphStyle('SubTitle', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=10, textColor=colors.HexColor('#64748b'), spaceAfter=15)
    heading_style = ParagraphStyle('CustomHeading2', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#1d4ed8'), spaceBefore=12, spaceAfter=6)
    normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#334155'), leading=14, spaceAfter=6)
    
    story = []
    story.append(Paragraph("<b>SkillMe Virtual Internship</b>", title_style))
    story.append(Paragraph(f"Complete 4-Week Project Specification &bull; {project_track['project_name']}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=12))
    
    story.append(Paragraph(f"Intern: <b>{student['first_name']} {student['last_name']}</b> | Domain: <b>{batch['domain']}</b>", heading_style))
    story.append(Paragraph(f"<b>Assigned Project:</b> {project_track['project_name']}<br/><i>{project_track['tagline']}</i>", normal_style))
    
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    headers = {"Content-Disposition": "inline; filename=skillme-4week-project-guide.pdf"}
    return Response(content=pdf, media_type="application/pdf", headers=headers)


@router.get("/current/{student_id}/{batch_id}")
async def get_current_tasks(student_id: int, batch_id: int):
    student, batch = await _load_student_enrollment(student_id, batch_id)

    prog = await db.fetch_one(
        "SELECT week FROM progress WHERE student_id = ? AND batch_id = ? ORDER BY week DESC LIMIT 1",
        (student_id, batch["id"])
    )
    current_week = int(prog["week"]) if prog else 1

    project_track = get_project_track_for_student(batch["domain"], student_id)
    
    # Generate correlated 4-week post templates, worded for how this domain shows its work
    domain_key = resolve_domain_key(batch["domain"])
    showcase = showcase_for(domain_key)
    domain_clean = _domain_label(batch["domain"])
    proj_name = project_track["project_name"]
    hashtags = hashtags_for(domain_key)

    linkedin_templates = {}
    weeks_dict = project_track.get("weeks", {})
    for w in [1, 2, 3, 4]:
        w_data = weeks_dict.get(str(w), weeks_dict.get(w, {}))
        bullets = "\n".join([f"• {pt}" for pt in w_data.get("post_highlights", [])])

        linkedin_templates[w] = (
            f"🚀 Excited to share my Week {w} milestone for '{proj_name}' in the {domain_clean} Virtual Internship at @SkillMe!\n\n"
            f"{showcase['caption_did'].format(week=w)}\n"
            f"{bullets}\n\n"
            f"{showcase['caption_demo']}\n\n"
            f"{hashtags}"
        )

    # Return ALL 4 weeks of tasks unified in one document
    tasks_list = []
    for w in [1, 2, 3, 4]:
        w_data = weeks_dict.get(str(w), weeks_dict.get(w, {}))
        tasks_list.append({
            "id": f"proj-{student_id}-w{w}",
            "title": w_data.get("title", f"Week {w} Project Task"),
            "description": w_data.get("description", ""),
            "deliverables": w_data.get("deliverables", []),
            "post_highlights": w_data.get("post_highlights", []),
            "week_number": w,
            "difficulty": w_data.get("difficulty") or {1: "Beginner", 2: "Beginner+", 3: "Intermediate"}.get(w, "Intermediate+"),
            "est_hours": w_data.get("est_hours"),
            "is_current": (w == current_week)
        })

    return {
        "student": {"first_name": student["first_name"], "last_name": student["last_name"]},
        "enrollment": {"domain": batch["domain"], "batch_id": batch["id"]},
        "batch": {"domain": batch["domain"]},  # legacy key for frontends deployed before the rename
        "project": {
            "name": project_track["project_name"],
            "tagline": project_track["tagline"],
            "weeks": project_track["weeks"]
        },
        "current_week": current_week,
        "tasks": tasks_list,
        "linkedin_templates": linkedin_templates
    }
