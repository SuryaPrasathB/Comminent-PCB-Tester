import threading
import time
from src.core.logger import logger
from src.core.config import SLAVE_DEVICES

class SafetyMonitor(threading.Thread):
    def __init__(self, modbus_client, stop_event, callback):
        super().__init__()
        self.modbus = modbus_client
        self.stop_event = stop_event
        self.callback = callback
        
        plc = SLAVE_DEVICES["PLC"]
        self.plc_slave = plc["slave_id"]
        
        coils = plc["coils"]
        self.addr_estop = coils["EMERGENCY_STOP"]
        self.addr_curtain = coils["CURTAIN_SENSOR"]

    def run(self):
        logger.info("SafetyMonitor thread started")
        
        while not self.stop_event.is_set():
            try:
                # -----------------------------------------------------
                # Check EMERGENCY STOP (101)
                # -----------------------------------------------------
                estop_bits = self.modbus.read_coils(self.plc_slave, self.addr_estop, 1)
                if estop_bits and estop_bits[0]:
                    logger.warning("SafetyMonitor: EMERGENCY STOP DETECTED")
                    self.callback("Emergency Stop")
                    break
                    
                # -----------------------------------------------------
                # Check CURTAIN SENSOR (102)
                # -----------------------------------------------------
                curtain_bits = self.modbus.read_coils(self.plc_slave, self.addr_curtain, 1)
                if curtain_bits and curtain_bits[0]:
                    logger.warning("SafetyMonitor: CURTAIN SENSOR DETECTED")
                    self.callback("Curtain Sensor")
                    break
                
                # Sleep to yield execution and prevent busy loop
                time.sleep(0.2) 
                
            except Exception as e:
                # Log errors but continue unless severe
                # If modbus is closed externally, this might spam errors until stop_event is set
                logger.error(f"SafetyMonitor error: {e}")
                time.sleep(1)

        logger.info("SafetyMonitor thread stopped")
