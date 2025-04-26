# src/__main__.py
# (Остается БЕЗ ИЗМЕНЕНИЙ с предыдущего шага)
import asyncio
import logging
import sys
from src.bot import main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Initializing application via __main__.py...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user or system exit.")
    except Exception as e:
        logger.critical(f"Unhandled exception at top level: {e}", exc_info=True)
    finally:
        logger.info("Application shutdown.")