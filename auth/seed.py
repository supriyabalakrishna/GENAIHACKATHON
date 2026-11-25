from database.connection import SessionLocal, engine
from database.models import Base, User
from auth.hashing import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()
accounts = [
    ("Dr. Maya Chen", "teacher@educite.local", "TeacherDemo!2026", "teacher"),
    ("Aarav Student", "aarav@educite.local", "StudentDemo!2026", "student"),
    ("Mina Student", "mina@educite.local", "StudentDemo!2026", "student"),
    ("Leo Student", "leo@educite.local", "StudentDemo!2026", "student"),
]
for name, email, password, role in accounts:
    if not db.query(User).filter(User.email == email).first():
        db.add(User(name=name, email=email, password_hash=hash_password(password), role=role))
db.commit()
db.close()
print("Seed accounts created.")
