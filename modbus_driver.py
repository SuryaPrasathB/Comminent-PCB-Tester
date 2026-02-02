# modbus_driver.py
from pymodbus.client.serial import ModbusSerialClient
import struct
import logging

from logs import logger


class ModbusRTU:
    def __init__(self, port, baudrate=9600, timeout=1):
        logger.info(f"Initializing ModbusRTU | port={port}, baudrate={baudrate}, timeout={timeout}")

        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=timeout
        )

        if not self.client.connect():
            logger.error(f"Modbus RTU connection failed | port={port}")
            raise RuntimeError("Modbus RTU connection failed")

        logging.info("Modbus RTU connected")
        logger.info(f"Modbus RTU connected | port={port}")

    # ---------------- COILS ----------------
    def write_coil(self, slave, address, value: bool):
        logger.info(f"write_coil | slave={slave}, address={address}, value={value}")

        rq = self.client.write_coil(address, value, device_id=slave)
        if rq.isError():
            logger.error(f"Write coil failed | slave={slave}, address={address}")
            raise RuntimeError("Write coil failed")

    def read_coils(self, slave, address, count=1):
        logger.info(f"read_coils | slave={slave}, address={address}, count={count}")

        rr = self.client.read_coils(address, count=count, device_id=slave)
        if rr.isError():
            logger.error(f"Read coils failed | slave={slave}, address={address}")
            raise RuntimeError("Read coils failed")
        return rr.bits

    # ---------------- HOLDING REGISTERS ----------------
    def read_holding_registers(self, slave, address, count=2):
        logger.info(
            f"read_holding_registers | slave={slave}, address={address}, count={count}"
        )

        rr = self.client.read_holding_registers(address, count=count, device_id=slave)
        if rr.isError():
            logger.error(
                f"Read holding registers failed | slave={slave}, address={address}"
            )
            raise RuntimeError("Read holding registers failed")
        return rr.registers

    # ---------------- FLOAT HELPERS ----------------
    def read_float(self, slave, address, endian="ABCD"):
        """
        endian:
            'ABCD' → Big endian float (Impedance meter)
            'CDAB' → Word-swapped float (AC / DC meters)
        """
        logger.info(
            f"read_float | slave={slave}, address={address}, endian={endian}"
        )

        regs = self.read_holding_registers(slave, address, 2)

        if len(regs) != 2:
            logger.error(
                f"Invalid register count for float | slave={slave}, address={address}"
            )
            raise RuntimeError("Invalid register count for float")

        hi, lo = regs[0], regs[1]

        if endian == "ABCD":
            raw = struct.pack(">HH", hi, lo)
        elif endian == "CDAB":
            raw = struct.pack(">HH", lo, hi)
        else:
            logger.error(f"Unsupported endian mode: {endian}")
            raise ValueError(f"Unsupported endian mode: {endian}")

        value = struct.unpack(">f", raw)[0]
        logger.info(
            f"read_float success | slave={slave}, address={address}, value={value}"
        )

        return value

    def close(self):
        logger.info("Closing Modbus RTU connection")
        self.client.close()
        logging.info("Modbus RTU closed")
        logger.info("Modbus RTU closed")
