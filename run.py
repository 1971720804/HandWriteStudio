import os
import sys

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import main

raise SystemExit(main())
