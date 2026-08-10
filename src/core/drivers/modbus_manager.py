# src/core/drivers/modbus_manager.py
import threading
from src.core.drivers.modbus_driver import ModbusRTU, ModbusTCP
from src.core.logger import logger
from src.ui.settings_manager import SettingsManager

class ModbusProxy:
    """
    A smart proxy that routes PLC commands (slave 1) via ModbusTCP 
    and Meter commands (slave > 1) via ModbusRTU.
    """
    def __init__(self, tcp_client, rtu_client, plc_slave_id=1):
        self.tcp_client = tcp_client
        self.rtu_client = rtu_client
        self.plc_slave_id = plc_slave_id

    def _get_client(self, args, kwargs):
        slave = kwargs.get('slave')
        if slave is None and len(args) > 0:
            slave = args[0]
        
        if slave == self.plc_slave_id:
            return self.tcp_client
        return self.rtu_client

    def write_coil(self, *args, **kwargs):
        return self._get_client(args, kwargs).write_coil(*args, **kwargs)

    def write_coils(self, *args, **kwargs):
        return self._get_client(args, kwargs).write_coils(*args, **kwargs)
        
    def read_coils(self, *args, **kwargs):
        return self._get_client(args, kwargs).read_coils(*args, **kwargs)

    def read_holding_registers(self, *args, **kwargs):
        return self._get_client(args, kwargs).read_holding_registers(*args, **kwargs)

    def read_float(self, *args, **kwargs):
        return self._get_client(args, kwargs).read_float(*args, **kwargs)

    def read_floats(self, *args, **kwargs):
        return self._get_client(args, kwargs).read_floats(*args, **kwargs)

    def sleep_worker(self, *args, **kwargs):
        # Can route to either since it's just a time.sleep() wrapper
        self.tcp_client.sleep_worker(*args, **kwargs)

    def close(self):
        # Let ModbusManager handle actual closing of the inner clients, 
        # or we just ignore the generic close call since they're shared.
        pass

class ModbusManager:
    """
    Manages shared Modbus instances to prevent frequent open/close
    and resource contention on serial ports.
    """
    _instances = {}
    _lock = threading.RLock()

    @classmethod
    def get_client(cls, port, baudrate=9600, timeout=1):
        with cls._lock:
            settings = SettingsManager()
            qr_settings = settings.get_setting("qr_scanners", {})
            is_scanner = port in [qr_settings.get("scanner_1_port"), qr_settings.get("scanner_2_port")]

            # Scanners always just get an RTU client for their specific port
            if is_scanner:
                if port not in cls._instances:
                    logger.info(f"ModbusManager: Creating scanner client for {port}")
                    cls._instances[port] = ModbusRTU(port=port, baudrate=baudrate, timeout=timeout)
                return cls._instances[port]

            # PLC and RS485 connectivity
            plc_settings = settings.get_setting("plc_settings", {})
            plc_ip = plc_settings.get("ip_address", "192.168.0.123")
            
            # The requested 'port' parameter here will be the RS485 Bus COM port (e.g., 'COM4').
            # We construct a proxy that intercepts commands and routes them based on slave ID.
            proxy_key = f"proxy_{plc_ip}_{port}"
            
            if proxy_key not in cls._instances:
                logger.info(f"ModbusManager: Creating ModbusProxy (PLC={plc_ip}, RS485={port})")
                
                if plc_ip not in cls._instances:
                    cls._instances[plc_ip] = ModbusTCP(ip=plc_ip, port=502, timeout=timeout)
                
                if port not in cls._instances:
                    cls._instances[port] = ModbusRTU(port=port, baudrate=baudrate, timeout=timeout)
                    
                cls._instances[proxy_key] = ModbusProxy(
                    tcp_client=cls._instances[plc_ip],
                    rtu_client=cls._instances[port],
                    plc_slave_id=1
                )
            
            return cls._instances[proxy_key]

    @classmethod
    def close_all(cls):
        with cls._lock:
            for key in list(cls._instances.keys()):
                cls.clear_client(key)

    @classmethod
    def clear_client(cls, key):
        with cls._lock:
            if key in cls._instances:
                logger.info(f"ModbusManager: Clearing client for {key}")
                try:
                    # Proxy client doesn't need explicit close (does nothing), but actual clients do
                    if not isinstance(cls._instances[key], ModbusProxy):
                        cls._instances[key].close()
                except:
                    pass
                del cls._instances[key]
