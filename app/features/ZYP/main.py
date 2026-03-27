import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.features.ZYP.tui import ZYPTuiApp


def main():
    app = ZYPTuiApp()
    asyncio.run(app.initialize())
    app.run()


if __name__ == "__main__":
    main()
