from .aplicacao import PDFInserterApp
from .entrypoint import main as tk_main
from .pyside_ui import run_app as main

__all__ = ["PDFInserterApp", "main", "tk_main"]
