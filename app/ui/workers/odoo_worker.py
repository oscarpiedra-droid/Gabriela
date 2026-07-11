import sys
import urllib.error
from PySide6.QtCore import QObject, Signal, QRunnable, Slot
from loguru import logger

# Errores de socket que indican corte de conexión TCP (WinError 10053, 10054...)
_SOCKET_ERRORS = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError, OSError)

class OdooWorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    """
    finished = Signal()
    error = Signal(str)
    result = Signal(object)

class OdooWorker(QRunnable):
    """
    Worker thread to execute Odoo tasks without blocking the UI.
    Incluye detección automática de errores de socket (WinError 10053)
    para emitir mensajes diferenciales y permitir reintento externo.
    """
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = OdooWorkerSignals()

    @Slot()
    def run(self):
        """
        Execute the function and catch any errors.
        """
        try:
            res = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(res)
        except (urllib.error.URLError, *_SOCKET_ERRORS) as e:
            # Error de red/socket: la conexión TCP fue cortada (WinError 10053, etc.)
            logger.warning(
                f"[OdooWorker] Conexión cortada por el sistema (error de socket): {e}. "
                "El servicio reconectará en el próximo intento automáticamente."
            )
            self.signals.error.emit(
                f"Conexión a Odoo interrumpida (error de red). "
                f"Se reintentará automáticamente.\nDetalle: {e}"
            )
        except Exception as e:
            logger.error(f"Worker Error: {e}")
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()
