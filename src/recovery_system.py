import threading
import time
from datetime import datetime
from typing import Optional
from log import get_logger

logger = get_logger()


#maager recovery
class RecoveryManager:
    def __init__(self, max_retries: int = 3, retry_delay: int = 5):
        self.max_retries  = max_retries
        self.retry_delay  = retry_delay
        self.failure_count: dict = {}
        self.last_failure:  dict = {}

    def execute_with_recovery(self, func, func_name: str, *args, **kwargs):
        retry_count = 0

        while retry_count < self.max_retries:
            try:
                result = func(*args, **kwargs)

                if func_name in self.failure_count:
                    logger.info(
                        f"✔ {func_name} recuperado tras "
                        f"{self.failure_count[func_name]} fallo(s)"
                    )
                    del self.failure_count[func_name]

                return True, result

            except Exception as e:
                retry_count += 1
                self.failure_count[func_name] = self.failure_count.get(func_name, 0) + 1
                self.last_failure[func_name]  = datetime.now()

                logger.error(
                    f"✗ Error en {func_name} "
                    f"(intento {retry_count}/{self.max_retries}): {e}",
                    exc_info=True,
                )

                if retry_count < self.max_retries:
                    logger.info(f"↻ Reintentando en {self.retry_delay}s …")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"✗✗✗ {func_name} falló tras {self.max_retries} intentos"
                    )

        return False, None

    def execute_with_recovery_async(
        self, func, func_name: str, stop_event: threading.Event,
        *args, **kwargs,
    ):
        retry_count = 0

        while retry_count < self.max_retries:
            try:
                result = func(*args, **kwargs)

                if func_name in self.failure_count:
                    logger.info(
                        f"✔ {func_name} recuperado tras "
                        f"{self.failure_count[func_name]} fallo(s)"
                    )
                    del self.failure_count[func_name]

                return True, result

            except Exception as e:
                retry_count += 1
                self.failure_count[func_name] = self.failure_count.get(func_name, 0) + 1
                self.last_failure[func_name]  = datetime.now()

                logger.error(
                    f"✗ Error en {func_name} "
                    f"(intento {retry_count}/{self.max_retries}): {e}",
                    exc_info=True,
                )

                if retry_count < self.max_retries:
                    logger.info(f"↻ Reintentando en {self.retry_delay}s …")
                    stop_event.wait(self.retry_delay)
                    if stop_event.is_set():
                        logger.info(f"[recovery] Señal de parada recibida durante reintento de {func_name}")
                        return False, None
                else:
                    logger.error(
                        f"✗✗✗ {func_name} falló tras {self.max_retries} intentos"
                    )

        return False, None

    def get_failure_stats(self) -> dict:
        return {
            "failure_count": self.failure_count.copy(),
            "last_failure":  self.last_failure.copy(),
        }


#monitor del watch dog
class WatchdogMonitor:

    def __init__(self, check_interval: int = 300):  #intervalo expresanddo en segundos(5minutos)
        self.check_interval  = check_interval
        self.components: dict = {}
        self.stop_event       = threading.Event()
        self.monitor_thread   = None

    def register_component(self, name: str, health_check_func, restart_func) -> None:

        self.components[name] = {
            "health_check":  health_check_func,
            "restart":       restart_func,
            "last_check":    None,
            "restart_count": 0,
            "last_restart":  None,
        }
        logger.info(f"[watchdog] Componente registrado: {name}")

    def _monitor_loop(self) -> None:
        while not self.stop_event.is_set():
            for name, comp in self.components.items():
                try:
                    is_healthy       = comp["health_check"]()
                    comp["last_check"] = datetime.now()

                    if not is_healthy:
                        logger.warning(f"[watchdog] {name} NO saludable — reiniciando …")
                        comp["restart"]()
                        comp["restart_count"] += 1
                        comp["last_restart"]   = datetime.now()
                        logger.info(
                            f"[watchdog] ↻ {name} reiniciado "
                            f"(total: {comp['restart_count']})"
                        )

                except Exception as e:
                    logger.error(f"[watchdog] Error monitoreando {name}: {e}", exc_info=True)

            self.stop_event.wait(self.check_interval)

        logger.info("[watchdog] Monitor detenido")

    def start(self) -> None:
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("[watchdog] Ya está en ejecución")
            return

        self.stop_event.clear()
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="watchdog",
        )
        self.monitor_thread.start()
        logger.info("[watchdog] Monitor iniciado")

    def stop(self) -> None:
        logger.info("[watchdog] Deteniendo …")
        self.stop_event.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)

    def get_stats(self) -> dict:
        return {
            name: {
                "last_check":    comp["last_check"],
                "restart_count": comp["restart_count"],
                "last_restart":  comp["last_restart"],
            }
            for name, comp in self.components.items()
        }


# manager de timeout
class TimeoutManager:
    @staticmethod
    def run_with_timeout(func, timeout_seconds: int, *args, **kwargs):
        result    = [None]
        exception = [None]

        def wrapper():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)

        if thread.is_alive():
            logger.error(f"[timeout] Función excedió {timeout_seconds}s")
            return False, None

        if exception[0]:
            logger.error(f"[timeout] Error en función: {exception[0]}", exc_info=True)
            return False, None

        return True, result[0]


#singletones
_recovery_manager: Optional[RecoveryManager] = None
_watchdog_monitor: Optional[WatchdogMonitor] = None


def get_recovery_manager() -> RecoveryManager:
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = RecoveryManager()
    return _recovery_manager


def get_watchdog() -> WatchdogMonitor:
    global _watchdog_monitor
    if _watchdog_monitor is None:
        _watchdog_monitor = WatchdogMonitor()
    return _watchdog_monitor