"""使用合成记录测试 API 与 SQL 契约，不需要本地数据库。"""
from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.corpus import repository
from backend.corpus.connection import get_connection

ONE = UUID("11111111-1111-4111-8111-111111111111")
TWO = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import backend.app as api
    with TestClient(api.app) as test_client:
        yield test_client
    api.app.dependency_overrides.clear()


def summary(identity=ONE, order=1, cipai="念奴娇"):
    return {
        "id": identity, "source_order": order,
        "collection": "合成词集", "author": "词人甲", "cipai": cipai,
        "title": None, "yusheng_title": "合成寓声", "incipit": "合成起句。",
        "review_status": "imported_unreviewed",
    }


def full_record():
    return {
        **{key: val for key, val in summary().items() if key != "incipit"},
        "body_segments": ["合成上段。", "合成下段。"],
        "prefaces": [], "text_version": 1,
    }


class FakeConnection:
    """最小游标替身，只用于核对 SQL 与绑定参数。"""
    def __init__(self, *, pages=None, details=None, count=2):
        self.pages = pages if pages is not None else [summary(), summary(TWO, 2)]
        self.details = details or {}
        self.count = count
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "COUNT(*)" in sql:
            return SimpleNamespace(fetchone=lambda: {"total": self.count})
        if "FROM poems WHERE id =" in sql:
            return SimpleNamespace(fetchone=lambda: self.details.get(params[0]))
        if "ORDER BY source_order" in sql:
            return SimpleNamespace(fetchall=lambda: self.pages)
        raise AssertionError("Unexpected SQL in read-only repository")


def override_connection(client, fake):
    import backend.app as api
    api.app.dependency_overrides[get_connection] = lambda: fake


def test_catalog_page_filters_order_and_no_private_data(client):
    fake = FakeConnection(pages=[summary()], count=2)
    override_connection(client, fake)
    response = client.get(
        "/api/poems",
        params={"author": "词人甲", "cipai": "念奴娇", "q": "合成",
                "limit": 1, "offset": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["limit"] == 1 and data["offset"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == str(ONE)
    assert "body_segments" not in data["items"][0]
    assert data["items"][0]["yusheng_title"] == "合成寓声"
    assert "yusheng" not in data["items"][0]
    assert "original_segments" not in data["items"][0]
    assert "source_locator" not in data["items"][0]
    assert len(fake.calls) == 2
    for sql, params in fake.calls:
        assert "FROM poems" in sql
        assert "poem_source_texts" not in sql
        assert "source_sha256" not in sql
        assert "author = %s" in sql
        assert "(cipai = %s OR yusheng_title = %s)" in sql
        assert tuple(params[:3]) == ("词人甲", "念奴娇", "念奴娇")
        assert tuple(params[3:]) == ("合成",) * 5 or (
            tuple(params[3:]) == ("合成",) * 5 + (1, 1)
        )
        assert "合成" not in sql
    assert "ORDER BY source_order LIMIT %s OFFSET %s" in fake.calls[1][0]
    assert fake.calls[1][1][-2:] == (1, 1)


def test_catalog_defaults_and_empty_result(client):
    fake = FakeConnection(pages=[], count=0)
    override_connection(client, fake)
    response = client.get("/api/poems")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    assert fake.calls[0][1] == ()
    assert fake.calls[1][1] == (20, 0)


@pytest.mark.parametrize("query", [
    "limit=0", "limit=101", "offset=-1", "limit=abc",
    "q=" + "a" * 101,
])
def test_invalid_pagination_and_query_returns_422(client, query):
    # 把 HTTP 参数校验与数据库依赖隔离；FastAPI 可能在报告非法查询参数前
    # 先解析 Depends()。
    override_connection(client, FakeConnection())
    assert client.get("/api/poems?" + query).status_code == 422


def test_detail_returns_only_reader_fields(client):
    fake = FakeConnection(details={ONE: full_record()})
    override_connection(client, fake)
    resp = client.get(f"/api/poems/{ONE}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(ONE)
    assert data["body_segments"] == ["合成上段。", "合成下段。"]
    assert data["prefaces"] == []
    assert data["yusheng_title"] == "合成寓声"
    assert "yusheng" not in data
    assert "original_segments" not in data
    assert "inline_notes" not in data
    assert "lacunae" not in data
    assert "FROM poems WHERE id = %s" in fake.calls[0][0]
    assert fake.calls[0][1] == (ONE,)


def test_detail_not_found_and_invalid_uuid(client):
    fake = FakeConnection()
    override_connection(client, fake)
    assert client.get(f"/api/poems/{ONE}").status_code == 404
    assert client.get("/api/poems/not-a-uuid").status_code == 422


def test_connection_not_configured_is_503(client, monkeypatch):
    import backend.corpus.connection as connection
    monkeypatch.setattr(connection, "load_dotenv", lambda: None)
    monkeypatch.delenv("POETICUS_DATABASE_URL", raising=False)
    response = client.get("/api/poems")
    assert response.status_code == 503
    assert response.json()["detail"] == "作品数据库尚未配置"


def test_connection_failure_is_503_without_leaking_password(client, monkeypatch):
    import backend.corpus.connection as connection
    monkeypatch.setattr(connection, "load_dotenv", lambda: None)
    monkeypatch.setenv(
        "POETICUS_DATABASE_URL",
        "postgresql://poeticus:SECRET_PASSWORD@localhost:5432/poeticus",
    )

    def fail(*args, **kwargs):
        raise psycopg.OperationalError("connection failed; password SECRET_PASSWORD")

    monkeypatch.setattr(connection.psycopg, "connect", fail)
    response = client.get("/api/poems")
    assert response.status_code == 503
    assert response.json()["detail"] == "作品数据库暂时不可用"
    assert "SECRET_PASSWORD" not in response.text


def test_repository_literal_search_and_parameter_binding():
    fake = FakeConnection(pages=[], count=0)
    rows, count = repository.list_poems(
        fake, author=None, cipai=None, q="100%_测试", limit=5, offset=0
    )
    assert rows == [] and count == 0
    assert "STRPOS" in fake.calls[0][0]
    assert "%s" in fake.calls[0][0]
    assert "100%_测试" not in fake.calls[0][0]
    assert fake.calls[0][1] == ("100%_测试",) * 5
    assert fake.calls[1][1][-2:] == (5, 0)


def test_repository_tune_filter_matches_cipai_or_yusheng_without_conflating_fields():
    fake = FakeConnection(pages=[summary()], count=1)
    rows, count = repository.list_poems(
        fake, author="贺铸", cipai="翦朝霞", q=None, limit=20, offset=0,
    )
    assert len(rows) == 1 and count == 1
    for sql, params in fake.calls:
        assert "author = %s" in sql
        assert "(cipai = %s OR yusheng_title = %s)" in sql
        assert "翦朝霞" not in sql
        assert tuple(params[:3]) == ("贺铸", "翦朝霞", "翦朝霞")
    assert fake.calls[0][1] == ("贺铸", "翦朝霞", "翦朝霞")
    assert fake.calls[1][1] == ("贺铸", "翦朝霞", "翦朝霞", 20, 0)


def test_repository_keyword_search_includes_yusheng_and_uses_literal_matching():
    fake = FakeConnection(pages=[], count=0)
    repository.list_poems(
        fake, author=None, cipai=None, q="翦朝霞", limit=20, offset=0,
    )
    sql, params = fake.calls[0]
    assert "STRPOS(LOWER(COALESCE(yusheng_title, '')), LOWER(%s)) > 0" in sql
    assert tuple(params) == ("翦朝霞",) * 5
    assert "翦朝霞" not in sql


def test_repository_space_separated_terms_use_and_across_fields():
    """每词可以匹配不同字段；同一词在允许列间 OR，多词之间 AND。"""
    fake = FakeConnection(pages=[], count=0)
    repository.list_poems(
        fake, author=None, cipai=None, q="  苏轼　念奴娇  大江东去  ",
        limit=20, offset=0,
    )
    sql, params = fake.calls[0]
    assert sql.count("STRPOS") == 15
    assert " AND " in sql
    assert params == ("苏轼",) * 5 + ("念奴娇",) * 5 + ("大江东去",) * 5
    assert fake.calls[1][1] == params + (20, 0)
    assert "大江东去" not in sql


def test_repository_unspaced_query_remains_one_literal_term():
    """未来无空格跨字段组合命中由单独的搜索研究 Issue 决定。"""
    fake = FakeConnection(pages=[], count=0)
    repository.list_poems(
        fake, author=None, cipai=None, q="虞美人春花", limit=20, offset=0,
    )
    sql, params = fake.calls[0]
    assert sql.count("STRPOS") == 5
    assert params == ("虞美人春花",) * 5
