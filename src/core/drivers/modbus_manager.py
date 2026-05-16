# src/core/drivers/modbus_manager.py
import threading
from src.core.drivers.modbus_driver import ModbusRTU
from src.core.logger import logger

class ModbusManager:
    """
    Manages shared ModbusRTU instances to prevent frequent open/close
    and resource contention on serial ports.
    """
    _instances = {}
    _lock = threading.RLock()

    @classmethod
    def get_client(cls, port, baudrate=9600, timeout=1):
        with cls._lock:
            if port not in cls._instances:
                logger.info(f"ModbusManager: Creating new client for {port}")
                cls._instances[port] = ModbusRTU(port, baudrate, timeout)
            else:
                logger.info(f"ModbusManager: Reusing existing client for {port}")
            return cls._instances[port]

    @classmethod
    def close_all(cls):
        with cls._lock:
            for port in list(cls._instances.keys()):
                cls.clear_client(port)

    @classmethod
    def clear_client(cls, port):
        with cls._lock:
            if port in cls._instances:
                logger.info(f"ModbusManager: Clearing client for {port}")
                try:
                    cls._instances[port].close()
                except:
                    pass
                del cls._instances[port]
