def shorten(client, url="https://example.com/page", **extra):
    body = {"url": url}
    body.update(extra)
    return client.post("/shorten", json=body)


class TestShorten:
    def test_shorten_success(self, client):
        res = shorten(client)
        assert res.status_code == 201
        data = res.get_json()
        assert "code" in data and len(data["code"]) == 7
        assert data["url"] == "https://example.com/page"
        assert data["short_url"].endswith(data["code"])
        assert data["expires_at"] is None

    def test_shorten_missing_url(self, client):
        res = client.post("/shorten", json={})
        assert res.status_code == 400

    def test_shorten_rejects_javascript_scheme(self, client):
        res = shorten(client, url="javascript:alert(1)")
        assert res.status_code == 400
        assert "scheme" in res.get_json()["error"].lower()

    def test_shorten_rejects_non_json_body(self, client):
        res = client.post("/shorten", data="not json")
        assert res.status_code == 400

    def test_shorten_with_custom_alias(self, client):
        res = shorten(client, alias="my-custom-code")
        assert res.status_code == 201
        assert res.get_json()["code"] == "my-custom-code"

    def test_shorten_duplicate_alias_conflicts(self, client):
        shorten(client, url="https://a.com", alias="taken")
        res = shorten(client, url="https://b.com", alias="taken")
        assert res.status_code == 409

    def test_shorten_invalid_alias_rejected(self, client):
        res = shorten(client, alias="a b")
        assert res.status_code == 400

    def test_shorten_two_urls_get_different_codes(self, client):
        r1 = shorten(client, url="https://one.example.com")
        r2 = shorten(client, url="https://two.example.com")
        assert r1.get_json()["code"] != r2.get_json()["code"]


class TestRedirect:
    def test_redirect_success(self, client):
        code = shorten(client, url="https://example.com/target").get_json()["code"]
        res = client.get(f"/{code}", follow_redirects=False)
        assert res.status_code == 302
        assert res.headers["Location"] == "https://example.com/target"

    def test_redirect_unknown_code_404(self, client):
        res = client.get("/does-not-exist")
        assert res.status_code == 404

    def test_redirect_increments_clicks(self, client):
        code = shorten(client).get_json()["code"]
        client.get(f"/{code}")
        client.get(f"/{code}")
        stats = client.get(f"/stats/{code}").get_json()
        assert stats["clicks"] == 2

    def test_expired_link_returns_410(self, app, client):
        code = shorten(client, ttl_seconds=1).get_json()["code"]

        # Force it into the past directly in the fake store rather than
        # sleeping in tests.
        for row in app.supabase.tables["urls"]:
            if row["code"] == code:
                row["expires_at"] = "2000-01-01T00:00:00+00:00"

        res = client.get(f"/{code}")
        assert res.status_code == 410


class TestStats:
    def test_stats_success(self, client):
        code = shorten(client, url="https://example.com/stats-me").get_json()["code"]
        res = client.get(f"/stats/{code}")
        assert res.status_code == 200
        data = res.get_json()
        assert data["url"] == "https://example.com/stats-me"
        assert data["clicks"] == 0
        assert "created_at" in data

    def test_stats_unknown_code(self, client):
        res = client.get("/stats/nope")
        assert res.status_code == 404


class TestDelete:
    def test_delete_without_key_401(self, client):
        code = shorten(client).get_json()["code"]
        res = client.delete(f"/{code}")
        assert res.status_code == 401

    def test_delete_with_wrong_key_403(self, client):
        code = shorten(client).get_json()["code"]
        res = client.delete(f"/{code}", headers={"X-API-Key": "wrong"})
        assert res.status_code == 403

    def test_delete_with_master_key_succeeds(self, client):
        code = shorten(client).get_json()["code"]
        res = client.delete(f"/{code}", headers={"X-API-Key": "test-master-key"})
        assert res.status_code == 204
        assert client.get(f"/stats/{code}").status_code == 404

    def test_delete_unknown_code_404(self, client):
        res = client.delete("/nope", headers={"X-API-Key": "test-master-key"})
        assert res.status_code == 404

    def test_owner_can_delete_own_link(self, client):
        user = client.post("/register", json={"username": "alice"}).get_json()
        res = client.post(
            "/shorten",
            json={"url": "https://example.com/mine"},
            headers={"X-API-Key": user["api_key"]},
        )
        code = res.get_json()["code"]

        del_res = client.delete(f"/{code}", headers={"X-API-Key": user["api_key"]})
        assert del_res.status_code == 204

    def test_other_user_cannot_delete_owned_link(self, client):
        alice = client.post("/register", json={"username": "alice2"}).get_json()
        bob = client.post("/register", json={"username": "bob2"}).get_json()

        res = client.post(
            "/shorten",
            json={"url": "https://example.com/mine2"},
            headers={"X-API-Key": alice["api_key"]},
        )
        code = res.get_json()["code"]

        del_res = client.delete(f"/{code}", headers={"X-API-Key": bob["api_key"]})
        assert del_res.status_code == 403


class TestAnalytics:
    def test_analytics_returns_top_clicked(self, client):
        code_a = shorten(client, url="https://a.example.com").get_json()["code"]
        code_b = shorten(client, url="https://b.example.com").get_json()["code"]

        client.get(f"/{code_a}")
        client.get(f"/{code_a}")
        client.get(f"/{code_b}")

        res = client.get("/analytics?format=json")
        assert res.status_code == 200
        data = res.get_json()
        assert data[0]["code"] == code_a
        assert data[0]["clicks"] == 2

    def test_analytics_html_page_renders(self, client):
        res = client.get("/analytics")
        assert res.status_code == 200
        assert b"most-clicked" in res.data


class TestMultiUser:
    def test_register_creates_api_key(self, client):
        res = client.post("/register", json={"username": "carol"})
        assert res.status_code == 201
        data = res.get_json()
        assert data["username"] == "carol"
        assert len(data["api_key"]) > 10

    def test_register_duplicate_username_conflicts(self, client):
        client.post("/register", json={"username": "dave"})
        res = client.post("/register", json={"username": "dave"})
        assert res.status_code == 409

    def test_my_links_requires_api_key(self, client):
        res = client.get("/my-links")
        assert res.status_code == 401

    def test_my_links_returns_only_own_links(self, client):
        alice = client.post("/register", json={"username": "alice3"}).get_json()
        bob = client.post("/register", json={"username": "bob3"}).get_json()

        client.post(
            "/shorten",
            json={"url": "https://example.com/alice-link"},
            headers={"X-API-Key": alice["api_key"]},
        )
        client.post(
            "/shorten",
            json={"url": "https://example.com/bob-link"},
            headers={"X-API-Key": bob["api_key"]},
        )

        res = client.get("/my-links", headers={"X-API-Key": alice["api_key"]})
        data = res.get_json()
        assert data["username"] == "alice3"
        assert len(data["links"]) == 1
        assert data["links"][0]["url"] == "https://example.com/alice-link"


class TestRateLimit:
    def test_rate_limit_returns_429(self, app):
        app.rate_limiter.max_requests = 2
        client = app.test_client()

        r1 = client.post("/shorten", json={"url": "https://example.com/1"})
        r2 = client.post("/shorten", json={"url": "https://example.com/2"})
        r3 = client.post("/shorten", json={"url": "https://example.com/3"})

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers
