import pytest

from tests.conftest import upload_file

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def other_users_doc(client, auth, user_factory):
    owner = auth
    up = await client.post("/api/v1/documents", headers=owner["headers"], files=upload_file())
    intruder = await user_factory()
    return up.json()["id"], intruder


async def test_intruder_cannot_read_document(client, other_users_doc):
    doc_id, intruder = other_users_doc
    assert (await client.get(f"/api/v1/documents/{doc_id}", headers=intruder["headers"])).status_code == 404


async def test_intruder_cannot_read_result(client, other_users_doc):
    doc_id, intruder = other_users_doc
    resp = await client.get(f"/api/v1/documents/{doc_id}/result", headers=intruder["headers"])
    assert resp.status_code == 404


async def test_intruder_cannot_delete_document(client, other_users_doc):
    doc_id, intruder = other_users_doc
    assert (await client.delete(f"/api/v1/documents/{doc_id}", headers=intruder["headers"])).status_code == 404


async def test_intruder_cannot_retry_document(client, other_users_doc):
    doc_id, intruder = other_users_doc
    assert (
        await client.post(f"/api/v1/documents/{doc_id}/retry", headers=intruder["headers"])
    ).status_code == 404


async def test_owner_still_has_access(client, auth, other_users_doc):
    doc_id, _ = other_users_doc
    assert (await client.get(f"/api/v1/documents/{doc_id}", headers=auth["headers"])).status_code == 200
