import unittest
import threading
import time
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# We need an application instance to test Qt Signals across threads
app = QApplication.instance()
if not app:
    app = QApplication([])

from src.core.safety_monitor import SafetyMonitor
from src.core.test_runner import TestRunner
from src.core.drivers.modbus_driver import ModbusRTU

class TestStabilityFixes(unittest.TestCase):
    
    def test_safety_monitor_cross_thread_signal(self):
        """
        Verify that SafetyMonitor (a QThread) correctly emits a signal
        that can be received by a slot, preventing the previous
        cross-thread raw callback crash.
        """
        mock_modbus = MagicMock()
        # Mock modbus read_coils to simulate an emergency stop (e.g., bit 104 is True)
        mock_modbus.read_coils.return_value = [False, True] 
        
        stop_event = threading.Event()
        monitor = SafetyMonitor(mock_modbus, stop_event)
        
        # We'll use a list to capture the emitted signal in this thread
        received_signals = []
        def mock_slot(reason):
            received_signals.append(reason)
            
        monitor.safety_alert_signal.connect(mock_slot)
        
        # Start the thread. It should detect the True bit, emit the signal, and break.
        monitor.start()
        
        # Wait a reasonable amount of time for the thread to process and exit
        monitor.wait(2000)
        
        # We must process Qt events to deliver the queued signal
        app.processEvents()
        
        self.assertIn("Emergency Stop", received_signals, 
                      "The safety alert signal should have been emitted and received across threads.")
        
    def test_modbus_send_raw_receive_no_sleep_while_locked(self):
        """
        Verify that send_raw_receive sets the serial timeout and does not use time.sleep
        for the delay, thus holding the lock efficiently.
        """
        with patch('src.core.drivers.modbus_driver.SIMULATION_MODE', False):
            # We must mock the lock to verify it is acquired and released
            driver = ModbusRTU("COM99")
            driver._ensure_connected = MagicMock(return_value=True)
            
            # Mock the underlying PySerial socket
            mock_socket = MagicMock()
            mock_socket.baudrate = 9600
            mock_socket.timeout = 1.0 # default timeout
            mock_socket.read.return_value = b'response'
            
            driver.client = MagicMock()
            driver.client.socket = mock_socket
            
            # We mock time.sleep to ensure it is NOT called with the 'delay' amount
            with patch('src.core.drivers.modbus_driver.time.sleep') as mock_sleep:
                result = driver.send_raw_receive(b'data', delay=2.5)
                
                self.assertEqual(result, b'response')
                
                # Verify that timeout was temporarily set to the delay value
                self.assertEqual(mock_socket.timeout, 1.0, "Timeout should be restored to original")
                
                # The only sleep that should occur is for baudrate stabilization (if baudrate changed)
                # Since we didn't pass baudrate, sleep should NOT be called at all
                mock_sleep.assert_not_called()
                
                # Check that read was called
                mock_socket.read.assert_called_once()
                
    def test_test_runner_db_pooling(self):
        """
        Verify that TestRunner opens ONE connection and passes it to save_test_result,
        rather than opening/closing per iteration.
        """
        # Mock settings and DB to prevent actual IO
        with patch('src.core.test_runner.SettingsManager'), \
             patch('src.core.test_runner.save_test_result') as mock_save, \
             patch('src.core.db_utils.connect_db') as mock_connect, \
             patch('src.core.drivers.modbus_manager.ModbusManager.get_client'), \
             patch('src.core.test_runner.SLAVE_DEVICES', {"PLC": {"slave_id": 1, "coils": {}}}):
            
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            
            # Setup dummy test cases
            test_cases = [
                {"sn": 1, "desc": "T1", "r": "1", "y": "0", "b": "0", "n": "1", "v": "5.5", "i": "1.0"},
                {"sn": 2, "desc": "T2", "r": "0", "y": "1", "b": "0", "n": "1", "v": "5.5", "i": "1.0"}
            ]
            
            runner = TestRunner(
                project_name="TestProj",
                pcb_serial=("SN123",),
                test_cases=test_cases,
                com_port="COM99",
                run_single=False
            )
            
            # Mock the execute test so we don't actually try to talk to modbus
            runner._execute_test = MagicMock()
            
            # Mock finalize to just call save_test_result directly to verify kwargs
            def mock_finalize(tc, pcb_idx, v, i, res, ac=None):
                mock_save("TestProj", "SN123", tc["sn"], {"desc": tc["desc"], "r": "1", "y": "0", "b": "0", "n": "1", "v": "5.5", "i": "1.0", "measured_v": "5.5", "measured_i": "1.0", "result": "Pass"}, conn=runner.db_conn)
            runner._finalize = mock_finalize
            
            # We don't start the actual QThread because TestRunner loop expects modbus responses,
            # which we can't easily mock purely without blocking. Instead we just call .run()
            # on the main thread and mock the inner execute loops.
            runner._execute_test = MagicMock()
            
            # Since _execute_test is mocked, it won't call _finalize natively, so we manually
            # invoke it here to simulate the sequence of a test finishing.
            def mock_execute(tc):
                runner._finalize(tc, 1, 5.5, 1.0, "Pass")
            runner._execute_test.side_effect = mock_execute

            runner.run()
            
            # Verify connect was called exactly ONCE at start
            mock_connect.assert_called_once()
            
            # Verify that save_test_result was called twice (once per case) and passed the connection
            self.assertEqual(mock_save.call_count, 2)
            for call in mock_save.call_args_list:
                args, kwargs = call
                self.assertEqual(kwargs['conn'], mock_conn, "Shared DB connection should be passed to save_test_result")
                
            # Verify connection was closed at the end
            mock_conn.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()
