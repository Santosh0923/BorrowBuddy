from getpass import getpass

import models
from auth import hash_password
from database import SessionLocal


db = SessionLocal()

try:
    name = input("Admin name: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass("Admin password: ")

    existing_user = (
        db.query(models.User)
        .filter(models.User.email == email)
        .first()
    )

    if existing_user:
        print("A user with this email already exists.")

    else:
        admin = models.User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role="admin"
        )

        db.add(admin)
        db.commit()

        print("ADMIN ACCOUNT CREATED SUCCESSFULLY")

finally:
    db.close()