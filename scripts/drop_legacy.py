import os
import psycopg2

db_url = os.getenv('DATABASE_URL', '')
if not db_url:
    raise SystemExit('ERROR: DATABASE_URL environment variable is not set. Set it before running this script.')
conn = psycopg2.connect(db_url)
conn.autocommit = True
cur = conn.cursor()
legacy = ['products','sales','customers','campaigns','reviews','semantic_metrics','semantic_dimensions','queries','insights','evaluation_cases','evaluation_runs','system_events']
for t in legacy:
    try:
        cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
        print(f'Dropped: {t}')
    except Exception as e:
        print(f'Skip {t}: {str(e)[:60]}')
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print(f'\nRemaining ({len(tables)}):')
for t in tables:
    print(f'  {t}')
conn.close()
