from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from db.database import db
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from services.project_curriculum import get_project_track_for_student

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

@router.get("/latest/pdf")
async def generate_task_pdf(student_id: int, batch_id: int):
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
    if not student or not batch:
        raise HTTPException(status_code=404, detail="Student or Batch not found")
    
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
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
    if not student or not batch:
        raise HTTPException(status_code=404, detail="Student or Batch not found")

    prog = await db.fetch_one(
        "SELECT week FROM progress WHERE student_id = ? AND batch_id = ? ORDER BY week DESC LIMIT 1",
        (student_id, batch_id)
    )
    current_week = int(prog["week"]) if prog else 1

    project_track = get_project_track_for_student(batch["domain"], student_id)
    
    # Generate correlated 4-week post templates
    name = f"{student['first_name']} {student['last_name']}".strip()
    domain_clean = batch["domain"].replace("-", " ").title()
    proj_name = project_track["project_name"]
    hashtag = batch["domain"].replace("-", "").capitalize()

    linkedin_templates = {}
    weeks_dict = project_track.get("weeks", {})
    for w in [1, 2, 3, 4]:
        w_data = weeks_dict.get(str(w), weeks_dict.get(w, {}))
        bullets = "\n".join([f"• {pt}" for pt in w_data.get("post_highlights", [])])
        
        linkedin_templates[w] = (
            f"🚀 Excited to share my Week {w} milestone for '{proj_name}' in the {domain_clean} Virtual Internship at SkillMe!\n\n"
            f"During Week {w}, I built and tested the following features locally on localhost in VS Code:\n\n"
            f"🎯 Week {w} Milestone Highlights:\n"
            f"{bullets}\n\n"
            f"Check out the quick video demonstration below to see the project running live on localhost! 💡\n\n"
            f"#SkillMe #SkillMeInternship #{hashtag} #Coding #BuildInPublic #LocalhostProject #SoftwareEngineering #TechInternship"
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
            "difficulty": "Foundation" if w == 1 else ("Intermediate" if w == 2 else ("Advanced" if w == 3 else "Capstone")),
            "is_current": (w == current_week)
        })

    return {
        "student": {"first_name": student["first_name"], "last_name": student["last_name"]},
        "batch": {"domain": batch["domain"], "repo_name": batch["repo_name"]},
        "project": {
            "name": project_track["project_name"],
            "tagline": project_track["tagline"],
            "weeks": project_track["weeks"]
        },
        "current_week": current_week,
        "tasks": tasks_list,
        "linkedin_templates": linkedin_templates
    }
