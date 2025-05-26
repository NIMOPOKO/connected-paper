"""
コマンドラインから一度だけ実行し、最初の管理者を作成します。
Usage:
    python create_admin.py <username> <password>
"""
import sys
from db import SessionLocal, init_db, User
from auth_utils import hash_password

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python create_admin.py <username> <password>")
        sys.exit(1)
    username, password = sys.argv[1], sys.argv[2]
    init_db()
    db = SessionLocal()
    if db.query(User).filter(User.username == username).first():
        print(f"ユーザー '{username}' は既に存在します。")
        sys.exit(1)
    admin = User(
        username=username,
        hashed_password=hash_password(password),
        is_admin=True
    )
    db.add(admin)
    db.commit()
    db.close()
    print(f"管理者ユーザー '{username}' を作成しました。")