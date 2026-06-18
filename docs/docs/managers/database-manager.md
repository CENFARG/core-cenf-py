# DatabaseManager (M08)

Transactions and generic repositories. Always use `async with db.transaction() as tx:` — never raw sessions.
