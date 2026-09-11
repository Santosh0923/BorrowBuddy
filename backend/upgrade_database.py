"""Apply migrations with backup and verify preservation of all legacy values."""
from sqlalchemy import text
from database import engine
from migrate import migrate


def snapshot():
    with engine.connect() as conn:
        return {table: {row['id']: dict(row) for row in conn.execute(text('SELECT * FROM '+table)).mappings()}
                for table in ('users','resources','borrow_requests','request_history')}


if __name__ == '__main__':
    before = snapshot()
    migrate()
    after = snapshot()
    for table, rows in before.items():
        assert set(rows) == set(after[table]), 'Record IDs changed: '+table
        for id, row in rows.items():
            for column, value in row.items():
                expected = value
                if table == 'users' and column == 'role' and value == 'staff':
                    expected = 'faculty'
                if table == 'borrow_requests' and column == 'status':
                    expected = {'Returned':'Completed','Returned - Pending Inspection':'Returned Pending Inspection'}.get(value,value)
                if table == 'request_history' and column in ('old_status','new_status') and value == 'Returned - Pending Inspection':
                    expected = 'Returned Pending Inspection'
                assert after[table][id][column] == expected, f'Unexpected change: {table}.{column} #{id}'
        print(f'Preservation verified: {table}, {len(rows)} rows; original values retained except documented status mapping')
    print('Database upgrade complete. Existing passwords and inventory quantities preserved.')
