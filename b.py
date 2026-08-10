import os
import sys

if getattr(sys, 'frozen', False):
    null_file = open(os.devnull, 'w', encoding='utf-8')
    sys.stdout = null_file
    sys.stderr = null_file

from gerenciador_atlantico.pyside_ui import run_app as main


if __name__ == "__main__":
    raise SystemExit(main())
