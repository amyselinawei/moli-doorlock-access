from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, String, TIMESTAMP, func, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
import os



app = FastAPI()

# 掛載 static 目錄，讓 /static/style.css 可以被前端載入
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    student_id = Column(String(20), primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    rfid_uid = Column(String(50), unique=True, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class AccessLog(Base):
    __tablename__ = "access_logs"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String(20), ForeignKey("users.student_id"), nullable=False)
    rfid_uid = Column(String(50), nullable=False)
    action = Column(String(10), nullable=False)  # 'entry' / 'exit'
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now())

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "error": None}
    )

@app.post("/register")
async def register_post(
    request: Request,
    student_id: str = Form(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    student_id = student_id.strip()
    name = name.strip()

    if db.query(User).filter(User.student_id == student_id).first():
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "❌ 學號已註冊，請直接刷卡進門"},
        )

    try:
        user = User(student_id=student_id, name=name)
        db.add(user)
        db.commit()
        return RedirectResponse(
            url=f"/success?student_id={student_id}", status_code=303
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="註冊失敗")

@app.get("/success", response_class=HTMLResponse)
async def success_page(
    request: Request, student_id: str, db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.student_id == student_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用戶不存在")
    return templates.TemplateResponse(
        "success.html", {"request": request, "user": user}
    )

@app.post("/rfid_scan")
async def rfid_scan(
    student_id: str = Form(...),
    rfid_uid: str = Form(...),
    action: str = Form(default="entry"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.student_id == student_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用戶不存在")

    if not user.rfid_uid:
        user.rfid_uid = rfid_uid
        db.commit()
    elif user.rfid_uid != rfid_uid:
        raise HTTPException(status_code=400, detail="RFID 與註冊資料不符")

    log = AccessLog(student_id=student_id, rfid_uid=rfid_uid, action=action)
    db.add(log)
    db.commit()

    return JSONResponse({"status": "success", "message": f"{action} 成功"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
