import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://teamtasks:teamtasks@localhost:5432/teamtasks")
SECRET_KEY = os.getenv("SECRET_KEY", "development-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 480

class Base(DeclarativeBase): pass
class Role(str, Enum): admin = "admin"; member = "member"
class TaskStatus(str, Enum): todo = "todo"; in_progress = "in_progress"; done = "done"
class Priority(str, Enum): low = "low"; medium = "medium"; high = "high"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(SAEnum(Role), default=Role.member)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.todo)
    priority: Mapped[Priority] = mapped_column(SAEnum(Priority), default=Priority.medium)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    project: Mapped[Project] = relationship(back_populates="tasks")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="auth/login")

class UserCreate(BaseModel): name: str = Field(min_length=2, max_length=100); email: EmailStr; password: str = Field(min_length=8)
class UserOut(BaseModel): model_config = ConfigDict(from_attributes=True); id: int; name: str; email: EmailStr; role: Role
class Token(BaseModel): access_token: str; token_type: str = "bearer"
class ProjectIn(BaseModel): name: str = Field(min_length=2, max_length=120); description: Optional[str] = None
class ProjectOut(ProjectIn): model_config = ConfigDict(from_attributes=True); id: int; owner_id: int; created_at: datetime
class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=180); description: Optional[str] = None; status: TaskStatus = TaskStatus.todo; priority: Priority = Priority.medium
    assignee_id: Optional[int] = None; due_date: Optional[datetime] = None
class TaskOut(TaskIn): model_config = ConfigDict(from_attributes=True); id: int; project_id: int; created_at: datetime

app = FastAPI(title="Team Tasks API", version="1.0.0", description="API para proyectos y tareas colaborativas.")
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup(): Base.metadata.create_all(engine)
def db_session():
    db = SessionLocal()
    try: yield db
    finally: db.close()
def token_for(user: User): return jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)}, SECRET_KEY, algorithm=ALGORITHM)
def current_user(token: str = Depends(oauth2), db: Session = Depends(db_session)):
    try: uid = int(jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub"))
    except (JWTError, TypeError, ValueError): raise HTTPException(status_code=401, detail="Token inválido")
    user = db.get(User, uid)
    if not user: raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user
def project_or_404(project_id: int, db: Session):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return project
def can_manage(project: Project, user: User):
    if user.role != Role.admin and project.owner_id != user.id: raise HTTPException(status_code=403, detail="No tienes permisos para esta acción")

@app.get("/health")
def health(): return {"status": "ok"}
@app.post("/auth/register", response_model=UserOut, status_code=201, tags=["auth"])
def register(payload: UserCreate, db: Session = Depends(db_session)):
    if db.scalar(select(User).where(User.email == payload.email)): raise HTTPException(409, "El correo ya está registrado")
    role = Role.admin if not db.scalar(select(User.id).limit(1)) else Role.member
    user = User(name=payload.name, email=payload.email, password_hash=pwd.hash(payload.password), role=role); db.add(user); db.commit(); db.refresh(user); return user
@app.post("/auth/login", response_model=Token, tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(db_session)):
    user = db.scalar(select(User).where(User.email == form.username))
    if not user or not pwd.verify(form.password, user.password_hash): raise HTTPException(status_code=401, detail="Credenciales incorrectas", headers={"WWW-Authenticate":"Bearer"})
    return {"access_token": token_for(user)}
@app.get("/auth/me", response_model=UserOut, tags=["auth"])
def me(user: User = Depends(current_user)): return user

@app.get("/projects", response_model=list[ProjectOut], tags=["projects"])
def list_projects(user: User = Depends(current_user), db: Session = Depends(db_session)): return db.scalars(select(Project).order_by(Project.created_at.desc())).all()
@app.post("/projects", response_model=ProjectOut, status_code=201, tags=["projects"])
def create_project(payload: ProjectIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    project = Project(**payload.model_dump(), owner_id=user.id); db.add(project); db.commit(); db.refresh(project); return project
@app.put("/projects/{project_id}", response_model=ProjectOut, tags=["projects"])
def update_project(project_id: int, payload: ProjectIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    project = project_or_404(project_id, db); can_manage(project, user)
    for key, value in payload.model_dump().items(): setattr(project, key, value)
    db.commit(); db.refresh(project); return project
@app.delete("/projects/{project_id}", status_code=204, tags=["projects"])
def delete_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    project = project_or_404(project_id, db); can_manage(project, user); db.delete(project); db.commit()

@app.get("/projects/{project_id}/tasks", response_model=list[TaskOut], tags=["tasks"])
def list_tasks(project_id: int, status_filter: Optional[TaskStatus] = Query(None, alias="status"), priority: Optional[Priority] = None, assignee_id: Optional[int] = None, user: User = Depends(current_user), db: Session = Depends(db_session)):
    project_or_404(project_id, db); stmt = select(Task).where(Task.project_id == project_id)
    if status_filter: stmt = stmt.where(Task.status == status_filter)
    if priority: stmt = stmt.where(Task.priority == priority)
    if assignee_id: stmt = stmt.where(Task.assignee_id == assignee_id)
    return db.scalars(stmt.order_by(Task.created_at.desc())).all()
@app.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=201, tags=["tasks"])
def create_task(project_id: int, payload: TaskIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    project = project_or_404(project_id, db); can_manage(project, user)
    if payload.assignee_id and not db.get(User, payload.assignee_id): raise HTTPException(422, "Responsable no encontrado")
    task = Task(**payload.model_dump(), project_id=project_id); db.add(task); db.commit(); db.refresh(task); return task
@app.put("/tasks/{task_id}", response_model=TaskOut, tags=["tasks"])
def update_task(task_id: int, payload: TaskIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    task = db.get(Task, task_id)
    if not task: raise HTTPException(404, "Tarea no encontrada")
    can_manage(task.project, user)
    for key, value in payload.model_dump().items(): setattr(task, key, value)
    db.commit(); db.refresh(task); return task
@app.delete("/tasks/{task_id}", status_code=204, tags=["tasks"])
def delete_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    task = db.get(Task, task_id)
    if not task: raise HTTPException(404, "Tarea no encontrada")
    can_manage(task.project, user); db.delete(task); db.commit()

