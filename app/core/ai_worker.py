"""
AI Background Workers
"""
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool

class AIWorkerSignals(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

class AIWorker(QRunnable):
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = AIWorkerSignals()

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.signals.finished.emit(str(result))
        except Exception as e:
            self.signals.error.emit(str(e))
