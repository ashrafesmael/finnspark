#!/usr/bin/env python3
"""finnspark — accelerator & investment platform. FastAPI entrypoint (mirrors FinnPayments run.py)."""
import logging
import os
import sys
from pathlib import Path

import uvicorn

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "finnspark.log", mode="a"),
    ],
)
logger = logging.getLogger("finnspark")


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8002"))
    logger.info("=" * 50)
    logger.info("finnspark — accelerator & investment platform")
    logger.info("Starting server on %s:%s", host, port)
    logger.info("=" * 50)
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
