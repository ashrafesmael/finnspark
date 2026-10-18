import pytest

from app.database import engine, Base
from app.main import _migrate


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Ensure the test database has the full current schema.

    Tests run against a disposable copy of the live database, which may
    predate columns added by _migrate(); startup events don't fire for a
    module-level TestClient, so apply create_all + migrations here instead.
    """
    Base.metadata.create_all(bind=engine)
    _migrate(engine)
    yield
