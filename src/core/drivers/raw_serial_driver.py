# raw_serial_driver.py
import serial
import time

from src.core.config import SERIAL_SETTINGS, SLAVE_DEVICES
from src.core.logger import logger


class RawSerial:
    """
    RAW serial driver for non-Modbus devices (e.g. QR scanner)
    Works on RS485 → RS232 converters using same COM port
    Serial parameters are taken ONLY from config.py
    """

    def __init__(self, port: str, baudrate: int = None):
        logger.info(f"Initializing RawSerial | port={port}")

        print(f"[RAW] Opening RAW serial port: {port}")

        # Use provided baudrate or fall back to config
        effective_baud = baudrate if baudrate else SERIAL_SETTINGS["baudrate"]

        self.ser = serial.Serial(
            port=port,
            baudrate=effective_baud,
            bytesize=SERIAL_SETTINGS["bytesize"],
            parity=SERIAL_SETTINGS["parity"],
            stopbits=SERIAL_SETTINGS["stopbits"],
            timeout=SERIAL_SETTINGS["timeout"],
            exclusive=SERIAL_SETTINGS.get("exclusive", True),
        )

        if not self.ser.is_open:
            logger.error(f"Failed to open RAW serial port | port={port}")
            raise RuntimeError("Failed to open RAW serial port")

        print(
            "[RAW] RAW serial opened "
            f"(baud={effective_baud}, "
            f"parity={SERIAL_SETTINGS['parity']}, "
            f"stopbits={SERIAL_SETTINGS['stopbits']})"
        )

        logger.info(
            f"RAW serial opened | port={port}, "
            f"baud={effective_baud}, "
            f"parity={SERIAL_SETTINGS['parity']}, "
            f"stopbits={SERIAL_SETTINGS['stopbits']}"
        )

    # -------------------------------------------------
    def write_read(
            self,
            tx_data,
            rx_len: int = 256,
            delay: float = 0.1
    ) -> bytes:
        """
        Send raw bytes and read response

        tx_data can be:
          - bytes            -> b'\x01\x54\x04'
          - list/tuple[int]  -> [0x01, 0x54, 0x04]
          - hex string       -> "01 54 04" or "015404"
        """

        # -------------------------------
        # Normalize TX data to bytes
        # -------------------------------
        if isinstance(tx_data, bytes):
            tx_bytes = tx_data

        elif isinstance(tx_data, (list, tuple)):
            # e.g. [0x01, 0x54, 0x04]
            tx_bytes = bytes(tx_data)

        elif isinstance(tx_data, str):
            # e.g. "01 54 04" or "015404"
            tx_bytes = bytes.fromhex(tx_data)

        else:
            raise TypeError(f"Unsupported tx_data type: {type(tx_data)}")

        logger.info(
            f"RAW write_read | tx_len={len(tx_bytes)}, rx_len={rx_len}, delay={delay}"
        )

        if not self.ser or not self.ser.is_open:
            logger.error("RAW serial not open")
            raise RuntimeError("RAW serial not open")

        # Clear buffers
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

        # 🔹 Proper HEX logging (always padded)
        tx_hex = " ".join(f"{b:02X}" for b in tx_bytes)
        print(f"[RAW] TX ({len(tx_bytes)} bytes): {tx_hex}")
        logger.info(f"RAW TX | {tx_hex}")

        # Transmit
        self.ser.write(tx_bytes)
        self.ser.flush()

        # Wait
        time.sleep(delay)

        # Read response
        rx = self.ser.read(rx_len)

        if rx:
            rx_hex = " ".join(f"{b:02X}" for b in rx)
            print(f"[RAW] RX ({len(rx)} bytes): {rx_hex}")
            logger.info(f"RAW RX | {rx_hex}")
            return rx
        else:
            print("[RAW] RX timeout / no data")
            logger.warning("RAW RX timeout / no data")
            return b"NG"

    # -------------------------------------------------
    def close(self):
        if self.ser and self.ser.is_open:
            print("[RAW] Closing RAW serial port")
            logger.info("Closing RAW serial port")
            self.ser.close()
            logger.info("RAW serial port closed")

