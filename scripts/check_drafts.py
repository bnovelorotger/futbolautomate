from app.db.session import session_scope
from sqlalchemy import text

with session_scope() as s:
    rows = s.execute(text(
        "SELECT content_type, competition_slug, DATE(created_at) as created_date, COUNT(*) as cnt "
        "FROM content_candidates WHERE status = 'draft' "
        "GROUP BY content_type, competition_slug, DATE(created_at) "
        "ORDER BY created_date DESC, cnt DESC LIMIT 30"
    )).fetchall()
    print(f"{'TYPE':<30} {'COMPETITION':<35} {'DATE':<12} CNT")
    print("-" * 85)
    for r in rows:
        print(f"{r[0]:<30} {r[1]:<35} {str(r[2]):<12} {r[3]}")

    total = s.execute(text("SELECT COUNT(*) FROM content_candidates WHERE status = 'draft'")).scalar()
    print(f"\nTotal drafts: {total}")

    # Last scraper runs
    print("\n--- Last scraper runs ---")
    runs = s.execute(text(
        "SELECT competition_code, source_name, status, started_at, records_found "
        "FROM scraper_runs ORDER BY started_at DESC LIMIT 15"
    )).fetchall()
    for r in runs:
        print(f"{str(r[3])[:16]}  {str(r[0]):<35} {str(r[1]):<15} {str(r[2]):<10} found={r[4]}")
