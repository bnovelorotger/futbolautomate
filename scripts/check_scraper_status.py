from app.db.session import session_scope
from sqlalchemy import text

with session_scope() as s:
    runs = s.execute(text(
        "SELECT competition_code, source_name, status, started_at, records_found, records_inserted, records_updated, error_message "
        "FROM scraper_runs ORDER BY started_at DESC LIMIT 20"
    )).fetchall()
    print(f"{'DATE':<18} {'COMPETITION':<35} {'SOURCE':<12} {'STATUS':<10} found  ins  upd  err")
    print("-" * 110)
    for r in runs:
        err = (r[7] or "")[:40] if r[7] else ""
        print(f"{str(r[3])[:16]:<18} {str(r[0]):<35} {str(r[1]):<12} {str(r[2]):<10} {r[4]:<6} {r[5]:<4} {r[6]:<4} {err}")
