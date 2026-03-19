from __future__ import annotations

import uvicorn

from app.config import get_settings
from app.web import create_app


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        create_app(settings=settings),
        host=settings.web_host,
        port=settings.web_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
