from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from pathlib import Path
import shutil, json
from html import escape
from database.connection import get_db, SessionLocal
from database.models import *
from auth.dependencies import require_role
from auth.csrf import ensure_csrf
from core.document_processor import extract_document, LEGACY_ERROR, EMPTY_ERROR
from core.chunker import chunk_text
from core.ollama_client import embed_many, ensure_models, health
from core.vector_store import get_collection
from core.retriever import retrieve
from core.key_point_generator import generate_key_points
from core.audit_pipeline import reset_failed_submission
from core.audit_runner import run_audit
from core.report_generator import report_csv, report_json, claim_report_rows
from config.settings import settings, BASE_DIR

router = APIRouter(prefix="/teacher")
templates = Jinja2Templates(directory="templates")

def page(request, template, user, db, **context):
    return templates.TemplateResponse(request=request, name=template, context={"user": user, "csrf_token": ensure_csrf(request), **context})

@router.get("/dashboard")
async def dashboard(request: Request, user=Depends(require_role("teacher")), db: Session=Depends(get_db)):
    docs = db.query(Document).count(); questions = db.query(Question).count(); submissions = db.query(Submission).count()
    awaiting = db.query(Grade).filter(Grade.released_to_student == False).count()
    grades = db.query(Grade).all()
    avg = round(sum(g.ai_marks/g.max_marks*100 for g in grades)/len(grades), 1) if grades else None
    return page(request, "teacher/dashboard.html", user, db, docs=docs, questions=questions, submissions=submissions,
                awaiting=awaiting, avg=avg, activities=db.query(Submission).order_by(Submission.submitted_at.desc()).limit(5).all())

def index_document(doc_id: int):
    db = SessionLocal()
    doc = db.get(Document, doc_id)
    if doc is None:
        db.close()
        return
    try:
        doc.indexing_status = "Indexing"
        doc.error_message = None
        db.commit()
        ensure_models()
        extracted, page_count = extract_document(doc.file_path)
        if not extracted:
            raise ValueError(EMPTY_ERROR)
        chunks = []
        for raw in extracted:
            location = raw["location_type"]; number = raw["page_number"]
            if location == "page":
                cid = f"doc{doc.id}_p{number}_c{raw.get('_c_no',1)}"
            elif location == "slide":
                cid = f"doc{doc.id}_s{number}_c{raw.get('_c_no',1)}"
            else:
                cid = f"doc{doc.id}_pNA_c{raw.get('_c_no',1)}"
            raw["chunk_id"] = cid
            chunks.append(raw)
        # Rebuild stable IDs globally per location
        counters = {}
        fixed = []
        for raw in chunks:
            key=(raw["location_type"],raw["page_number"])
            counters[key]=counters.get(key,0)+1
            n=counters[key]
            if raw["location_type"]=="page": cid=f"doc{doc.id}_p{raw['page_number']}_c{n}"
            elif raw["location_type"]=="slide": cid=f"doc{doc.id}_s{raw['page_number']}_c{n}"
            else: cid=f"doc{doc.id}_pNA_c{n}"
            raw["chunk_id"]=cid; fixed.append(raw)
        collection=get_collection()
        ids=[c["chunk_id"] for c in fixed]
        vectors = []
        batch_size = 8
        total_batches = (len(fixed) + batch_size - 1) // batch_size
        for start in range(0, len(fixed), batch_size):
            batch_number = start // batch_size + 1
            doc.indexing_status = f"Indexing ({batch_number}/{total_batches} batches)"
            db.commit()
            vectors.extend(embed_many([c["text"] for c in fixed[start:start + batch_size]]))
        metadatas=[{"document_id":doc.id,"document_name":doc.filename,"page_number":c["page_number"],
                    "location_type":c["location_type"],"chunk_id":c["chunk_id"]} for c in fixed]
        collection.upsert(ids=ids, embeddings=vectors, documents=[c["text"] for c in fixed], metadatas=metadatas)
        doc.indexing_status="Indexed"; doc.page_count=page_count; doc.chunk_count=len(fixed); doc.error_message=None
    except Exception as exc:
        doc.indexing_status="Failed"; doc.error_message=str(exc)
    finally:
        db.commit()
        db.close()

@router.get("/documents")
async def documents(request: Request, user=Depends(require_role("teacher")), db: Session=Depends(get_db)):
    return page(request, "teacher/documents.html", user, db,
                documents=db.query(Document).filter(Document.uploaded_by==user.id).order_by(Document.uploaded_at.desc()).all(),
                max_upload_mb=settings.max_upload_mb)

@router.get("/documents/status")
async def document_status(request: Request, user=Depends(require_role("teacher")), db: Session=Depends(get_db)):
    documents = db.query(Document).filter(Document.uploaded_by==user.id).order_by(Document.uploaded_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="components/documents_table.html",
        context={"documents": documents, "csrf_token": ensure_csrf(request)},
    )

@router.get("/ollama-status")
async def ollama_status(user=Depends(require_role("teacher"))):
    healthy, message = health()
    css_class = "online" if healthy else "offline"
    safe_message = escape(message, quote=True)
    return HTMLResponse(f'<span class="ollama {css_class}" title="{safe_message}">{safe_message}</span>')

@router.post("/documents/upload")
async def upload_documents(request: Request, background_tasks: BackgroundTasks, files: list[UploadFile]=File(...),
                           user=Depends(require_role("teacher")), db: Session=Depends(get_db)):
    form = await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    allowed={".pdf",".docx",".pptx",".txt"}
    for upload in files:
        suffix=Path(upload.filename).suffix.lower()
        if suffix in (".ppt",".doc"): error=LEGACY_ERROR
        elif suffix not in allowed: error="Unsupported file format."
        else:
            size=0; dest=BASE_DIR/"data"/"uploads"/f"{datetime.utcnow().timestamp():.0f}_{upload.filename}"
            with dest.open("wb") as f:
                while chunk:=upload.file.read(1024*1024):
                    size+=len(chunk)
                    f.write(chunk)
            if size > settings.max_upload_mb*1024*1024: dest.unlink(missing_ok=True); error="File exceeds the configured upload size limit."
            else:
                doc=Document(filename=upload.filename,file_path=str(dest),file_type=suffix.lstrip("."),uploaded_by=user.id,indexing_status="Uploaded")
                db.add(doc); db.flush(); db.commit()
                background_tasks.add_task(index_document, doc.id)
                continue
        doc=Document(filename=upload.filename,file_path="",file_type=suffix.lstrip("."),uploaded_by=user.id,indexing_status="Failed",error_message=error)
        db.add(doc)
    db.commit()
    return RedirectResponse("/teacher/documents", status_code=302)

@router.post("/documents/{doc_id}/reindex")
async def reindex(doc_id:int, background_tasks:BackgroundTasks, request:Request,
                  user=Depends(require_role("teacher")), db:Session=Depends(get_db)):
    if str((await request.form()).get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    doc=db.get(Document,doc_id)
    if not doc or doc.uploaded_by != user.id:
        raise HTTPException(404,"Document not found.")
    if not doc.file_path or not Path(doc.file_path).is_file():
        raise HTTPException(400,"The original uploaded file is unavailable and cannot be re-indexed.")
    doc.indexing_status="Indexing"
    doc.error_message=None
    db.commit()
    background_tasks.add_task(index_document,doc_id); return RedirectResponse("/teacher/documents",302)

@router.post("/documents/{doc_id}/delete")
async def delete_document(doc_id:int, request:Request, user=Depends(require_role("teacher")), db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    doc=db.get(Document,doc_id)
    if not doc or doc.uploaded_by != user.id:
        raise HTTPException(404,"Document not found.")
    published=db.query(Assignment).join(AssignmentDocument).filter(AssignmentDocument.document_id==doc_id,Assignment.status=="published").first()
    if published: raise HTTPException(400,"Document is used by a published assignment and cannot be deleted.")
    collection=get_collection()
    try:
        got=collection.get(where={"document_id":doc_id})
        if got["ids"]:
            collection.delete(ids=got["ids"])
    except Exception as exc:
        raise HTTPException(503, f"Could not remove indexed passages. Document was not deleted: {exc}") from exc
    Path(doc.file_path).unlink(missing_ok=True) if doc.file_path else None
    db.delete(doc); db.commit(); return RedirectResponse("/teacher/documents",302)

@router.get("/questions")
async def questions(request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db),error:str|None=None):
    return page(request,"teacher/questions.html",user,db,assignments=db.query(Assignment).order_by(Assignment.created_at.desc()).all(),
                documents=db.query(Document).filter(Document.uploaded_by==user.id,Document.indexing_status=="Indexed").all(),error=error)

@router.post("/assignments")
async def save_assignment(request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    title=str(form.get("title","")).strip()
    action=str(form.get("action","draft"))
    selected_ids=[]
    try:
        selected_ids=[int(value) for value in form.getlist("document_ids")]
    except (TypeError,ValueError):
        return RedirectResponse("/teacher/questions?error=Select+valid+reading+documents.",303)
    questions_to_save=[]
    i=0
    while f"question_{i}" in form:
        text=str(form.get(f"question_{i}","")).strip()
        if text:
            try:
                marks=float(form.get(f"marks_{i}",10))
            except (TypeError,ValueError):
                return RedirectResponse("/teacher/questions?error=Enter+valid+marks+for+each+question.",303)
            if marks <= 0:
                return RedirectResponse("/teacher/questions?error=Question+marks+must+be+greater+than+zero.",303)
            questions_to_save.append((i+1,text,marks))
        i+=1
    if not title:
        return RedirectResponse("/teacher/questions?error=Assignment+title+is+required.",303)
    if action=="publish":
        if not selected_ids:
            return RedirectResponse("/teacher/questions?error=Choose+at+least+one+indexed+reading+document.",303)
        if not questions_to_save:
            return RedirectResponse("/teacher/questions?error=Add+at+least+one+question+before+publishing.",303)
        valid_ids={d.id for d in db.query(Document).filter(
            Document.id.in_(selected_ids),
            Document.uploaded_by==user.id,
            Document.indexing_status=="Indexed",
        ).all()}
        if valid_ids != set(selected_ids):
            return RedirectResponse("/teacher/questions?error=One+or+more+documents+are+not+indexed+or+available.",303)
    due=None
    if form.get("due_date"):
        try:
            due=datetime.fromisoformat(str(form["due_date"]))
        except ValueError:
            return RedirectResponse("/teacher/questions?error=Enter+a+valid+due+date.",303)
    assignment=Assignment(title=title,description=str(form.get("description","")),due_date=due,
                          allow_revisions=str(form.get("allow_revisions",""))=="on",
                          status="published" if action=="publish" else "draft",created_by=user.id)
    db.add(assignment); db.flush()
    for document_id in selected_ids:
        document=db.get(Document,document_id)
        if document:
            assignment.documents.append(document)
    for order,text,marks in questions_to_save:
        db.add(Question(assignment_id=assignment.id,question_text=text,question_order=order,
                        max_marks=marks,created_by=user.id))
    db.commit(); return RedirectResponse("/teacher/questions",302)

@router.post("/assignments/{assignment_id}/documents")
async def attach_assignment_documents(assignment_id:int,request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    assignment=db.get(Assignment,assignment_id)
    if not assignment or assignment.created_by!=user.id: raise HTTPException(404)
    if assignment.documents:
        raise HTTPException(400,"Reading documents are already assigned; existing evidence links were not changed.")
    try:
        document_ids=[int(value) for value in form.getlist("document_ids")]
    except (TypeError,ValueError):
        raise HTTPException(400,"Select valid indexed documents.")
    if not document_ids:
        raise HTTPException(400,"Select at least one indexed reading document.")
    selected=db.query(Document).filter(
        Document.id.in_(document_ids),
        Document.uploaded_by==user.id,
        Document.indexing_status=="Indexed",
    ).all()
    if len({document.id for document in selected})!=len(set(document_ids)):
        raise HTTPException(400,"One or more selected documents are not indexed or available.")
    completed=db.query(Submission).join(Question).filter(
        Question.assignment_id==assignment.id,
        Submission.audit_status.in_(["completed","completed_with_flags"]),
    ).first()
    if completed:
        raise HTTPException(400,"Source documents cannot be added after an audit has completed.")
    assignment.documents.extend(selected)
    db.commit()
    return RedirectResponse("/teacher/questions",302)

@router.post("/questions/{question_id}/keypoints/generate")
async def generate_points(question_id:int,request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    question=db.get(Question,question_id)
    if not question: raise HTTPException(404)
    try:
        ensure_models()
        doc_ids=[d.id for d in question.assignment.documents]
        passages=retrieve(question.question_text,doc_ids,settings.top_k)
        if not passages: raise HTTPException(400,"No relevant evidence retrieved from the assigned documents.")
        result=generate_key_points(question.question_text,passages)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Key points could not be generated: {exc}") from exc
    for k in list(question.key_points): db.delete(k)
    db.flush()
    for k in result.key_points:
        db.add(QuestionKeyPoint(question_id=question.id,point_text=k.text,point_order=k.id,
                                source_chunk_ids=k.evidence_ids,is_teacher_edited=False))
    db.commit(); return RedirectResponse("/teacher/questions",302)

@router.get("/reports")
async def reports(request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    return page(request,"teacher/reports.html",user,db,rows=build_report_rows(db))

def build_report_rows(db:Session):
    rows=[]
    for submission in db.query(Submission).order_by(Submission.submitted_at.desc()).all():
        question=db.get(Question,submission.question_id)
        student=db.get(User,submission.student_id)
        grade=db.query(Grade).filter(Grade.submission_id==submission.id).first()
        flagged=db.query(Evaluation).join(Claim).filter(
            Claim.submission_id==submission.id,Evaluation.review_required==True
        ).count()>0
        rows.append({
            "submission":submission,
            "student":student,
            "question":question,
            "assignment":question.assignment if question else None,
            "grade":grade,
            "flagged":flagged or submission.audit_status=="completed_with_flags",
        })
    return rows

@router.get("/reports/table")
async def reports_table(request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="teacher/_reports_table.html",
        context={"rows":build_report_rows(db)},
    )

@router.get("/reports/{submission_id}")
async def report_view(submission_id:int,request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    submission=db.get(Submission,submission_id)
    if not submission: raise HTTPException(404)
    claim_reports=claim_report_rows(db,submission_id)
    grade=db.query(Grade).filter(Grade.submission_id==submission_id).first()
    return page(request,"teacher/report_detail.html",user,db,submission=submission,question=db.get(Question,submission.question_id),
                student=db.get(User,submission.student_id),claim_reports=claim_reports,grade=grade,
                contradiction_penalty=settings.contradiction_penalty)

@router.post("/reports/{submission_id}/retry")
async def retry_submission(submission_id:int,request:Request,background_tasks:BackgroundTasks,
                           user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    submission=db.get(Submission,submission_id)
    if not submission: raise HTTPException(404)
    try:
        reset_failed_submission(db,submission)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    background_tasks.add_task(run_audit,submission.id)
    return RedirectResponse(f"/teacher/reports/{submission.id}",302)

@router.post("/reports/{submission_id}/override")
async def override(submission_id:int,request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    grade=db.query(Grade).filter(Grade.submission_id==submission_id).first()
    if not grade: raise HTTPException(404)
    grade.teacher_marks=float(form["teacher_marks"]); grade.teacher_feedback=str(form["teacher_feedback"])
    grade.overridden_by=user.id; grade.overridden_at=datetime.utcnow(); db.commit()
    return RedirectResponse(f"/teacher/reports/{submission_id}",302)

@router.post("/reports/{submission_id}/release")
async def release(submission_id:int,request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    grade=db.query(Grade).filter(Grade.submission_id==submission_id).first()
    if not grade: raise HTTPException(404)
    grade.released_to_student=True; db.commit(); return RedirectResponse(f"/teacher/reports/{submission_id}",302)

@router.get("/students")
async def students(request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    return page(request,"teacher/students.html",user,db,students=db.query(User).filter(User.role=="student").order_by(User.name).all())

@router.post("/students")
async def create_student(request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    from auth.hashing import hash_password
    email=str(form["email"]).strip().lower()
    if db.query(User).filter(User.email==email).first(): raise HTTPException(400,"A user with this email already exists.")
    db.add(User(name=str(form["name"]).strip(),email=email,password_hash=hash_password(str(form["password"])),role="student"))
    db.commit(); return RedirectResponse("/teacher/students",302)

@router.post("/students/{student_id}/deactivate")
async def deactivate_student(student_id:int,request:Request,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    student=db.get(User,student_id); student.is_active=False; db.commit(); return RedirectResponse("/teacher/students",302)
