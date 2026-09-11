from app.api.demo_noop import build_demo_noop_router


def test_demo_noop_router_registers_expected_paths() -> None:
    router = build_demo_noop_router()
    paths = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/api/classify", "POST") in paths
    assert ("/api/reindex", "POST") in paths
    assert ("/api/fetch", "POST") in paths


def test_demo_noop_router_preserves_response_payload() -> None:
    router = build_demo_noop_router()
    route = next(route for route in router.routes if route.path == "/api/classify")
    assert route.endpoint() == {"status": "demo_noop"}
