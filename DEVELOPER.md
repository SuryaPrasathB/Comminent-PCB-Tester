# DEVELOPER GUIDE: Internal Engineering

> **PCB Tester Pro - System Architecture & Maintenance Guide**
>
> This document details the internal design, coding standards, and extension points for software engineers maintaining the PCB Tester Pro system.

---

## 🏛 Architectural Philosophy

### Design Goals
*   **Reliability First**: Prioritizes safety and fail-safe operation over raw speed. The system defaults to "All Off" on any exception.
*   **Modular Hardware**: Drivers are abstracted to allow swapping meter brands without rewriting the core logic.
*   **Thread Safety**: Critical because Modbus communication is shared between the main `TestRunner` and the background `SafetyMonitor`.
*   **Data Integrity**: Test results are committed to a local SQL database immediately upon completion to prevent data loss.

### Trade-offs
*   **Polling vs. Interrupts**: We use polling (200ms interval) for safety inputs due to the limitations of standard Modbus RTU over RS-485. This introduces a slight latency but ensures compatibility with standard PLCs.
*   **Synchronous UI**: While `QThread` handles execution, some DB operations block briefly to ensure ACID compliance.

---

## 🏗 Deep Architecture Breakdown

### 1. Application Core (`src/core/`)
*   **`test_runner.py`**: The heart of the system. Inherits `QThread`.
    *   **Responsibilities**: Orchestrates the test sequence, sends Modbus commands, validates measurements, emits signals to UI.
    *   **Key Method**: `run()` executes the test loop. `_execute_test()` handles a single step.
*   **`safety_monitor.py`**: A daemon thread.
    *   **Responsibilities**: Continuously polls PLC inputs 103 (Curtain) and 104 (E-Stop).
    *   **Mechanism**: Shares the `ModbusRTU` instance but uses a `threading.RLock` to prevent collisions.
*   **`modbus_driver.py`**: Wrapper around `pymodbus`.
    *   **Locking**: Implements `with self.lock:` for every read/write operation to ensure thread safety.
*   **`config.py`**: Central configuration registry.
    *   **Responsibilities**: Maps physical PLC coils to logical names (e.g., `T_530V` -> Coil 306). Defines meter register addresses.

### 2. User Interface (`src/ui/`)
*   **Framework**: PySide6 (Qt).
*   **Pattern**: Model-View-Controller (MVC) hybrid.
    *   **Views**: `src/ui/views/` (e.g., `execution.py`, `project_config.py`).
    *   **Forms**: `src/ui/forms/*.ui` (Qt Designer files, loaded dynamically via `QUiLoader`).
    *   **Theme**: `src/ui/theme.py` manages dynamic styling (Light/Dark mode) and CSS injection.

### 3. Database Layer
*   **Schema**: `projects` (Test configurations), `test_results` (Historical data), `users` (Auth).
*   **Access**: `src/core/db_utils.py` handles connection pooling and CRUD operations.
    *   **Safety**: Uses parameterized queries to prevent SQL injection.

---

## 🧵 Code Organization Rules

### Naming Conventions
*   **Classes**: `PascalCase` (e.g., `TestRunner`, `MainWindow`).
*   **Functions/Variables**: `snake_case` (e.g., `start_test`, `measured_voltage`).
*   **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`, `PLC_SLAVE_ID`).
*   **Private Members**: Prefix with `_` (e.g., `_stop_requested`).

### File Responsibilities
*   **`main.py`**: Entry point only. Setup `QApplication`, logging, and Login window.
*   **`src/core/drivers/*.py`**: Hardware communication only. No UI logic.
*   **`src/ui/views/*.py`**: UI logic and signal handling. No direct hardware calls (delegate to `TestRunner`).

---

## 🧠 Core Logic Walkthrough

### 1. Test Execution Lifecycle
1.  **Start**: User clicks "Start". `ExecutionView` validates inputs and instantiates `TestRunner`.
2.  **Init**: `TestRunner` initializes `ModbusRTU` connection.
3.  **Safety Start**: `SafetyMonitor` thread starts polling.
4.  **Loop**:
    *   **Setup**: Send Modbus write commands to set Voltage/Current relays on PLC.
    *   **Stabilize**: Sleep for `STABILIZATION_TIME` (1.5s).
    *   **Measure**: Read float values from AC/DC meters.
    *   **Validate**: Compare measured vs. expected.
    *   **Store**: Save result to DB.
    *   **Emit**: Send `result_signal` to UI for table update.
5.  **Cleanup**: Reset all relays to OFF. Stop `SafetyMonitor`. Close Modbus.

### 2. Communication Layers
*   **Modbus RTU**:
    *   **Baud**: 9600, 8, N, 1.
    *   **Timeout**: 1.0s.
    *   **Retry Logic**: Implemented in `ModbusRTU` class wrapper (3 retries on failure).
    *   **Endianness**: Handled per device in `config.py` (`ABCD` vs `CDAB` byte order).

### 3. State Management
*   **Global**: `SettingsManager` (Singleton) holds app-wide preferences.
*   **Session**: `LoginWindow` passes `role` to `MainWindow`.
*   **UI Sync**: The UI is purely reactive. It updates *only* when receiving signals from `TestRunner`.

---

## 🪵 Logging & Debugging

*   **Format**: `%(asctime)s - %(levelname)s - %(message)s`
*   **Storage**: `logs/test_log_YYYYMMDD_HHMMSS.txt`. Rotates daily.
*   **Levels**:
    *   `DEBUG`: Raw Modbus frames (Hex).
    *   `INFO`: High-level steps ("Starting Test SN 1").
    *   `WARNING`: Recoverable errors ("Retry 1/3").
    *   `ERROR`: Critical failures ("Emergency Stop", "DB Connection Lost").

### Tracing a Bug
1.  **Identify**: Check the UI status bar or error popup.
2.  **Locate**: Open the latest log file in `logs/`.
3.  **Search**: Find the timestamp of the error. Look for "Exception" or "Error".
4.  **Fix**: Trace the stack trace back to the source file.

---

## 🔧 Extending the System

### Adding a New Meter
1.  **Config**: Add the device definition to `SLAVE_DEVICES` in `src/core/config.py`.
    ```python
    "NEW_METER": {
        "slave_id": 5,
        "registers": {"VOLTAGE": 0x1000},
        "endian": "ABCD"
    }
    ```
2.  **Driver**: If it uses standard Modbus, no driver change needed. If proprietary, add a class in `src/core/drivers/`.
3.  **Logic**: Update `test_runner.py` to read from the new device key.

### Adding a New Test Type
1.  **Database**: Add columns to `projects` and `test_results` tables (e.g., `frequency_test`).
2.  **UI**: Update `project_config.ui` to include the new parameter input.
3.  **Runner**: Add a handler in `TestRunner._execute_test()` for the new logic.

---

## 🚀 Build & Deployment

### Development Build
```bash
# Run from source
python main.py
```

### Production Build (PyInstaller)
Use the provided `PCB_Tester.spec` file.

```bash
pyinstaller PCB_Tester.spec
```
*   **Output**: `dist/PCB_Tester/` (Single folder executable).
*   **Assets**: The `.spec` file ensures `src/ui/forms` and `src/ui/assets` are bundled.

### Versioning
*   **Format**: `vX.Y.Z` (Major.Minor.Patch).
*   **Update**: Manually update `VERSION` constant in `main.py` (if present) or `MainWindow` title.

---

## 🧪 Testing Strategy

*   **Unit Tests**: (Currently limited). Recommended for `db_utils` and `config` parsing.
*   **Integration Tests**: Run the software with a **Modbus Simulator** (e.g., Modbus Slave) to mock the PLC and Meters.
*   **Hardware-in-Loop (HIL)**: Final validation **must** be done on the physical Jig with a Gold Sample PCB.

---

## ⚠️ Known Limitations & Technical Debt

1.  **Modbus Blocking**: The `pymodbus` synchronous client blocks the thread during I/O. Future improvement: migrate to `asyncio` Modbus client.
2.  **Hardcoded Coils**: Some PLC coil addresses are magic numbers in `config.py`. Refactor to a purely config-driven mapping.
3.  **UI Threading**: Occasional UI freeze if DB write takes >500ms. Move DB writes to a separate `Worker` thread.

---

## 🤝 Contribution Guidelines

1.  **Branching**: Use `feature/xyz` or `bugfix/abc` branches. Never push to `main` directly.
2.  **Commits**: Use conventional commits (e.g., `feat: add new meter`, `fix: resolve crash on login`).
3.  **Review**: All PRs must be reviewed by at least one other engineer.
4.  **Formatting**: Follow **PEP 8**. Use `black` for auto-formatting.

---
**End of Developer Guide**
