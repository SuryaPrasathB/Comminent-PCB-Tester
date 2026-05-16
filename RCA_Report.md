# ROOT CAUSE ANALYSIS REPORT

## 1. Executive Summary
The application crashes intermittently or hangs due to a deadlock and resource contention over the shared Modbus serial port connection (`ModbusRTU`). The deadlock is caused by the `SafetyMonitor` background daemon thread and the UI thread's `StartPoller` trying to acquire the same `ModbusRTU.lock` while competing with the main `TestRunner` thread. Additionally, there are severe cross-thread UI violations occurring when `TestRunner` signals are emitted and the database is updated directly from background threads, combined with recursive signal patterns during testing execution resulting in unhandled exceptions within the daemon threads that aren't caught by the main event loop.

## 2. Observed Symptoms
- Application crashes silently during test execution.
- Intermittent UI freezes when attempting to start a test or reset the PLC.
- High frequency of "Lock acquisition timeout" or "Modbus operation failed after 3 attempts" warnings in logs.
- Unhandled `BaseException`s logged from background threads (`TestRunner` and `SafetyMonitor`).
- UI becomes unresponsive ("Application Not Responding") occasionally on "Start".
- Missing last rows in database reports (race conditions).

## 3. Architecture Understanding
The application uses a hybrid MVC pattern built on PySide6 (Qt). 
- **Modbus Communication:** Managed centrally by `ModbusManager`, returning shared `ModbusRTU` singletons per COM port. `ModbusRTU` uses a `threading.RLock` to synchronize serial bus access.
- **Test Runner (`TestRunner`):** A `QThread` that sequences the test logic, performs heavy Modbus read/writes, writes to the SQL database, and emits signals to the UI.
- **Safety Monitor (`SafetyMonitor`):** A background daemon `threading.Thread` instantiated *inside* `TestRunner` that continuously polls safety coils via the *same* `ModbusRTU` singleton.
- **Start Poller (`StartPoller`):** A `QThread` instantiated by the main UI thread (`ExecutionView`) when idle to poll the PLC for a physical start button press using the *same* `ModbusRTU` singleton.

## 4. Most Probable Root Causes

### 1. Deadlock / Lock Starvation on `ModbusRTU.lock` (Confidence: 95%)
- **Technical Explanation:** `ModbusRTU` uses `self.lock = threading.RLock()` to serialize access. Both `StartPoller` (when idle), `TestRunner` (during test), and `SafetyMonitor` (during test) poll the same connection heavily. While `StartPoller` is stopped when tests start, it is killed non-gracefully (`time.sleep(0.1)` loop on `isRunning()`), sometimes leaving the lock in an undefined state. Furthermore, `ModbusRTU._retry_wrapper` sleeps *outside* the lock on retry, but `send_raw_receive` sleeps *inside* the lock (`time.sleep(delay)`). The `SafetyMonitor` polls every 1.0s, and `TestRunner` performs tight loops.
- **Why it causes crashes:** The UI thread calls `reset_table()` or `start_tests()`, which blocks on `ModbusManager.clear_client()` or UI updates. If `TestRunner` or `SafetyMonitor` holds the lock and hangs, or if the global crash handler catches an exception during this lock wait, the application crashes or freezes silently.
- **Evidence:** `DEVELOPER.md` notes "Occasional UI freeze if DB write takes >500ms" and "Modbus Blocking: The pymodbus synchronous client blocks the thread". The log shows lock acquisition timeouts.

### 2. Cross-Thread UI Violations and Database Blocking (Confidence: 90%)
- **Technical Explanation:** PySide6/Qt requires all UI updates to occur *only* on the main thread. While `TestRunner` correctly uses signals/slots for some updates, the `SafetyMonitor` callback (`self._safety_callback` -> `show_safety_popup`) is invoked directly from the `SafetyMonitor` daemon thread (a standard Python thread, not a `QThread`), which invokes `QMessageBox` and UI state changes directly from a background thread.
- **Why it causes crashes:** Calling Qt GUI functions from non-GUI threads results in memory corruption and segmentation faults (silent hard crashes in C++ space).
- **Evidence:** `SafetyMonitor` takes a `callback` and calls it directly: `self.callback("Emergency Stop")`. In `TestRunner`, `self._safety_callback` emits a signal but also does `self.safety_stop_signal.emit(reason)` which then connects to `show_safety_popup`. Depending on Qt connection types, emitting from a raw `threading.Thread` might not queue the signal properly. Also, `TestRunner` directly writes to SQLite, which locks the DB file.

### 3. Thread/Event Loop Starvation during Shutdown and Poller Reset (Confidence: 85%)
- **Technical Explanation:** In `ExecutionView._stop_polling()`, there is a busy-wait loop using `QApplication.processEvents()` mixed with `time.sleep(0.1)` while waiting for `self.poller` to stop.
- **Why it causes crashes:** Calling `processEvents()` inside a busy loop can cause recursive event processing and stack overflows, especially if timers or other signals trigger during the sleep. `StartPoller` has a hard timeout and then just abandons the thread (`self.poller = None`), leaving a rogue thread running and potentially holding the Modbus lock.
- **Evidence:** `_stop_polling` code shows: `while self.poller.isRunning() and time.time() < timeout: QApplication.processEvents(); time.sleep(0.1)`.

## 5. Crash Trigger Chain
1. User clicks "Start" or physically presses the Start button.
2. `StartPoller` detects the start, emits `start_signal`, and sets `self.running = False`.
3. `ExecutionView._stop_polling()` is called, blocking the main UI thread in a `processEvents()` loop waiting for `StartPoller` to die.
4. If `StartPoller` is blocked inside a Modbus read (due to synchronous serial I/O), the UI thread hangs for up to 5 seconds.
5. `TestRunner` starts and instantiates `SafetyMonitor`. Both begin aggressively querying `ModbusRTU`.
6. A Modbus read fails, triggering the `_retry_wrapper` which locks `ModbusRTU.lock`.
7. `SafetyMonitor` hits a critical exception or detects a safety event and calls `callback` directly on its thread, or `TestRunner` encounters a fatal Modbus error and invokes UI updates directly.
8. A segmentation fault occurs from cross-thread UI access, or the global exception hook catches a fatal error in a background thread and calls `sys.exit(1)`, bypassing normal Qt teardown.

## 6. Risky Code Patterns Found
1. **Direct UI Calls from Background Threads:** Passing a callback into a raw `threading.Thread` (`SafetyMonitor`) that eventually interacts with UI elements.
2. **Busy-Wait in UI Thread:** `while self.poller.isRunning(): QApplication.processEvents(); time.sleep(0.1)` is a massive anti-pattern in Qt.
3. **Improper Thread Lifecycle Management:** Abandoning running threads by setting `self.poller = None` if they don't exit in 5 seconds.
4. **Shared Mutable Lock with Synchronous I/O:** `ModbusRTU` holds an `RLock` across blocking I/O calls (`ser.read()`, `ser.write()`, `time.sleep()`), causing thread starvation.
5. **Database Connections in Threads:** Creating and closing SQLite connections repeatedly inside a high-frequency test loop (`TestRunner` loop).

## 7. Threading Analysis
- **GUI thread safety:** VIOLATED. `SafetyMonitor` executes callbacks that can trigger UI changes.
- **Background workers:** `TestRunner` (QThread) and `SafetyMonitor` (threading.Thread) and `StartPoller` (QThread) compete for the same hardware resource.
- **Signals/slots:** Used inconsistently. `StartPoller` uses signals, but `SafetyMonitor` uses raw callbacks.
- **Timers:** Used correctly for blinking, but misused in `_stop_polling()` with `time.sleep`.

## 8. Memory & Resource Analysis
- **Resource Leaks:** Modbus serial ports are held open indefinitely. If a thread is abandoned (`StartPoller`), it keeps a reference to `ModbusManager` and the serial port.
- **Database Leaks:** Repeated `connect_db` and closes in the test loop can exhaust file descriptors on Windows.

## 9. Performance Analysis
- **UI bottlenecks:** `processEvents()` loop in `_stop_polling`.
- **Blocking operations:** `time.sleep(delay)` *inside* the acquired `ModbusRTU.lock` during `send_raw_receive`.

## 10. Stability Recommendations

### Critical fixes
1. **Fix Cross-Thread UI Violations:** Change `SafetyMonitor` to inherit from `QThread` and use standard Qt `Signal/Slot` mechanisms (with `Qt.QueuedConnection`) instead of raw callbacks to communicate with `TestRunner` and the UI.
2. **Remove Busy-Wait:** Refactor `_stop_polling` to use an asynchronous approach. Send a stop signal to `StartPoller`, and connect its `finished` signal to a slot that starts `TestRunner`. Do not use `QApplication.processEvents()`.
3. **Fix Modbus Lock Contention:** Ensure no `time.sleep()` calls happen while holding `ModbusRTU.lock`.

### High priority fixes
1. **Graceful Thread Shutdown:** Ensure `StartPoller`, `SafetyMonitor`, and `TestRunner` implement proper interruptible wait states (using `QWaitCondition` or `threading.Event.wait(timeout)` instead of `time.sleep`).
2. **Database Pooling:** Open one database connection for the duration of the test run, rather than opening/closing per PCB per test step.

## 11. Instrumentation Recommendations
- **Logging:** Add thread IDs to all Qt signal emissions to verify which thread is actually executing the slot.
- **Crash Dump:** Integrate `faulthandler` module to capture C-level segmentation faults (which occur during cross-thread UI violations).

## 12. Reproduction Strategy
1. Launch the application and select a valid Project and COM port.
2. Quickly toggle between "Start" and "Stop" multiple times to rapidly spawn and kill `StartPoller` and `TestRunner` instances.
3. Alternatively, artificially introduce a delay in the Modbus hardware response (or use a slow simulator) to force the 5-second timeout in `_stop_polling`, abandoning a `StartPoller` thread. The next "Start" click will cause a lock collision and freeze/crash.

## 13. Final Conclusion
The single most likely root cause is a **Cross-Thread GUI Update Violation** originating from the `SafetyMonitor` daemon thread combined with **Thread Starvation/Deadlock** on the `ModbusRTU.lock`. When the safety monitor detects an anomaly or a Modbus read fails critically, it directly triggers callbacks that cascade into UI space from a non-main thread, instantly crashing the PySide6 application via a C++ segmentation fault that Python's `sys.excepthook` cannot catch.
