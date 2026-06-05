import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.routes_setup import api_setup_guard_middleware

app = FastAPI()
app.state.setup_required = True
app.middleware("http")(api_setup_guard_middleware)

@app.get("/v1/models")
async def models():
    return {"data": []}

@app.get("/health")
async def health():
    return {"status": "ok"}

def test_api_guard_blocks_v1_when_setup_required():
    client = TestClient(app)
    response = client.get("/v1/models")
    assert response.status_code == 403
    assert "Gateway requires configuration" in response.text
    assert "/setup" in response.text

def test_api_guard_allows_health_when_setup_required():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
