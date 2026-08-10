# modbus_driver.py
from pymodbus.client.serial import ModbusSerialClient
import struct
import logging
import threading
import time
import queue

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

        self.request_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._worker_loop, name=f"ModbusWorker-{self.port}", daemon=True)
        self.worker_thread.start()

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

    def reset_connection(self):
        """Closes the underlying Modbus serial client without stopping the worker thread."""
        locked = self.lock.acquire(blocking=True, timeout=15.0)
        if not locked:
            logger.error("reset_connection: Could not acquire lock within 15.0s. Aborting reset to prevent fatal segfaults.")
            return

        try:
            if self.is_simulated:
                return

            if self.client:
                logger.info(f"Resetting Modbus RTU connection on {self.port}")
                try:
                    self.client.close()
                except Exception as e:
                    logger.warning(f"Error while resetting Modbus RTU on {self.port}: {e}")
                finally:
                    self.client = None
        finally:
            if locked:
                self.lock.release()

    def close(self):
        t_name = threading.current_thread().name
        logger.info(f"[{t_name}] Stopping Modbus worker and closing client on {self.port}")

        # Stop worker thread safely
        req = {'method': 'STOP'}
        self.request_queue.put(req)

        if threading.current_thread() != self.worker_thread:
            self.worker_thread.join(timeout=2.0)
            if self.worker_thread.is_alive():
                logger.warning(f"[{t_name}] Modbus worker thread on {self.port} did not exit within timeout.")

        self.reset_connection()

    def sleep_worker(self, duration=2.0):
        """
        Forces the Modbus worker thread to sleep, pausing all background Modbus polling. 
        Useful for riding through massive EMI spikes (e.g. contactor switching) safely.
        """
        if self.is_simulated:
            return
            
        req = {
            'method': 'SLEEP',
            'duration': duration,
            'event': threading.Event(),
        }
        self.request_queue.put(req)
        req['event'].wait()

    def _worker_loop(self):
        """Dedicated thread to process all Modbus and Raw IO requests strictly sequentially."""
        logger.info(f"ModbusWorker started for port {self.port}")
        while True:
            try:
                req = self.request_queue.get()
                method_name = req.get('method')
                
                if method_name == 'STOP':
                    break
                
                if method_name == 'SLEEP':
                    time.sleep(req.get('duration', 1.0))
                    req['event'].set()
                    continue
                
                if method_name == 'send_raw_receive':
                    try:
                        res = self._execute_raw_io(**req['kwargs'])
                        req['result'] = res
                    except Exception as e:
                        req['error'] = e
                    finally:
                        req['event'].set()
                    continue

                try:
                    res = self._execute_modbus_with_retries(method_name, req.get('t_name', 'Unknown'), *req['args'], **req['kwargs'])
                    req['result'] = res
                except Exception as e:
                    req['error'] = e
                finally:
                    req['event'].set()

            except Exception as e:
                logger.error(f"Error in ModbusWorker loop for {self.port}: {e}")
        
        logger.info(f"ModbusWorker stopped for port {self.port}")

    def _execute_modbus_with_retries(self, method_name, t_name, *args, **kwargs):
        """
        Internal wrapper for Modbus calls with retries and error handling.
        """
        max_retries = 3
        last_exception = None

        for attempt in range(max_retries):
            if not self.lock.acquire(timeout=5.0):
                logger.warning(f"[{t_name}] Modbus attempt {attempt+1}/{max_retries} failed: Lock acquisition timeout inside worker")
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

                    time.sleep(0.05)
                    
                    ser = getattr(self.client, 'socket', None)
                    if not ser:
                        ser = getattr(self.client, 'transport', None)
                    # (Removed buffer clearing to prevent hard crashes on Windows during USB drops)

                    # EMI Safe Patch: Add a sleep after writing to let relays settle
                    if ser and not getattr(ser, '_emi_patched', False):
                        if hasattr(ser, 'write'):
                            original_write = ser.write
                            def emi_safe_write(data):
                                res = original_write(data)
                                time.sleep(0.15)
                                return res
                            ser.write = emi_safe_write
                            setattr(ser, '_emi_patched', True)

                    method = getattr(self.client, method_name)
                    
                    def validate_result(result):
                        if result is None:
                            raise RuntimeError("Modbus returned None (Communication Timeout)")
                        if hasattr(result, 'isError') and result.isError():
                            raise RuntimeError(f"Modbus Error: {result}")
                        return result

                    try:
                        logger.debug(f"[{t_name}] Modbus Call: {method_name} | args={args} | kwargs={kwargs}")
                        return validate_result(method(*args, **kwargs))
                    except TypeError as te:
                        error_msg = str(te)
                        if "unexpected keyword argument" not in error_msg:
                            raise te
                            
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
                        
                        if current_key:
                            try:
                                val = kwargs[current_key]
                                new_args = list(args) + [val]
                                logger.info(f"[{t_name}] Modbus: Trying positional fallback for {method_name} with {new_args}")
                                res = method(*new_args)
                                return validate_result(res)
                            except Exception as positional_e:
                                logger.warning(f"[{t_name}] Modbus: Positional fallback failed for {method_name}: {positional_e}")
                                pass
                        
                        raise te
                    
                except Exception as e:
                    last_exception = e
                    logger.warning(f"[{t_name}] Modbus attempt {attempt+1}/{max_retries} failed: {e}")
            finally:
                self.lock.release()
            
            time.sleep(0.2 * (attempt + 1))
        
        logger.error(f"[{t_name}] Modbus operation failed after {max_retries} attempts: {last_exception}")
        self.reset_connection()
        if last_exception:
            raise last_exception
        raise Exception(f"Modbus operation failed after {max_retries} attempts without specific exception")

    def _retry_wrapper(self, method_name, *args, **kwargs):
        t_name = threading.current_thread().name
        
        req = {
            'method': method_name,
            'args': args,
            'kwargs': kwargs,
            'event': threading.Event(),
            'result': None,
            'error': None,
            't_name': t_name
        }
        self.request_queue.put(req)
        
        start_wait = time.time()
        # Prevent GUI freeze if called from MainThread
        while not req['event'].wait(0.05):
            if not self.worker_thread.is_alive():
                req['error'] = RuntimeError(f"ModbusWorker thread for {self.port} is dead. Cannot execute {method_name}.")
                break
                
            if time.time() - start_wait > 15.0:
                logger.critical(f"ModbusWorker {self.port} HUNG for > 15s! Forcing client close to unblock kernel...")
                try:
                    if self.client:
                        self.client.close()
                except Exception:
                    pass
                req['error'] = RuntimeError(f"FATAL: {self.port} HUNG (USB/EMI crash). Port forced closed.")
                break
                
            if threading.current_thread().name == "MainThread":
                try:
                    from PySide6.QtWidgets import QApplication
                    app = QApplication.instance()
                    if app:
                        app.processEvents()
                except ImportError:
                    pass
        
        err = req['error']
        if err is not None:
            if isinstance(err, BaseException):
                raise err
            raise RuntimeError(f"Unknown error occurred: {err}")
        return req['result']

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

    def _execute_raw_io(self, tx_bytes, rx_len, delay, baudrate, t_name):
        """
        Sends raw bytes and reads response using the same serial handle.
        Synchronized internally by the worker thread queue.
        """
        tx_hex = " ".join(f"{b:02X}" for b in tx_bytes)
        logger.info(f"[{t_name}] _execute_raw_io [START] | TX: {tx_hex} | baudrate={baudrate}")
        print(f"[MODBUS-RAW] TX ({len(tx_bytes)} bytes): {tx_hex}")
        
        if not self.lock.acquire(timeout=5.0):
             logger.error(f"[{t_name}] _execute_raw_io [FATAL] | Lock acquisition timeout")
             raise RuntimeError("Could not acquire Modbus lock for raw IO")

        try:
            if self.is_simulated:
                logger.info("Simulation Mode: Returning mock QR response")
                return b"SIM_QR_CODE_123456"

            if not self._ensure_connected():
                raise RuntimeError("Modbus client not connected for raw access")

            ser = getattr(self.client, 'socket', None)
            if not ser:
                ser = getattr(self.client, 'transport', None)
            
            if not ser or not hasattr(ser, 'write'):
                raise RuntimeError("Could not access underlying serial port")

            old_baud = ser.baudrate
            old_timeout = ser.timeout
            if baudrate and baudrate != old_baud:
                logger.info(f"Switching baudrate: {old_baud} -> {baudrate}")
                ser.baudrate = baudrate
                time.sleep(0.2) 

            try:
                # (Removed buffer clearing to prevent hard crashes on Windows during USB drops)
                
                # Assert DTR and RTS just in case the scanner relies on them for power or flow control (Docklight does this by default)
                try:
                    ser.dtr = True
                    ser.rts = True
                except Exception:
                    pass

                ser.write(tx_bytes)
                ser.flush()

                # Robust polling loop to avoid relying on ser.timeout propagation
                rx = b""
                start_time = time.time()
                while time.time() - start_time < delay:
                    try:
                        if hasattr(ser, 'in_waiting') and ser.in_waiting > 0:
                            time.sleep(0.1) # Wait a tiny bit for the rest of the payload to arrive
                            rx = ser.read(ser.in_waiting)
                            break
                    except Exception as poll_e:
                        logger.debug(f"Polling error: {poll_e}")
                        pass
                    time.sleep(0.05)
                
                if not rx:
                    # Fallback if in_waiting is not available or timed out
                    old_timeout = ser.timeout
                    ser.timeout = 0.5
                    rx = ser.read(rx_len)
                    ser.timeout = old_timeout

                if rx:
                    rx_hex = " ".join(f"{b:02X}" for b in rx)
                    logger.info(f"[{t_name}] send_raw_receive [SUCCESS] | RX: {rx_hex}")
                    print(f"[MODBUS-RAW] RX ({len(rx)} bytes): {rx_hex}")
                    return rx
                else:
                    logger.warning(f"[{t_name}] send_raw_receive [TIMEOUT] | No data received within {delay}s")
                    return b""
            
            finally:
                if baudrate and ser.baudrate != old_baud:
                    logger.info(f"Restoring baudrate: {ser.baudrate} -> {old_baud}")
                    ser.baudrate = old_baud
                    time.sleep(0.2)

        except Exception as e:
            logger.error(f"[{t_name}] _execute_raw_io [FATAL] | {e}")
            raise
        finally:
            self.lock.release()

    def send_raw_receive(self, tx_data, rx_len=256, delay=0.5, baudrate=None):
        if isinstance(tx_data, str):
            try:
                tx_bytes = bytes.fromhex(tx_data)
            except ValueError:
                tx_bytes = tx_data.encode()
        else:
            tx_bytes = bytes(tx_data)

        t_name = threading.current_thread().name

        req = {
            'method': 'send_raw_receive',
            'kwargs': {
                'tx_bytes': tx_bytes,
                'rx_len': rx_len,
                'delay': delay,
                'baudrate': baudrate,
                't_name': t_name
            },
            'event': threading.Event(),
            'result': None,
            'error': None
        }
        self.request_queue.put(req)
        
        # Prevent GUI freeze if called from MainThread
        while not req['event'].wait(0.05):
            if threading.current_thread().name == "MainThread":
                try:
                    from PySide6.QtWidgets import QApplication
                    app = QApplication.instance()
                    if app:
                        app.processEvents()
                except ImportError:
                    pass

        if req['error']:
            raise req['error']
        return req['result']



class ModbusTCP(ModbusRTU):
    def __init__(self, ip, port=502, timeout=1):
        from src.core.config import SIMULATION_MODE
        logger.info(f"Initializing ModbusTCP | ip={ip}, port={port}, timeout={timeout}, SIMULATION_MODE={SIMULATION_MODE}")

        self.ip = ip
        # Initialize parent RTU to set up queue, lock, and worker thread
        super().__init__(port=str(ip) + ":" + str(port), baudrate=9600, timeout=timeout)
        self.worker_thread.name = f"ModbusWorker-TCP-{self.ip}"

    def _ensure_connected(self):
        with self.lock:
            if self.is_simulated:
                return True
                
            if self.client is not None:
                return True

            from pymodbus.client import ModbusTcpClient
            try:
                self.client = ModbusTcpClient(
                    host=self.ip,
                    port=int(self.port.split(':')[1]),
                    timeout=self.timeout
                )
                if not self.client.connect():
                    raise ConnectionError(f"Could not connect to Modbus TCP {self.ip}:{self.port}")
                logger.info(f"ModbusTCP Connected to {self.ip}:{self.port}")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize Modbus TCP client on {self.ip}:{self.port} | {e}")
                self.client = None
                return False
