"""Supported single-process local launcher: no reload, no proxy trust."""

import uvicorn

from bottleneck_analyzer.core.config import get_settings


def main() -> None:
    settings = get_settings()
    if settings.app_host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("APP_HOST must be a loopback address for the local prototype")
    if settings.app_reload:
        raise SystemExit("APP_RELOAD must be false for process-local investigations")
    uvicorn.run(
        "bottleneck_analyzer.main:app",
        host=settings.app_host,
        port=settings.app_port,
        workers=1,
        reload=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
