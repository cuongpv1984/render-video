from pathlib import Path
from .db import transaction

if __name__=="__main__":
    path=Path(__file__).resolve().parents[3]/"db"/"001_app.sql"
    with transaction() as cur:cur.execute(path.read_text(encoding="utf-8"))
    print("Runtime schema initialized")
