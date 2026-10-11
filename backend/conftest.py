"""
Root conftest: guarantee that a minimal DATABASE_URL is present before any
module-level import of app.core.config.settings.  Tests that use the real
database must supply their own connection string via the AUTH_TEST_POSTGRES_URL
environment variable or their own fixture.

This conftest does NOT connect to any database; it only satisfies the pydantic
required-field validation so that the test suite can be imported without a
local .env file.
"""
import os

# Use a safe SQLite in-memory fallback ONLY when the environment does not
# already provide a DATABASE_URL.  A real PostgreSQL URL in .env or the
# shell environment always takes priority.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
