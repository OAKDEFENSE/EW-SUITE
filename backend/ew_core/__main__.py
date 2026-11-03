"""Run the EW core service: ``python -m ew_core``."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "ew_core.api:app",
        host=os.environ.get("EW_HOST", "0.0.0.0"),
        port=int(os.environ.get("EW_PORT", "8000")),
        reload=os.environ.get("EW_RELOAD", "0") == "1",
        log_level=os.environ.get("EW_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
