# HOW TO USE: Operator & User Manual

> **PCB Tester Pro - System Manual**
>
> This document provides step-by-step instructions for operating the PCB Tester Pro software safely and efficiently.

---

## 🚦 First-Time Setup Walkthrough

### 1. Power-On Sequence
1.  **Main Power**: Switch ON the main AC supply to the Test Jig cabinet.
    *   *Verify*: Green "POWER ON" indicator on the cabinet front panel.
2.  **Instruments**: Ensure all meters (AC, DC, Impedance) are powered ON.
    *   *Verify*: Displays are active and showing "0.00" or idle state.
3.  **PC Boot**: Turn on the Host PC.
    *   *Verify*: Windows desktop loads successfully.

### 2. Software Startup
1.  **Launch**: Double-click the **PCB Tester Pro** shortcut on the desktop.
    *   *Verify*: The application splash screen (if any) or Login Window appears.
2.  **Login**: Enter your authorized username and password.
    *   *Note*: Contact your supervisor if you do not have credentials.
    *   *Role Check*: Ensure you see the correct role (Operator vs. Engineer) in the title bar after login.

### 3. Connection Check
1.  **Status Bar**: Check the bottom status bar for "PLC Connected" or "System Ready".
2.  **COM Port**: If you see a "Connection Error", go to **Settings** and verify the COM Port (e.g., `COM3`, `COM4`).
    *   *Action*: Select the correct port and click "Save". Restart if necessary.

---

## 🖥 UI Walkthrough (Screen-by-Screen)

### 1. Execution View (Main Dashboard)
The primary screen for daily testing operations.

*   **Top Section (Configuration)**:
    *   **Project**: Dropdown to select the PCB model/test plan.
    *   **PCB Serial 1**: Input field for the first PCB's serial number (scan or type).
    *   **PCB Serial 2**: Input field for the second PCB's serial number.
    *   **COM Port**: Quick display of the active communication port.
*   **Middle Section (Results Tables)**:
    *   Two tables (Left = PCB 1, Right = PCB 2) showing real-time test steps.
    *   **Columns**: Step No, Description, Expected V/I, Measured V/I, Result.
    *   **Color Coding**:
        *   ⬜ White: Pending
        *   🟧 Orange: Testing in progress
        *   🟩 Green: Pass
        *   🟥 Red: Fail
*   **Bottom Section (Controls)**:
    *   **START (Green)**: Initiates the automated test sequence. Active only when ready.
    *   **STOP (Red)**: Immediately aborts the test for safety.
    *   **RESET (Gray)**: Clears results and resets the jig state.
    *   **Status Label**: "Waiting for Start..." (Blinking Orange) indicates readiness.

### 2. Project Configuration (Admin Only)
Used to create or modify test plans.

*   **Project List**: Left sidebar showing saved test plans.
*   **Test Steps Table**: Main grid to define voltage/current injections.
    *   **Description**: What this step tests (e.g., "5V Rail Load Test").
    *   **R / Y / B / N**: Relay settings for Red, Yellow, Blue phases and Neutral.
    *   **Expected V / I**: Target values for Pass/Fail criteria.
*   **Circuit Preview**: A visual diagram (dynamic SVG) showing the relay configuration for the selected step. Hover to zoom.

### 3. Settings View
Global application preferences.

*   **Theme**: Toggle between Light and Dark mode.
*   **Report Export**: Configure where Excel reports are saved.
*   **About**: Software version and support contact info.

---

## 🔄 Typical Workflows

### 🛠 Workflow A: Standard Production Testing

1.  **Preparation**:
    *   Place **PCB 1** and **PCB 2** into the test jig slots.
    *   **Close the Jig Lid** securely (Safety Switch must engage).
2.  **Setup**:
    *   Select the correct **Project** from the dropdown menu.
    *   Click into "PCB Serial 1" and scan the QR code on the first board.
    *   Click into "PCB Serial 2" and scan the QR code on the second board.
3.  **Execution**:
    *   Press the **START** button on the screen (or physical Start button if integrated).
    *   *Observe*: The table rows will highlight in Orange as tests proceed.
    *   *Listen*: Relays will click as voltages change. **Do not open the jig.**
4.  **Completion**:
    *   The system will display a final "PASS" or "FAIL" popup/status.
    *   **PASS**: Remove PCBs and place in the "Accepted" bin.
    *   **FAIL**: Remove PCBs and place in the "Reject/Rework" bin. Report generated automatically.

### 📏 Workflow B: Calibration / Verification
(Performed by Technicians/Engineers)

1.  **Setup**:
    *   Use a "Master Gold Sample" PCB with known values.
    *   Select the "Calibration_Project" (if created).
2.  **Run Test**:
    *   Execute a single cycle.
3.  **Verify**:
    *   Compare the "Measured V" and "Measured I" columns against the Gold Sample's datasheet.
    *   If variance is >1%, hardware calibration of the meters may be required.

---

## ⚙️ Configuration Guide

### User Settings (`user_settings.json`)
Accessible via the **Settings** menu.

| Parameter | Type | Default | Impact |
| :--- | :--- | :--- | :--- |
| `theme` | String | "Light" | UI appearance (Light/Dark). |
| `com_port` | String | "COM1" | The USB-Serial port for the PLC. Critical for connection. |
| `report_path` | String | "Report Export" | Folder where Excel files are saved. |
| `template_path` | String | "active_template.xlsx" | The Excel template used for generating reports. |

### Test Parameters (Database)
Managed via **Project Configuration**.

*   **Voltage Taps**: Available levels: 138V, 144V, 240V, 265V, 500V, 510V, 520V, 530V.
*   **Current Taps**: Available limits: 0.5A, 1.25A, 2.5A.
*   **Tolerances**: Fixed at ±20% in system config (not user-changeable).

---

## ⚠️ Error Handling & Troubleshooting

| Symptom | Probable Cause | Corrective Action |
| :--- | :--- | :--- |
| **"Modbus Connection Failed"** | USB cable loose or wrong COM port. | Check USB connection. Verify COM port in Device Manager & Settings. |
| **"Emergency Stop Triggered"** | E-Stop button pressed. | Release the red E-Stop button on the jig. Press RESET in software. |
| **"Curtain Sensor Triggered"** | Hand or object in jig area. | Clear the test area. Ensure jig lid is closed. Press RESET. |
| **"Read Error (Timeout)"** | Meter powered off or disconnected. | Check power to AC/DC meters. Check RS485 wiring. |
| **Test Stuck on "Testing..."** | Software crash or loop. | Click STOP. If unresponsive, restart the application. |

---

## ✅ Dos & Don'ts

### DO:
*   ✅ **Always** visually inspect PCBs for short circuits *before* placing them in the jig.
*   ✅ **Always** wait for the "Test Completed" message before opening the jig.
*   ✅ **Always** check that the correct Project is selected for the PCB model.
*   ✅ **Regularly** clean the jig contacts to ensure good electrical connection.

### DO NOT:
*   ❌ **NEVER** touch the PCBs or Jig internals while the test is running (High Voltage Hazard!).
*   ❌ **NEVER** bypass safety switches (Lid Sensor / Curtain) with tape or tools.
*   ❌ **Do not** unplug USB cables while the software is running.
*   ❌ **Do not** modify the `user_settings.json` file manually unless instructed by IT.

---

## 🔧 Maintenance & Daily Use

### Daily Startup Checklist
1.  [ ] Clean test jig pins with an ESD brush.
2.  [ ] Verify E-Stop function (Press E-Stop → Verify software shows error).
3.  [ ] Run one "Dummy Test" to ensure all relays click and meters read.

### Shutdown Procedure
1.  Close the **PCB Tester Pro** application (Click 'X' or Exit).
2.  Turn OFF the Test Jig cabinet power.
3.  Shut down the PC.

### Backups
*   **Reports**: The "Report Export" folder should be backed up to a network drive weekly.
*   **Database**: The MySQL database (`pcb_tester`) should be dumped/backed up monthly by IT.

---
**End of Operator Manual**
