from pymodbus.client.serial import ModbusSerialClient
import inspect

client = ModbusSerialClient(port="COM1")
print(f"write_coil signature: {inspect.signature(client.write_coil)}")
print(f"read_coils signature: {inspect.signature(client.read_coils)}")
print(f"read_holding_registers signature: {inspect.signature(client.read_holding_registers)}")
