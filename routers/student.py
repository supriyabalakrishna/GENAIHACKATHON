from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import *
from auth.dependencies import require_role
from auth.csrf import ensure_csrf
from core.audit_pipeline import reset_failed_submission
from core.audit_runner import run_audit
from core.report_generator import report_csv, report_json, claim_report_rows
from datetime import datetime

router=APIRouter(prefix="/student")
templates=Jinja2Templates(directory="templates")

def page(request,template,user,db,**context):
    return templates.TemplateResponse(request=request,name=template,context={"user":user,"csrf_token":ensure_csrf(request),**context})

@router.get("/dashboard")
async def dashboard(request:Request,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    assignments=db.query(Assignment).filter(Assignment.status=="published").order_by(Assignment.due_date).all()
    released=db.query(Grade).join(Submission).filter(Submission.student_id==user.id,Grade.released_to_student==True).order_by(Grade.graded_at.desc()).limit(5).all()
    return page(request,"student/dashboard.html",user,db,assignments=assignments,released=released)

@router.get("/assignments")
async def assignments(request:Request,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    items=db.query(Assignment).filter(Assignment.status=="published").order_by(Assignment.due_date).all()
    return page(request,"student/assignments.html",user,db,assignments=items)

@router.get("/assignments/available")
async def available_assignments(request:Request,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    items=db.query(Assignment).filter(Assignment.status=="published").order_by(Assignment.due_date).all()
    return templates.TemplateResponse(
        request=request,
        name="student/_assignment_list.html",
        context={"assignments": items},
    )

@router.get("/assignments/{assignment_id}")
async def assignment_detail(assignment_id:int,request:Request,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    assignment=db.get(Assignment,assignment_id)
    if not assignment or assignment.status!="published": raise HTTPException(404)
    questions=sorted(assignment.questions,key=lambda q:q.question_order)
    return page(request,"student/assignment_detail.html",user,db,assignment=assignment,questions=questions)

@router.post("/submissions")
async def submit_answer(request:Request,background_tasks:BackgroundTasks,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    question_id=int(form["question_id"])
    answer=str(form["answer_text"]).strip()
    if not answer: raise HTTPException(400,"Answer cannot be empty.")
    question=db.get(Question,question_id)
    if not question or question.assignment.status!="published": raise HTTPException(404)
    previous=db.query(Submission).filter(Submission.student_id==user.id,Submission.question_id==question_id).order_by(Submission.submitted_at.desc()).first()
    if previous and not question.assignment.allow_revisions:
        raise HTTPException(400,"A submitted answer is locked for this assignment.")
    submission=Submission(student_id=user.id,question_id=question_id,answer_text=answer,audit_status="queued",
                          revision_of=previous.id if previous and question.assignment.allow_revisions else None)
    db.add(submission); db.commit(); db.refresh(submission)
    background_tasks.add_task(run_audit,submission.id)
    return RedirectResponse(f"/student/submissions/{submission.id}",302)



@router.get("/submissions/{submission_id}")
async def submission_status(submission_id:int,request:Request,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    submission=db.get(Submission,submission_id)
    if not submission or submission.student_id!=user.id: raise HTTPException(404)
    grade=db.query(Grade).filter(Grade.submission_id==submission_id).first()
    return page(request,"student/submission_status.html",user,db,submission=submission,grade=grade)

@router.post("/submissions/{submission_id}/retry")
async def retry_submission(submission_id:int,request:Request,background_tasks:BackgroundTasks,
                           user=Depends(require_role("student")),db:Session=Depends(get_db)):
    form=await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")): raise HTTPException(403)
    submission=db.get(Submission,submission_id)
    if not submission or submission.student_id!=user.id: raise HTTPException(404)
    try:
        reset_failed_submission(db,submission)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    background_tasks.add_task(run_audit,submission.id)
    return RedirectResponse(f"/student/submissions/{submission.id}",302)

@router.get("/results")
async def results(request:Request,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    return page(request,"student/results.html",user,db,rows=result_rows(db,user.id))

def result_rows(db:Session,student_id:int):
    rows=[]
    submissions=db.query(Submission).filter(Submission.student_id==student_id).order_by(Submission.submitted_at.desc()).all()
    for submission in submissions:
        grade=db.query(Grade).filter(Grade.submission_id==submission.id).first()
        question=db.get(Question,submission.question_id)
        rows.append({"submission":submission,"grade":grade,"question":question})
    return rows

@router.get("/results/available")
async def available_results(request:Request,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="student/_results_list.html",
        context={"rows":result_rows(db,user.id)},
    )

@router.get("/results/{submission_id}")
async def result_detail(submission_id:int,request:Request,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    submission=db.get(Submission,submission_id)
    if not submission or submission.student_id!=user.id: raise HTTPException(404)
    grade=db.query(Grade).filter(Grade.submission_id==submission_id).first()
    if not grade or not grade.released_to_student: raise HTTPException(403,"Grade has not been released.")
    claim_reports=claim_report_rows(db,submission_id)
    question=db.get(Question,submission.question_id)
    return page(request,"student/result_detail.html",user,db,submission=submission,grade=grade,claim_reports=claim_reports,question=question)

@router.get("/results/{submission_id}/export.{format}")
async def export_result(submission_id:int,format:str,request:Request,user=Depends(require_role("student")),db:Session=Depends(get_db)):
    submission=db.get(Submission,submission_id)
    if not submission or submission.student_id!=user.id: raise HTTPException(404)
    grade=db.query(Grade).filter(Grade.submission_id==submission_id).first()
    if not grade or not grade.released_to_student: raise HTTPException(403)
    question=db.get(Question,submission.question_id); student=db.get(User,user.id)
    claims=claim_report_rows(db,submission_id)
    report={"student":student.name,"assignment":question.assignment.title,"question":question.question_text,
            "answer":submission.answer_text,"claims":claims,"coverage":grade.key_point_coverage,
            "ai_marks":grade.ai_marks,"max_marks":grade.max_marks,"teacher_marks":grade.teacher_marks,"feedback":grade.teacher_feedback or grade.ai_feedback}
    if format=="csv": return Response(report_csv(report),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=result-{submission_id}.csv"})
    if format=="json": return Response(report_json(report),media_type="application/json",headers={"Content-Disposition":f"attachment; filename=result-{submission_id}.json"})
    raise HTTPException(404)
