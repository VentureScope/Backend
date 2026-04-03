# Common Issues and Solutions

This document contains solutions to common issues encountered during development and testing of the VentureScope Backend API.

## Test Infrastructure Issues

### Issue 1: Asyncio Event Loop Error

**Error:**
```
RuntimeError: Task <Task pending...> got Future <Future pending> attached to a different loop
```

**Cause:**
The test suite had a deprecated session-scoped `event_loop` fixture that conflicted with pytest-asyncio's automatic event loop management.

**Solution:**
Remove custom event_loop fixtures from `tests/conftest.py` and let pytest-asyncio handle event loop creation automatically. Modern pytest-asyncio (0.21.0+) manages event loops per test function automatically.

**Fixed in:** `tests/conftest.py` - Removed deprecated custom event_loop fixture

---

### Issue 2: Database Session Transaction Errors

**Error:**
```
InvalidRequestError: Can't operate on closed transaction inside context manager
```

**Cause:**
The `db_session` fixture had overly complex nested transaction management using `transaction.begin()` and `transaction.rollback()` that conflicted with SQLAlchemy 2.0's transaction handling.

**Solution:**
Simplified the database session fixture to use `sessionmaker` directly with the engine without explicit nested transactions. Let SQLAlchemy handle transaction management automatically.

**Fixed in:** `tests/conftest.py` - Simplified db_session fixture

---

### Issue 3: Bcrypt Version Compatibility Warning

**Error:**
```
(trapped) error reading bcrypt version
```

**Cause:**
Passlib 1.7.4 is incompatible with bcrypt 4.3.0+ due to changes in bcrypt's version string format.

**Solution:**
Pin bcrypt to version 4.0.1 in `requirements.txt` until passlib releases a compatible update.

```txt
bcrypt==4.0.1
```

**Fixed in:** `requirements.txt` - Pinned bcrypt to 4.0.1

**References:**
- [Passlib Issue #148](https://foss.heptapod.net/python-libs/passlib/-/issues/148)
- [Bcrypt Changelog](https://github.com/pyca/bcrypt/blob/main/CHANGELOG.rst)

---

### Issue 4: Datetime Deprecation Warning

**Error:**
```
DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version.
```

**Cause:**
`datetime.utcnow()` is deprecated in Python 3.12+ in favor of timezone-aware datetime objects.

**Solution:**
Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`:

```python
# Old (deprecated)
from datetime import datetime
expire = datetime.utcnow() + timedelta(minutes=15)

# New (recommended)
from datetime import datetime, timezone, timedelta
expire = datetime.now(timezone.utc) + timedelta(minutes=15)
```

**Fixed in:** `app/core/security.py` - Updated to use timezone-aware datetime

---

### Issue 5: SQLAlchemy 2.0 Deprecation Warnings

**Warning:**
```
RemovedIn20Warning: The 'autocommit' parameter to Session is deprecated
RemovedIn20Warning: The 'autoflush' parameter to Session is deprecated
```

**Cause:**
SQLAlchemy 2.0 removed the `autocommit` and `autoflush` parameters from `sessionmaker` in favor of explicit transaction control.

**Solution:**
Remove `autocommit` and `autoflush` parameters from sessionmaker configuration:

```python
# Old (deprecated)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# New (recommended)
SessionLocal = sessionmaker(bind=engine)
```

**Fixed in:** `tests/conftest.py` - Removed deprecated sessionmaker parameters

---

### Issue 6: Pytest Configuration Format

**Warning:**
```
pytest.ini: [tool:pytest] section is deprecated, use [pytest] instead
```

**Cause:**
The `[tool:pytest]` section header is deprecated in favor of `[pytest]`.

**Solution:**
Update `pytest.ini` to use the new format:

```ini
# Old (deprecated)
[tool:pytest]
testpaths = tests

# New (recommended)
[pytest]
testpaths = tests
```

**Fixed in:** `pytest.ini` - Updated section header to `[pytest]`

---

### Issue 7: Bash Script Grep Failure with set -e

**Error:**
Script exits when grep doesn't find a match due to `set -e` being enabled.

**Cause:**
`grep` returns exit code 1 when no matches are found, which causes the script to exit when `set -e` is enabled.

**Solution:**
Add `|| true` to grep commands that may legitimately return no matches:

```bash
# Old (fails with set -e)
grep "pattern" file.txt

# New (safe with set -e)
grep "pattern" file.txt || true
```

**Fixed in:** `scripts/init_db.sh` - Added `|| true` to grep command

---

## Docker and Environment Issues

### Issue 8: Test Database Not Found

**Error:**
```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) FATAL:  database "venturescope_test" does not exist
```

**Solution:**
Create the test database before running tests:

```bash
# Start database services
docker compose up -d postgres redis

# Create test database
docker compose exec -T postgres psql -U venturescope -d postgres -c "CREATE DATABASE venturescope_test;"
```

See `docs/testing/commands.md` for complete test setup instructions.

---

## Best Practices

1. **Always use timezone-aware datetime objects** - Use `datetime.now(timezone.utc)` instead of `datetime.utcnow()`
2. **Pin critical dependencies** - Pin dependencies like bcrypt that have known compatibility issues
3. **Let pytest-asyncio manage event loops** - Don't create custom event_loop fixtures
4. **Simplify transaction management** - Let SQLAlchemy handle transactions automatically
5. **Keep pytest configuration up to date** - Use modern pytest.ini format
6. **Handle grep failures in bash scripts** - Use `|| true` when grep may return no matches
7. **Use proper test database setup** - Always create test database before running integration tests

## See Also

- [Testing Commands](../testing/commands.md) - How to run tests
- [Testing Strategy](../testing/strategy.md) - Overall testing approach
- [Database Setup](../database/setup.md) - Database configuration and initialization
