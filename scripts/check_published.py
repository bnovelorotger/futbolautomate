from app.db.session import session_scope
from sqlalchemy import text

with session_scope() as s:
    rows = s.execute(text(
        "SELECT id, content_type, competition_slug, status, external_publication_ref, "
        "external_channel, published_at "
        "FROM content_candidates WHERE id IN (320, 321) ORDER BY id"
    )).fetchall()
    for r in rows:
        print(f"id={r[0]}  {r[1]:<25} {r[2]:<35} status={r[3]}")
        print(f"       channel={r[5]}  ref={r[4]}  published={str(r[6])[:19]}")
        print()
