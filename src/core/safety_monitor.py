import time
import threading
from PySide6.QtCore import QObject, Signal
from src.core.logger import logger
from src.core.config import SLAVE_DEVICES

class SafetySignals(QObject):
    safety_alert_signal = Signal(str)

_safety_signal_refs = []

class SafetyMonitor:
    def __init__(self, modbus_client, stop_event):
        self.signals = SafetySignals()
        _safety_signal_refs.append(self.signals)
        self.modbus = modbus_client
        self.stop_event = stop_event
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        
        plc = SLAVE_DEVICES["PLC"]
        self.plc_slave = plc["slave_id"]
        
        coils = plc["coils"]
        self.addr_estop = coils["EMERGENCY_STOP"]
        self.addr_curtain = coils["CURTAIN_SENSOR"]

    def start(self):
        self._thread.start()

    def wait(self, timeout=None):
        if timeout:
            self._thread.join(timeout / 1000.0)
        else:
            self._thread.join()

    def isRunning(self):
        return self._thread.is_alive()

    def _run_loop(self):
        logger.info("SafetyMonitor thread started")
        
        while not self.stop_event.is_set():
            try:
                # -----------------------------------------------------
                # Batch read contiguous safety sensors (103, 104)
                # addr_estop=104, addr_curtain=103
                # -----------------------------------------------------
                start_addr = min(self.addr_estop, self.addr_curtain)
                count = max(self.addr_estop, self.addr_curtain) - start_addr + 1
                
                bits = self.modbus.read_coils(self.plc_slave, start_addr, count)
                
                if bits:
                    # Map back to correct sensors
                    curtain_active = bits[self.addr_curtain - start_addr]
                    estop_active = bits[self.addr_estop - start_addr]
                    
                    if estop_active:
                        logger.warning("SafetyMonitor: EMERGENCY STOP DETECTED")
                        try:
                            self.signals.safety_alert_signal.emit("Emergency Stop")
                        except RuntimeError:
                            pass
                        break
                        
                    if curtain_active:
                        logger.warning("SafetyMonitor: CURTAIN SENSOR DETECTED")
                        try:
                            self.signals.safety_alert_signal.emit("Curtain Sensor")
                        except RuntimeError:
                            pass
                        break
                
                # Increased sleep to reduce bus contention on shared RS485 port
                # Slowed to 1.0s to give more bus bandwidth to TestRunner
                if self.stop_event.wait(1.0):
                    break
                
            except Exception as e:
                # Log errors but continue unless severe
                # If modbus is closed externally, this might spam errors until stop_event is set
                logger.error(f"SafetyMonitor error: {e}")
                if self.stop_event.wait(1.0):
                    break
            except BaseException as be:
                logger.error(f"CRITICAL BASE EXCEPTION in SafetyMonitor: {be}")
                import traceback
                logger.error(traceback.format_exc())
                break

        logger.info("SafetyMonitor thread stopped")
