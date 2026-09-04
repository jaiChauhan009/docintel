from __future__ import annotations

import os
import uuid

# --- Environment MUST be set before importing anything under app.* ----------
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_docintel.db")
os.environ.setdefault("EVENT_BUS", "fake")
os.environ.setdefault("STORAGE_BACKEND", "memory")
os.environ.setdefault("OCR_PROVIDER", "plaintext")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MAX_PROCESSING_ATTEMPTS", "3")
os.environ.setdefault("RETRY_BACKOFF_BASE_SECONDS", "0")
os.environ.setdefault("WEBHOOK_BACKOFF_BASE_SECONDS", "0")
os.environ.setdefault("RATE_LIMIT_REQUESTS", "100000")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.deps import get_current_user
from app.db.session import SessionFactory, engine, get_session
from app.integrations.events import InMemoryEventPublisher, set_event_publisher
from app.integrations.llm.fake_client import FakeLLMClient
from app.integrations.ocr.tesseract import PlainTextOCRProvider
from app.integrations.storage import get_storage
from app.main import app
from app.models import Base
from app.services.processing_service import DocumentProcessor

pytest_plugins = ()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_schema):
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"DELETE FROM {table.name}"))
    get_storage()._objects.clear()  # type: ignore[attr-defined]
    yield


@pytest_asyncio.fixture
async def session():
    async with SessionFactory() as s:
        yield s


@pytest.fixture
def event_bus() -> InMemoryEventPublisher:
    bus = InMemoryEventPublisher()
    set_event_publisher(bus)
    yield bus
    set_event_publisher(None)


@pytest_asyncio.fixture
async def client(event_bus):
    async def _override_session():
        async with SessionFactory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Worker helpers
# --------------------------------------------------------------------------- #
class WorkerRunner:
    def __init__(self, bus: InMemoryEventPublisher):
        self.bus = bus
        self.ocr = PlainTextOCRProvider()
        self.llm = FakeLLMClient()
        self.max_rounds = 20

    async def drain(self, *, ocr=None, llm=None) -> list[str]:
        outcomes: list[str] = []
        rounds = 0
        while not self.bus.queue.empty() and rounds < self.max_rounds:
            rounds += 1
            event = await self.bus.queue.get()
            async with SessionFactory() as s:
                proc = DocumentProcessor(
                    s,
                    ocr=ocr or self.ocr,
                    llm=llm or self.llm,
                    storage=get_storage(),
                    publisher=self.bus,
                )
                outcomes.append(await proc.process_event(event.to_dict()))
        return outcomes


@pytest.fixture
def worker(event_bus) -> WorkerRunner:
    return WorkerRunner(event_bus)


# --------------------------------------------------------------------------- #
# Auth helpers
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def user_factory(client):
    created = []

    async def _make(email: str | None = None, password: str = "hunter2pass"):
        email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Test User"},
        )
        assert resp.status_code == 201, resp.text
        token = resp.json()["access_token"]
        created.append(email)
        return {"email": email, "password": password, "token": token,
                "headers": {"Authorization": f"Bearer {token}"}}

    return _make


@pytest_asyncio.fixture
async def auth(user_factory):
    return await user_factory()


def upload_file(name: str = "invoice_sample.txt", content: bytes | None = None):
    import pathlib

    if content is None:
        p = pathlib.Path(__file__).parent.parent / "samples" / name
        content = p.read_bytes()
    return {"file": (name, content, "text/plain")}
