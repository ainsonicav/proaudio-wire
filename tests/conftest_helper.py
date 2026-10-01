"""scripts/ 폴더를 sys.path에 올려 build.py / fill_images.py / notify_telegram.py를
평범한 모듈처럼 import할 수 있게 해주는 작은 헬퍼. (unittest 전용, pytest 불필요)"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
