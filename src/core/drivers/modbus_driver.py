# modbus_driver.py
from pymodbus.client.serial import ModbusSerialClient
import struct
import logging
import threading
import time

from src.core.logger import logger
from src.core.config import SIMULATION_MODE, SERIAL_SETTINGS


class ModbusRTU:
    def __init__(self, port, baudrate=9600, timeout=1):
        logger.info(f"Initializing ModbusRTU | port={port}, baudrate={baudrate}, timeout={timeout}, SIMULATION_MODE={SIMULATION_MODE}")

        self.lock = threading.RLock()
        self.is_simulated = SIMULATION_MODE
        self.port = port
        self.baudrate = baudrate if baudrate != 9600 else SERIAL_SETTINGS.get("baudrate", 9600)
        self.timeout = timeout if timeout != 1 else SERIAL_SETTINGS.get("timeout", 1)
        self.client = None

        if not self.is_simulated:
            try:
                self._ensure_connected()
            except Exception as e:
                logger.error(f"Initial Modbus connection failed on {port}: {e}")
                # We don't raise here, we'll try again on first use

    def _ensure_connected(self):
        with self.lock:
            if self.is_simulated:
                return True
            
            if self.client is not None:
                return True

            try:
                logger.info(f"ModbusRTU: Attempting to connect to {self.port}...")
                self.client = ModbusSerialClient(
                    port=self.port,
                    framer='rtu',
                    baudrate=self.baudrate,
                    bytesize=SERIAL_SETTINGS.get("bytesize", 8),
                    parity=SERIAL_SETTINGS.get("parity", 'N'),
                    stopbits=SERIAL_SETTINGS.get("stopbits", 1),
                    timeout=self.timeout,
                    **{k: v for k, v in SERIAL_SETTINGS.items() if k not in ['baudrate', 'bytesize', 'parity', 'stopbits', 'timeout']}
                )

                if not self.client.connect():
                    self.client = None
                    return False
                
                logger.info(f"Modbus RTU connected | port={self.port}")
                return True
            except Exception as e:
                logger.error(f"Failed to create Modbus client on {self.port}: {e}")
                self.client = None
                return False

    def close(self):
        t_name = threading.current_thread().name
        # Try to acquire lock with timeout to prevent hanging the UI thread during shutdown
        locked = self.lock.acquire(blocking=True, timeout=0.5)
        if not locked:
            logger.warning(f"[{t_name}] Close: Could not acquire lock within 0.5s. Forcefully closing client.")

        try:
            if self.is_simulated:
                logger.info("Simulation Mode: Bypassing Modbus RTU close")
                return

            if self.client:
                logger.info(f"Closing Modbus RTU connection on {self.port}")
                try:
                    self.client.close()
                    logger.info(f"Modbus RTU closed | port={self.port}")
                except Exception as e:
                    logger.warning(f"Error while closing Modbus RTU on {self.port}: {e}")
                finally:
                    self.client = None
        finally:
            if locked:
                self.lock.release()

    def _retry_wrapper(self, method_name, *args, **kwargs):
        """
        Generic wrapper for Modbus calls with retries and error handling.
        """
        max_retries = 3
        last_exception = None
        t_name = threading.current_thread().name

        for attempt in range(max_retries):
            # Use timed acquisition to prevent background threads from hanging indefinitely
            if not self.lock.acquire(timeout=5.0):
                logger.warning(f"[{t_name}] Modbus attempt {attempt+1}/{max_retries} failed: Lock acquisition timeout")
                continue

            try:
                if not self.is_simulated:
                    if not self._ensure_connected():
                        logger.warning(f"[{t_name}] Modbus attempt {attempt+1}/{max_retries} failed: Could not establish connection")
                        time.sleep(0.5)
                        continue

                try:
                    if self.is_simulated:
                        return None 

                    # Increased inter-request delay for shared RS485 bus stability
                    # Throttled to 100ms to prevent native driver buffer overflows
                    time.sleep(0.1)
                    
                    # Execute the method on the client
                    method = getattr(self.client, method_name)
                    
                    def validate_result(result):
                        if result is None:
                            raise RuntimeError("Modbus returned None (Communication Timeout)")
                        if hasattr(result, 'isError') and result.isError():
                            raise RuntimeError(f"Modbus Error: {result}")
                        return result

                    # 1. Try the original call (usually with slave=...)
                    try:
                        logger.info(f"[{t_name}] Modbus Call: {method_name} | args={args} | kwargs={kwargs}")
                        return validate_result(method(*args, **kwargs))
                    except TypeError as te:
                        error_msg = str(te)
                        # Only proceed if it's an 'unexpected keyword argument' error
                        if "unexpected keyword argument" not in error_msg:
                            raise te
                            
                        # 2. Try known keyword variants
                        variants = ['slave', 'unit', 'device_id']
                        current_key = next((k for k in variants if k in kwargs), None)
                        
                        if current_key:
                            val = kwargs[current_key]
                            other_variants = [v for v in variants if v != current_key]
                            
                            for v in other_variants:
                                try:
                                    new_kwargs = kwargs.copy()
                                    new_kwargs.pop(current_key)
                                    new_kwargs[v] = val
                                    res = method(*args, **new_kwargs)
                                    return validate_result(res)
                                except TypeError:
                                    continue
                        
                        # 3. Try Positional Fallback (Brute Force)
                        if current_key:
                            try:
                                val = kwargs[current_key]
                                # Map method names to positional order: (address, [count/value], slave)
                                # Most pymodbus 3.x methods follow this pattern.
                                new_args = list(args) + [val]
                                logger.info(f"[{t_name}] Modbus: Trying positional fallback for {method_name} with {new_args}")
                                res = method(*new_args)
                                return validate_result(res)
                            except Exception as positional_e:
                                logger.warning(f"[{t_name}] Modbus: Positional fallback failed for {method_name}: {positional_e}")
                                pass
                        
                        # If all fallbacks failed, raise the original error
                        raise te
                    
                except Exception as e:
                    last_exception = e
                    logger.warning(f"[{t_name}] Modbus attempt {attempt+1}/{max_retries} failed: {e}")
            finally:
                self.lock.release()
            
            # Sleep OUTSIDE the lock
            time.sleep(0.2 * (attempt + 1))
        
        logger.error(f"[{t_name}] Modbus operation failed after {max_retries} attempts: {last_exception}")
        # Force close on fatal error to ensure fresh connection next time
        self.close()
        raise last_exception

    # ---------------- COILS ----------------
    def write_coil(self, slave, address, value: bool):
        t_name = threading.current_thread().name
        logger.info(f"[{t_name}] write_coil [START] | slave={slave}, address={address}, value={value}")
        
        if self.is_simulated:
            return

        try:
            self._retry_wrapper("write_coil", address, value, slave=slave)
            logger.info(f"[{t_name}] write_coil [SUCCESS] | slave={slave}, address={address}")
        except Exception as e:
            logger.error(f"[{t_name}] write_coil [FATAL] | slave={slave}, address={address} | {e}")
            raise

    def write_coils(self, slave, address, values):
        t_name = threading.current_thread().name
        logger.info(f"[{t_name}] write_coils [START] | slave={slave}, address={address}, count={len(values)}")
        
        if self.is_simulated:
            return

        try:
            self._retry_wrapper("write_coils", address, values, slave=slave)
            logger.info(f"[{t_name}] write_coils [SUCCESS] | slave={slave}, address={address}, count={len(values)}")
        except Exception as e:
            logger.error(f"[{t_name}] write_coils [FATAL] | slave={slave}, address={address} | {e}")
            raise

    def read_coils(self, slave, address, count=1):
        t_name = threading.current_thread().name
        # logger.info(f"[{t_name}] read_coils [START] | slave={slave}, address={address}, count={count}")

        if self.is_simulated:
            return [False] * count

        try:
            result = self._retry_wrapper("read_coils", address, count=count, slave=slave)
            # logger.info(f"[{t_name}] read_coils [SUCCESS] | slave={slave}, address={address}, count={count}")
            return result.bits
        except Exception as e:
            logger.error(f"[{t_name}] read_coils [FATAL] | slave={slave}, address={address} | {e}")
            raise

    # ---------------- HOLDING REGISTERS ----------------
    def read_holding_registers(self, slave, address, count=2):
        t_name = threading.current_thread().name
        # logger.info(f"[{t_name}] read_holding_registers [START] | slave={slave}, address={address}, count={count}")

        if self.is_simulated:
            return [0] * count

        try:
            result = self._retry_wrapper("read_holding_registers", address, count=count, slave=slave)
            # logger.info(f"[{t_name}] read_holding_registers [SUCCESS] | slave={slave}, address={address}")
            return result.registers
        except Exception as e:
            logger.error(f"[{t_name}] read_holding_registers [FATAL] | slave={slave}, address={address} | {e}")
            raise

    # ---------------- FLOAT HELPERS ----------------
    def read_floats(self, slave, address, count=1, endian="ABCD"):
        """Reads multiple consecutive floats (each taking 2 registers)."""
        t_name = threading.current_thread().name
        logger.info(f"[{t_name}] read_floats [START] | slave={slave}, address={address}, count={count}, endian={endian}")
        
        try:
            # Each float is 2 registers
            regs = self.read_holding_registers(slave, address, count * 2)

            if len(regs) != count * 2:
                raise RuntimeError(f"Invalid register count ({len(regs)}) for {count} floats at {address}")

            values = []
            for i in range(count):
                hi, lo = regs[i*2], regs[i*2 + 1]

                if endian == "ABCD":
                    raw = struct.pack(">HH", hi, lo)
                elif endian == "CDAB":
                    raw = struct.pack(">HH", lo, hi)
                else:
                    raise ValueError(f"Unsupported endian mode: {endian}")

                val = struct.unpack(">f", raw)[0]
                values.append(val)
            
            logger.info(f"[{t_name}] read_floats [SUCCESS] | slave={slave}, address={address}, values={values}")
            return values
            
        except Exception as e:
            logger.error(f"[{t_name}] read_floats [FATAL] | slave={slave}, address={address} | {e}")
            raise

    def read_float(self, slave, address, endian="ABCD"):
        """Helper to read a single float."""
        results = self.read_floats(slave, address, count=1, endian=endian)
        return results[0] if results else None

    def send_raw_receive(self, tx_data, rx_len=256, delay=0.5, baudrate=None):
        """
        Sends raw bytes and reads response using the same serial handle.
        Synchronized by self.lock to prevent collisions with Modbus calls.
        Supports temporary baudrate switching for non-standard hardware.
        """
        # Normalize to bytes for logging
        if isinstance(tx_data, str):
            try:
                tx_bytes = bytes.fromhex(tx_data)
            except ValueError:
                tx_bytes = tx_data.encode()
        else:
            tx_bytes = bytes(tx_data)

        tx_hex = " ".join(f"{b:02X}" for b in tx_bytes)
        t_name = threading.current_thread().name
        logger.info(f"[{t_name}] send_raw_receive [START] | TX: {tx_hex} | baudrate={baudrate}")
        print(f"[MODBUS-RAW] TX ({len(tx_bytes)} bytes): {tx_hex}")
        
        if not self.lock.acquire(timeout=5.0):
             logger.error(f"[{t_name}] send_raw_receive [FATAL] | Lock acquisition timeout")
             raise RuntimeError("Could not acquire Modbus lock for raw IO")

        try:
            if self.is_simulated:
                logger.info("Simulation Mode: Returning mock QR response")
                return b"SIM_QR_CODE_123456"

            if not self._ensure_connected():
                raise RuntimeError("Modbus client not connected for raw access")

            # Access underlying pyserial object
            ser = getattr(self.client, 'socket', None)
            if not ser:
                ser = getattr(self.client, 'transport', None)
            
            if not ser or not hasattr(ser, 'write'):
                raise RuntimeError("Could not access underlying serial port")

            # --- Handle Dynamic Baudrate ---
            old_baud = ser.baudrate
            old_timeout = ser.timeout
            if baudrate and baudrate != old_baud:
                logger.info(f"Switching baudrate: {old_baud} -> {baudrate}")
                ser.baudrate = baudrate
                time.sleep(0.2) # Increased stabilization for shared bus

            try:
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()

                # Set timeout so read will block efficiently until data or timeout
                ser.timeout = delay

                # Transmit
                ser.write(tx_bytes)
                ser.flush()

                # Read efficiently using PySerial timeout
                rx = ser.read(rx_len)
                
                if rx:
                    rx_hex = " ".join(f"{b:02X}" for b in rx)
                    logger.info(f"send_raw_receive [SUCCESS] | RX: {rx_hex}")
                    print(f"[MODBUS-RAW] RX ({len(rx)} bytes): {rx_hex}")
                    return rx
                else:
                    logger.warning("send_raw_receive [TIMEOUT] | No data received")
                    return b""
            
            finally:
                # Restore original baudrate and timeout
                ser.timeout = old_timeout
                if baudrate and ser.baudrate != old_baud:
                    logger.info(f"Restoring baudrate: {ser.baudrate} -> {old_baud}")
                    ser.baudrate = old_baud
                    time.sleep(0.2) # Increased stabilization

        except Exception as e:
            logger.error(f"[{t_name}] send_raw_receive [FATAL] | {e}")
            raise
        finally:
            self.lock.release()

