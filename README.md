# PCB Tester Pro

> **Automated Industrial Quality Assurance System for PCB Manufacturing**

**PCB Tester Pro** is a mission-critical, industrial-grade software solution designed to automate the electrical testing and validation of Power Supply Unit (PSU) Printed Circuit Boards (PCBs). It replaces manual multimeter testing with a high-speed, safety-critical automated test sequence, ensuring consistent quality and operator safety.

This system is built for **Manufacturing Engineers**, **Test Operators**, and **Quality Assurance Managers** who require reliable, traceable, and high-throughput testing in a factory environment.

---

## 🏗 High-Level Architecture

The system operates as a **SCADA-lite** control application, orchestrating hardware instruments via a centralized Modbus RTU bus.

```ascii
+-----------------+      Modbus RTU       +------------------+
|   Host PC       | <--- (RS-485) ------> |    PLC Controller|
| (PCB Tester Pro)|                       | (Master Control) |
+-----------------+                       +---------+--------+
        |                                           |
        | SQL                                       | 24V I/O
        v                                           v
+-----------------+                       +------------------+
|   MySQL DB      |                       |   Test Jig       |
| (Results/Logs)  |                       | (Relays/Sensors) |
+-----------------+                       +---------+--------+
                                                    |
                                          +---------+--------+
                                          | Meters (AC/DC/Z) |
                                          | (Slave Devices)  |
                                          +------------------+
```

### Data Flow
1.  **User Input**: Operator scans a QR code (PCB Serial) and selects a Test Project.
2.  **Configuration**: System loads the test sequence (Voltage taps, Current limits) from the local MySQL database.
3.  **Orchestration**: The `TestRunner` thread sends Modbus commands to the PLC to configure the relay matrix (Jig).
4.  **Measurement**: The system polls AC/DC meters and Impedance testers for readings.
5.  **Validation**: Measured values are compared against defined tolerances (`±20%`).
6.  **Safety**: A dedicated `SafetyMonitor` thread continuously polls Emergency Stop and Curtain Sensors.
7.  **Reporting**: Results are saved to the database and exported to Excel reports.

---

## 🌟 Key Features

*   **Automated Test Sequences**: Executes complex voltage/current injection and measurement scenarios automatically.
*   **Dual PCB Testing**: Supports simultaneous or sequential testing of two PCBs (Slots 1 & 2) in a single jig.
*   **Real-time Safety Monitoring**: Dedicated background thread monitors safety inputs (E-Stop, Light Curtains) with <200ms reaction time.
*   **Database-Driven Configuration**: Test plans are stored in MySQL, allowing dynamic reconfiguration without code changes.
*   **Role-Based Access Control**: Secure login for Operators (Run-only) and Engineers (Edit configurations).
*   **Comprehensive Reporting**: Generates detailed Excel reports with Pass/Fail status, timestamps, and measurement data.
*   **Visual Feedback**: Industrial UI with clear color-coding (Green=Pass, Red=Fail, Orange=Testing).
*   **Hardware Abstraction**: Modular driver architecture allows swapping meter brands with minimal code changes.

---

## 🛠 Technology Stack

### Core Application
*   **Language**: Python 3.10+
*   **GUI Framework**: PySide6 (Qt for Python)
*   **Concurrency**: `QThread` for non-blocking UI, `threading` for background safety monitoring.

### Data & Communication
*   **Database**: MySQL (via `mysql-connector-python`)
*   **Protocol**: Modbus RTU (via `pymodbus`)
*   **Serial**: `pyserial` for QR Scanners.

### Reporting & Utilities
*   **Excel Export**: `openpyxl`
*   **Logging**: Standard `logging` module with file rotation.

### Hardware Ecosystem
*   **PLC**: Standard Modbus-compatible PLC (e.g., Delta, Mitsubishi).
*   **Meters**: Digital Power Meters (AC/DC), Insulation Resistance Testers.
*   **Scanners**: Standard USB/Serial QR Code Readers.

---

## 📂 Folder Structure

```text
.
├── main.py                     # Application Entry Point
├── requirements.txt            # Python Dependencies
├── user_settings.json          # Local User Preferences
├── src/
│   ├── core/                   # Backend Business Logic
│   │   ├── config.py           # Hardware Mappings & Constants
│   │   ├── db_utils.py         # Database CRUD Operations
│   │   ├── logger.py           # Logging Configuration
│   │   ├── report_generator.py # Excel Report Logic
│   │   ├── safety_monitor.py   # Background Safety Thread
│   │   ├── test_runner.py      # Main Test Execution Engine
│   │   └── drivers/            # Hardware Drivers (Modbus, Serial)
│   └── ui/                     # Frontend UI (PySide6)
│       ├── forms/              # .ui files (Qt Designer)
│       ├── views/              # View Logic (Controllers)
│       ├── main_window.py      # Main Application Shell
│       ├── theme.py            # Styling & Theme Management
│       └── assets/             # Images & Icons
└── Report Export/              # Output Directory for Excel Reports
```

---

## 🚀 Installation & Setup

### Prerequisites
1.  **Operating System**: Windows 10/11 (Recommended for driver support).
2.  **Python**: Version 3.10 or higher.
3.  **Database**: MySQL Server 8.0+ installed and running locally.

### Installation Steps

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/your-org/pcb-tester-pro.git
    cd pcb-tester-pro
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Database Setup**:
    *   Ensure MySQL is running on `localhost:3306`.
    *   Credentials default to `root` / `lscontrols` (Configurable in `src/core/config.py`).
    *   The application automatically creates the schema (`pcb_tester` database) on first run.

4.  **Hardware Configuration**:
    *   Connect the USB-RS485 adapter.
    *   Verify the COM port in Device Manager.
    *   Update `user_settings.json` or the UI Settings with the correct COM port.

---

## ⚡ Quick Start

1.  **Launch the Application**:
    ```bash
    python main.py
    ```

2.  **Login**:
    *   **Operator**: Default credentials (if configured) or Guest access.
    *   **Admin**: Use administrator credentials for configuration access.

3.  **Run a Test**:
    *   Navigate to **Execution View**.
    *   Select a **Project** from the dropdown.
    *   Scan or enter **PCB Serial Numbers**.
    *   Ensure the Jig is closed and safe.
    *   Click **START**.

---

## 🖥 User Interface Overview

*   **Login Screen**: Secure entry point handling user authentication.
*   **Execution View**: The main operator dashboard. Displays real-time test status, live measurements, and Pass/Fail results.
*   **Project Configuration**: (Admin only) Editor for defining test steps, voltage levels, and expected values. Includes a circuit preview.
*   **Settings**: Application preferences (Theme, COM Port, Report Paths).
*   **Logs**: Historical view of system events and errors for troubleshooting.

---

## ⚠️ Safety & Industrial Considerations

This software controls high-voltage equipment. Safety is paramount.

*   **Fail-Safe Design**: The system defaults to an "All Off" state upon initialization or critical error.
*   **Emergency Stop**: Hardwired E-Stop buttons are monitored via software (PLC Input 104). Triggering E-Stop immediately aborts the test and opens the Main Contactor.
*   **Light Curtain**: Accessing the test area (PLC Input 103) during operation triggers an immediate safety stop.
*   **Watchdog**: Communication timeouts (>1s) with the PLC cause the system to halt execution to prevent "zombie" states.

---

## 📄 License & Usage

**Proprietary Software**.
Copyright © 2024 L S Control Systems. All Rights Reserved.

*   **Internal Use Only**: This software is intended solely for use within designated manufacturing facilities.
*   **No Warranty**: Provided "as is" without warranty of any kind. The authors are not liable for hardware damage caused by misuse.

---
**Maintained by**: Development Team @ L S Control Systems
**Contact**: development@lscssystems.com
