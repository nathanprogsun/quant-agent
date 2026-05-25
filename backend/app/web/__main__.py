"""Web package __main__.py - application entry point.

Run with: python -m app.web
Or: uvicorn app.web.__main__:get_app --reload
"""

from app.web.application import get_app

app = get_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.web.__main__:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
