# test_runner.py
import math
import threading
import time

from PySide6.QtCore import QThread, Signal

import random
from src.core.db_utils import save_test_result
from src.core.drivers.modbus_driver import ModbusRTU
from src.core.safety_monitor import SafetyMonitor

from src.core.config import (
    SLAVE_DEVICES,
    VOLTAGE_TOLERANCE_PERCENT, VOLTAGE_TAPPINGS, CURRENT_TAPPINGS, CURRENT_TOLERANCE_PERCENT, STABILIZATION_TIME,
    MIN_IMPEDANCE_MOHM, VLL_TO_TAP, SIMULATION_MODE
)

from src.core.logger import logger

LIMIT_TABLE = {
    0.0:  {"v_upper": 5.75, "v_lower": 5.40},
    0.5:  {"v_upper": 5.75, "v_lower": 5.40},
    1.25: {"v_upper": 5.75, "v_lower": 5.30},
    2.5:  {"v_upper": 5.75, "v_lower": 5.10},
}

ZERO_CURRENT_LIMIT = 0.2

class TestRunner(QThread):
    result_signal = Signal(dict)
    finished_signal = Signal(str)
    error_signal = Signal(str)
    running_sn_signal = Signal(int)
    safety_stop_signal = Signal(str)

    def __init__(
            self,
            project_name,
            pcb_serial,
            test_cases,
            com_port,
            start_index=0,
            active_pcbs=(1,),  # 👈 ADD THIS
            run_single=False
    ):
        super().__init__()

        self.project_name = project_name
        self.pcb_serials  = pcb_serial  # tuple now
        self.test_cases   = test_cases
        self.start_index  = start_index
        self.run_single   = run_single
        self.com_port     = com_port
        self.active_pcbs  = active_pcbs

        self._stop_requested = False
        self._fatal_error = False
        self.modbus = None
        self.safety_monitor = None
        self.safety_stop_event = None

        print("[TEST] ====================================")
        print("[TEST] TestRunner initialized")
        print(f"[TEST] Project    : {project_name}")
        print(f"[TEST] PCB Serial : {pcb_serial}")
        print(f"[TEST] COM Port   : {com_port}")
        print(f"[TEST] Run Single : {run_single}")
        print(f"[TEST] Active PCBs: {active_pcbs}")

        logger.info("TestRunner initialized")
        logger.info(f"Project={project_name}, PCB={pcb_serial}, COM={com_port}, RunSingle={run_single}, ActivePCBs={active_pcbs}")

    # -------------------------------------------------
    # Logging helpers
    # -------------------------------------------------
    def _sep(self):
        print("[TEST] ------------------------------------")
        logger.info("------------------------------------")

    def _task_ok(self, msg):
        print(f"[TEST] {msg} : SUCCESS")
        logger.info(f"{msg} : SUCCESS")

    def _task_fail(self, msg, detail=""):
        print(f"[TEST] {msg} : FAILED ({detail})")
        logger.error(f"{msg} : FAILED ({detail})")

    # -------------------------------------------------
    def stop(self):
        print("[TEST] Stop requested by user")
        logger.warning("Stop requested by user")
        self._stop_requested = True

    # -------------------------------------------------
    def run(self):
        print("[TEST] ====================================")
        print("[TEST] Test execution started")
        logger.info("Test execution started")

        try:
            print(f"[TEST] Opening Modbus RTU on {self.com_port}")
            logger.info(f"Opening Modbus RTU on {self.com_port}")

            self.modbus = ModbusRTU(port=self.com_port)

            # -------------------------------------------------
            # START SAFETY MONITOR
            # -------------------------------------------------
            self.safety_stop_event = threading.Event()
            self.safety_monitor = SafetyMonitor(
                self.modbus,
                self.safety_stop_event,
                self._safety_callback
            )
            self.safety_monitor.start()
            logger.info("SafetyMonitor started within TestRunner")

            plc = SLAVE_DEVICES["PLC"]
            plc_slave = plc["slave_id"]
            coils = plc["coils"]

            if self.run_single:
                print(f" Single Test Case: {self.test_cases[self.start_index]}")
                logger.info("Running single test case")
                self._execute_test(self.test_cases[self.start_index])

            else:
                for tc in self.test_cases[self.start_index:]:
                    if self._stop_requested or self._fatal_error:
                        break
                    self._execute_test(tc)

        except Exception as e:
            logger.error(f"Fatal Modbus error: {e}")
            self._fatal_comm_error("Modbus", "-", e)

        finally:
            # STOP SAFETY MONITOR
            if self.safety_stop_event:
                self.safety_stop_event.set()
            if self.safety_monitor:
                self.safety_monitor.join()

            # SAFETY: FORCE MAINS OFF (always)
            if self.modbus:
                try:
                    plc = SLAVE_DEVICES["PLC"]
                    plc_slave = plc["slave_id"]
                    coils = plc["coils"]

                    print("[PLC] MAINS OFF (final safety)")
                    logger.info("MAINS OFF (final safety)")

                    self.modbus.write_coil( plc_slave,coils["MAIN_CONTACTOR"],False)
                    time.sleep(0.5)

                    # 2️⃣ Turn OFF all coils (including MAIN again — no issue)
                    print("[PLC] FINAL SAFETY RESET → ALL COILS OFF")
                    logger.info("FINAL SAFETY RESET → ALL COILS OFF")

                    for name, addr in coils.items():
                        try:
                            self.modbus.write_coil(plc_slave, addr, False)
                        except Exception as inner_e:
                            logger.warning(f"Failed to reset coil {name}: {inner_e}")


                except Exception as e:
                    logger.warning(f"Failed to turn MAINS OFF safely: {e}")

            # CLOSE MODBUS CONNECTION
            if self.modbus:
                print("[TEST] Closing Modbus connection")
                logger.info("Closing Modbus connection")
                try:
                    self.modbus.close()
                except Exception:
                    pass

            # FINAL STATUS REPORT
            if self._fatal_error:
                print("[TEST] Test execution stopped due to ERROR")
                logger.error("Test execution stopped due to ERROR")
                status = "error"
            elif self._stop_requested:
                print("[TEST] Test execution stopped by USER")
                logger.warning("Test execution stopped by USER")
                status = "stop_requested"
            else:
                print("[TEST] Test execution completed successfully")
                logger.info("Test execution completed successfully")
                status = "success"

            self.finished_signal.emit(status)

    # -------------------------------------------------
    def _execute_test(self, tc):
        sn = tc["sn"]

        self.running_sn_signal.emit(sn)

        self._sep()
        print(f"[TEST] Executing Test SN : {sn}")
        print(f"[TEST] Description       : {tc['desc']}")
        print(f"[TEST] R={tc['r']} Y={tc['y']} B={tc['b']} N={tc['n']}")

        logger.info(f"Executing Test SN={sn} | {tc['desc']}")

        plc = SLAVE_DEVICES["PLC"]
        plc_slave = plc["slave_id"]
        coils = plc["coils"]

        # =================================================
        # 1️⃣ IMPEDANCE TEST
        # =================================================
        if "Impedance" in tc["desc"]:
            self._sep()
            try:
                print("[TEST] Mode: Impedance test")

                for pcb in self.active_pcbs:
                    if self._stop_requested or self._fatal_error:
                        return

                    self._run_impedance_for_pcb(tc, pcb)

                return

            except Exception as e:
                self._fatal_comm_error("IMP_METER", "-", e)
                return

        # =================================================
        # 2️⃣ OTHER TEST CASES
        # =================================================
        self._sep()
        try:
            print("[TEST] Setting Voltage and Current Relays")
            logger.info("Setting Voltage and Current Relays")

            present_slave_name = plc.get("display_name")
            print(f"[PLC] Target Slave      : {present_slave_name}")
            print(f"[PLC] PLC Slave ID      : {plc_slave}")

            # =================================================
            # NEUTRAL OPTIONS
            # =================================================
            neutral_state = (tc["n"] == "C")
            print(f"[PLC] NEUTRAL coil -> {'ON (C)' if neutral_state else 'OFF (NC)'}")
            print(f"[PLC] WRITE coil NEUTRAL = {neutral_state}")
            self.modbus.write_coil(plc_slave, coils["NEUTRAL"], neutral_state)

            # =================================================
            # VOLTAGE TAPS (COMMON TRANSFORMER + PHASE ENABLES)
            # =================================================

            # Neutral logic (same as above, untouched)
            neutral_state = (tc["n"] == "C")

            # Phase voltage selections from test case
            rv = tc["r"]
            yv = tc["y"]
            bv = tc["b"]

            print(f"[TEST] Voltage selections → R={rv}, Y={yv}, B={bv}, Neutral={tc['n']}")

            # -------------------------------------------------
            # Phase ENABLE control
            print(f"[PLC] WRITE coil R_EN = {rv != 'NC'}")
            self.modbus.write_coil(plc_slave, coils["R_EN"], rv != "NC")

            print(f"[PLC] WRITE coil Y_EN = {yv != 'NC'}")
            self.modbus.write_coil(plc_slave, coils["Y_EN"], yv != "NC")

            print(f"[PLC] WRITE coil B_EN = {bv != 'NC'}")
            self.modbus.write_coil(plc_slave, coils["B_EN"], bv != "NC")

            print(
                f"[TEST] Phase enables → "
                f"R_EN={rv != 'NC'}, "
                f"Y_EN={yv != 'NC'}, "
                f"B_EN={bv != 'NC'}"
            )

            # -------------------------------------------------
            # Reset ALL transformer taps (COMMON)
            print("[PLC] Resetting ALL transformer taps (COMMON)")

            for name, addr in coils.items():
                if name.startswith("T_"):
                    print(f"[PLC] RESET coil {name}")
                    self.modbus.write_coil(plc_slave, addr, False)

            # -------------------------------------------------
            # Decide voltage to apply (first non-NC phase)
            # -------------------------------------------------
            # Decide voltage to apply (first non-NC phase)
            selected_voltage = None
            for v in (rv, yv, bv):
                if v != "NC":
                    selected_voltage = v
                    break

            if selected_voltage:
                print(f"[TEST] Selected voltage: {selected_voltage}")
                print("[PLC] Applying transformer tap using drawing mapping")

                # Neutral-specific handling for 240V
                if selected_voltage == "240V":
                    if neutral_state:
                        # Neutral connected → true phase voltage
                        tap_key = "240"
                        print("[PLC] Neutral CONNECTED → using T_240")
                    else:
                        # Neutral NC → phase voltage via transformer
                        tap_key = "138"
                        print("[PLC] Neutral NC → using T_138")
                else:
                    # All other voltages → normal mapping
                    tap_key = VLL_TO_TAP.get(selected_voltage,selected_voltage.replace("V", ""))

                print(f"[PLC] SET transformer tap T_{tap_key}")
                self.modbus.write_coil( plc_slave,coils[f"T_{tap_key}"],True)

            else:
                print("[TEST] No voltage applied (all phases NC)")

            # =================================================
            # CURRENT TAPS
            # =================================================
            print("[PLC] Resetting ALL current relays")

            for pcb in (1, 2):
                for cur in CURRENT_TAPPINGS:
                    if cur != "0A":
                        cur_key = cur.replace("A", "").replace(".", "_")
                        coil_name = f"CUR{pcb}_{cur_key}"
                        print(f"[PLC] RESET coil {coil_name}")
                        self.modbus.write_coil(plc_slave, coils[coil_name], False)

            # -------------------------------------------------
            # Apply current only to active PCBs
            if tc["i"] != "0A":
                cur_key = tc["i"].replace("A", "").replace(".", "_")

                for pcb in self.active_pcbs:
                    coil_name = f"CUR{pcb}_{cur_key}"
                    print(f"[PLC] SET current tap {coil_name}")
                    self.modbus.write_coil(plc_slave, coils[coil_name], True)
            else:
                print("[PLC] No current applied (0A selected)")

            print("[TEST] Waiting for stabilization (cool-down)")
            logger.info("Waiting for stabilization")
            time.sleep(STABILIZATION_TIME)

            self._task_ok("Setting Voltage and Current Relays")

            # =================================================
            # PCB 2 ENABLE RELAY
            # =================================================
            print("[PLC] Configuring PCB_2_EN relay")

            pcb2_enabled = (2 in self.active_pcbs)

            print(f"[PLC] WRITE coil PCB_2_EN = {pcb2_enabled}")
            self.modbus.write_coil(
                plc_slave,
                coils["PCB_2_EN"],
                pcb2_enabled
            )

            # =================================================
            # MAINS ON (for non-impedance tests only)
            # =================================================
            print("[PLC] MAINS ON → MAIN_CONTACTOR = ON")
            logger.info("MAINS ON → MAIN_CONTACTOR ON")

            self.modbus.write_coil( plc_slave, coils["MAIN_CONTACTOR"],True)

            # Allow contactor + transformer to settle
            time.sleep(STABILIZATION_TIME)

        except Exception as e:
            self._task_fail("Setting Voltage and Current Relays", present_slave_name)
            self._fatal_comm_error("PLC", present_slave_name, e)
            return

        # =================================================
        # 3️⃣ READ AC VOLTAGES
        # =================================================
        self._sep()
        try:
            print("[TEST] Reading AC Voltages")
            logger.info("Reading AC Voltages")

            ac = SLAVE_DEVICES["AC_METER"]
            endian = ac.get("endian", "ABCD")
            present_slave_name = ac.get("display_name")

            # ---------------------------------------------
            # Decide which voltages to read based on Neutral
            # ---------------------------------------------
            neutral_connected = (tc["n"] == "C")

            if neutral_connected:
                print("[TEST] Neutral CONNECTED → Reading Phase-to-Neutral Voltages")
                logger.info("Neutral CONNECTED → Reading Phase-to-Neutral Voltages")

                if SIMULATION_MODE:
                    r_v, y_v, b_v = (240.0 + random.uniform(-2, 2) for _ in range(3))
                else:
                    r_v = self.modbus.read_float(ac["slave_id"], ac["registers"]["R_N_VOLTAGE"], endian=endian)
                    y_v = self.modbus.read_float(ac["slave_id"], ac["registers"]["Y_N_VOLTAGE"], endian=endian)
                    b_v = self.modbus.read_float(ac["slave_id"], ac["registers"]["B_N_VOLTAGE"], endian=endian)

                print(f"[TEST] R-N Voltage = {r_v:.3f} V")
                print(f"[TEST] Y-N Voltage = {y_v:.3f} V")
                print(f"[TEST] B-N Voltage = {b_v:.3f} V")

                logger.info(
                    f"AC Voltages (P-N) → R-N={r_v:.3f}, Y-N={y_v:.3f}, B-N={b_v:.3f}"
                )

                ac_vals = {
                    "r_v": f"{r_v:.3f}",
                    "y_v": f"{y_v:.3f}",
                    "b_v": f"{b_v:.3f}",
                }

            else:
                print("[TEST] Neutral NC → Reading Phase-to-Phase  1")
                logger.info("Neutral NC → Reading Phase-to-Phase Voltages")

                if SIMULATION_MODE:
                    r_v, y_v, b_v = (415.0 + random.uniform(-5, 5) for _ in range(3))
                else:
                    r_v = self.modbus.read_float(ac["slave_id"], ac["registers"]["R_Y_VOLTAGE"], endian=endian)
                    y_v = self.modbus.read_float(ac["slave_id"], ac["registers"]["Y_B_VOLTAGE"], endian=endian)
                    b_v = self.modbus.read_float(ac["slave_id"], ac["registers"]["B_R_VOLTAGE"], endian=endian)

                print(f"[TEST] R-Y Voltage = {r_v:.3f} V")
                print(f"[TEST] Y-B Voltage = {y_v:.3f} V")
                print(f"[TEST] B-R Voltage = {b_v:.3f} V")

                logger.info(f"AC Voltages (P-P) → R-Y={r_v:.3f}, Y-B={y_v:.3f}, B-R={b_v:.3f}")

                ac_vals = {
                    "r_v": f"{r_v:.3f}",
                    "y_v": f"{y_v:.3f}",
                    "b_v": f"{b_v:.3f}",
                }

            self._task_ok("Reading AC Voltages")

        except Exception as e:
            self._task_fail("Reading AC Voltages", present_slave_name)
            self._fatal_comm_error("AC_METER", present_slave_name, e)
            return

        # =================================================
        # 4️⃣ READ DC METERS (PCB SPECIFIC)
        # =================================================
        self._sep()

        try:
            print("[TEST] Reading DC Voltage and Current")
            logger.info("Reading DC Voltage and Current")

            dc_results = {}

            # Parse expected values for simulation
            v_str = str(tc["v"].replace("V", "")).strip()
            expected_v = float(v_str) if v_str != "NA" else 0.0

            i_str = str(tc["i"].replace("A", "")).strip()
            expected_i = float(i_str) if i_str != "NA" else 0.0

            for pcb in self.active_pcbs:
                print(f"[TEST][PCB{pcb}] Reading DC meters")

                # ----------------------------------------
                # Select correct DC meters dynamically
                # ----------------------------------------
                dc_v_key = f"DC_V_METER_{pcb}"
                dc_i_key = f"DC_I_METER_{pcb}"

                dc_v = SLAVE_DEVICES[dc_v_key]
                dc_i = SLAVE_DEVICES[dc_i_key]

                if SIMULATION_MODE:
                    # Determine fail condition (5% chance to fail)
                    is_fail = random.random() < 0.05

                    if is_fail:
                        # Generate value well outside expected
                        measured_v = expected_v + random.choice([-1.0, 1.0]) * random.uniform(1.0, 5.0)
                        measured_i = expected_i + random.choice([-1.0, 1.0]) * random.uniform(0.5, 1.0)
                    else:
                        # Generate near expected values
                        # Adjust noise based on expectations
                        measured_v = expected_v + random.uniform(-0.1, 0.1) if expected_v > 0 else random.uniform(-0.2, 0.2)
                        measured_i = expected_i + random.uniform(-0.05, 0.05) if expected_i > 0 else random.uniform(-0.1, 0.1)
                else:
                    # Voltage
                    measured_v = self.modbus.read_float(
                        dc_v["slave_id"],
                        dc_v["registers"]["DC_VOLTAGE"],
                        endian=dc_v.get("endian", "ABCD")
                    )

                    # Current
                    measured_i = self.modbus.read_float(
                        dc_i["slave_id"],
                        dc_i["registers"]["DC_CURRENT"],
                        endian=dc_i.get("endian", "ABCD")
                    )

                print(f"[TEST][PCB{pcb}] DC → V={measured_v:.3f}  I={measured_i:.3f}")
                logger.info(f"[PCB{pcb}] DC → V={measured_v:.3f}, I={measured_i:.3f}")

                dc_results[pcb] = (measured_v, measured_i)

            self._task_ok("Reading DC Voltage and Current")

        except Exception as e:
            self._task_fail("Reading DC Voltage and Current", "DC_METER")
            self._fatal_comm_error("DC_METER", "-", e)
            return

        # =================================================
        # 5️⃣ VALIDATION
        # =================================================
        try:

            v_str = str(tc["v"].replace("V", "")).strip()
            expected_v = float(v_str)

            i_str = str(tc["i"].replace("A", "")).strip()
            expected_i = float(i_str)

            print(f"[TEST] expected_v: {expected_v}")
            print(f"[TEST] expected_i: {expected_i}")

            # -----------------------------------------
            # Get voltage limits from table
            # -----------------------------------------
            if expected_v == 0.0:
                v_upper = 0.5
                v_lower = -0.5
            else:
                if expected_i not in LIMIT_TABLE:
                    raise ValueError(f"No limits defined for load {expected_i}A")

                limits = LIMIT_TABLE[expected_i]
                v_upper = limits["v_upper"]
                v_lower = limits["v_lower"]

            # -----------------------------------------
            # Current limits
            # -----------------------------------------
            if expected_i == 0.0:
                i_upper = ZERO_CURRENT_LIMIT
                i_lower = -ZERO_CURRENT_LIMIT
            else:
                tol = expected_i * (CURRENT_TOLERANCE_PERCENT / 100)
                i_upper = expected_i + tol
                i_lower = expected_i - tol

            print(f"[TEST] Voltage limits: {v_lower} - {v_upper}")
            print(f"[TEST] Current limits: {i_lower} - {i_upper}")

        except Exception as e:
            print(f"[TEST] Exception occurred while setting limits: {e}")
            logger.error(f"Validation exception: {e}")
            # If we fail to compute limits, all PCBs fail
            for pcb in self.active_pcbs:
                v_meas, i_meas = dc_results.get(pcb, (None, None))
                self._finalize(tc, pcb, v_meas, i_meas, "Fail", ac_vals)
            return

        for pcb in self.active_pcbs:
            v_meas, i_meas = dc_results.get(pcb, (None, None))

            print(f"[TEST][PCB{pcb}] measured_v: {v_meas}")
            print(f"[TEST][PCB{pcb}] measured_i: {i_meas}")

            if v_meas is not None and i_meas is not None:
                voltage_pass = v_lower <= v_meas <= v_upper
                current_pass = i_lower <= i_meas <= i_upper

                result = "Pass" if (voltage_pass and current_pass) else "Fail"
            else:
                result = "Fail"

            print(f"[TEST][PCB{pcb}] Result = {result}")
            logger.info(f"[PCB{pcb}] Test Result = {result}")

            self._finalize(tc, pcb, v_meas, i_meas, result, ac_vals)

    # -------------------------------------------------
    def _finalize(self, tc, pcb_index, v, i, result, ac_vals=None):
        v_meas = f"{v:.3f}" if v is not None else "NA"
        i_meas = f"{i:.3f}" if i is not None else "NA"

        if not self.run_single:
            print("[TEST] Saving result to database")
            logger.info("Saving test result to database")

            pcb_serial = self.pcb_serials[pcb_index - 1]

            save_test_result(
                self.project_name,
                pcb_serial,
                tc["sn"],
                {
                    "desc": tc["desc"],
                    "r": tc["r"],
                    "y": tc["y"],
                    "b": tc["b"],
                    "n": tc["n"],
                    "v": tc['v'],
                    "i": tc['i'],
                    "measured_v": v_meas,
                    "measured_i": i_meas,
                    "result": result
                }
            )

        else:
            print("[TEST] Single-run mode → DB save skipped")
            logger.info("Single-run mode → DB save skipped")

        payload = {
            "sn": tc["sn"],
            "pcb_index": pcb_index,
            "v": tc['v'],
            "i": tc['i'],
            "measured_v": v_meas,
            "measured_i": i_meas,
            "result": result
        }

        if ac_vals is not None:
            if isinstance(ac_vals, dict):
                payload.update(ac_vals)
            else:
                print("[WARN] ac_vals ignored (not a dict):", ac_vals)
                logger.warning("ac_vals ignored (not a dict)")

        self.result_signal.emit(payload)

    # -------------------------------------------------
    def _run_impedance_for_pcb(self, tc, pcb_index):

        plc = SLAVE_DEVICES["PLC"]
        plc_slave = plc["slave_id"]
        coils = plc["coils"]

        prefix = f"IMP{pcb_index}"

        test_en = f"{prefix}_TEST_EN"
        r_coil = f"{prefix}_R"
        y_coil = f"{prefix}_Y"
        b_coil = f"{prefix}_B"
        n_coil = f"{prefix}_N"

        print(f"\n[TEST][PCB{pcb_index}] ===============================")
        print(f"[TEST][PCB{pcb_index}] Starting impedance measurement")


        # -------------------------------------------------
        # 2) FULL ELECTRICAL ISOLATION (VERY IMPORTANT)
        # -------------------------------------------------
        print("[PLC] Resetting ALL transformer taps (COMMON)")
        for tap in VOLTAGE_TAPPINGS:
            if tap == "NC":
                continue

            tap_key = VLL_TO_TAP.get(tap, tap.replace("V", ""))
            print(f"[PLC] RESET coil T_{tap_key}")
            self.modbus.write_coil(plc_slave,coils[f"T_{tap_key}"],False)

        # Disable phase contactors (very important before megger)
        # COmmon for both the PCBs
        print(f"[PCB{pcb_index}] Disabling phase contactors R/Y/B")
        self.modbus.write_coil(plc_slave, coils["R_EN"], False)
        self.modbus.write_coil(plc_slave, coils["Y_EN"], False)
        self.modbus.write_coil(plc_slave, coils["B_EN"], False)

        # Disable PCB 2 Contactor
        self.modbus.write_coil(plc_slave, coils["PCB_2_EN"], False)

        # Neutral OFF
        print(f"[PCB{pcb_index}] NEUTRAL OFF")
        self.modbus.write_coil(plc_slave, coils["NEUTRAL"], False)

        # Disable ALL current relays for BOTH PCBs
        print(f"[PCB{pcb_index}] Isolating current paths (CUR1 + CUR2 OFF)")
        for cur in CURRENT_TAPPINGS:
            if cur != "0A":
                cur_key = cur.replace('A', '').replace('.', '_')

                self.modbus.write_coil(plc_slave, coils[f"CUR1_{cur_key}"], False)
                self.modbus.write_coil(plc_slave, coils[f"CUR2_{cur_key}"], False)

                print(f"[PCB{pcb_index}] CUR1_{cur_key}=OFF , CUR2_{cur_key}=OFF")

        # -------------------------------------------------
        # 1) ENABLE IMPEDANCE PATH
        # -------------------------------------------------
        print(f"[PCB{pcb_index}] TEST PATH ENABLE")
        self.modbus.write_coil(plc_slave, coils[test_en], True)
        time.sleep(0.1)

        # -------------------------------------------------
        # 3) IMPEDANCE MEASUREMENT (PCB SPECIFIC METER)
        # -------------------------------------------------

        # Select correct impedance meter based on PCB
        imp_key = f"IMP_METER_{pcb_index}"
        imp = SLAVE_DEVICES[imp_key]

        slave = imp["slave_id"]
        endian = imp.get("endian", "ABCD")

        print(f"[PCB{pcb_index}] Using {imp['display_name']} (Slave {slave})")

        impedance_results = {}

        # Connect Neutral of selected PCB
        print(f"[PCB{pcb_index}] Connecting Neutral path")
        self.modbus.write_coil(plc_slave, coils[n_coil], True)
        time.sleep(0.15)

        for phase, coil_key, reg_key in [
            ("R", r_coil, "R_N_IMP"),
            ("Y", y_coil, "Y_N_IMP"),
            ("B", b_coil, "B_N_IMP"),
        ]:
            print(f"\n[PCB{pcb_index}] Measuring {phase}-N")

            # Always reset phases first (prevent leakage path)
            self.modbus.write_coil(plc_slave, coils[r_coil], False)
            self.modbus.write_coil(plc_slave, coils[y_coil], False)
            self.modbus.write_coil(plc_slave, coils[b_coil], False)

            time.sleep(0.05)

            # Enable selected phase
            print(f"[PCB{pcb_index}] Closing relay {coil_key}")
            self.modbus.write_coil(plc_slave, coils[coil_key], True)

            # Stabilization time for megger
            time.sleep(STABILIZATION_TIME)

            # Read impedance from correct meter
            if SIMULATION_MODE:
                # 5% chance to generate a failing impedance (< MIN_IMPEDANCE_MOHM)
                if random.random() < 0.05:
                    value = MIN_IMPEDANCE_MOHM * random.uniform(0.1, 0.9)
                else:
                    value = MIN_IMPEDANCE_MOHM + random.uniform(0.5, 5.0)
            else:
                value = self.modbus.read_float(
                    slave,
                    imp["registers"][reg_key],
                    endian=endian
                )

            impedance_results[phase] = value
            print(f"[PCB{pcb_index}] {phase}-N = {value:.3f} MΩ")

            # OPEN PHASE AFTER EACH MEASUREMENT (IMPORTANT SAFETY)
            self.modbus.write_coil(plc_slave, coils[coil_key], False)
            time.sleep(0.05)

        # -------------------------------------------------
        # 4) IMMEDIATELY DISABLE HIGH VOLTAGE PATH
        # -------------------------------------------------
        print(f"\n[PCB{pcb_index}] Disabling impedance path")

        self.modbus.write_coil(plc_slave, coils[test_en], False)
        self.modbus.write_coil(plc_slave, coils[r_coil], False)
        self.modbus.write_coil(plc_slave, coils[y_coil], False)
        self.modbus.write_coil(plc_slave, coils[b_coil], False)
        self.modbus.write_coil(plc_slave, coils[n_coil], False)

        # -------------------------------------------------
        # 5) VALIDATION
        # -------------------------------------------------
        all_pass = all(v > MIN_IMPEDANCE_MOHM for v in impedance_results.values())

        result_text = (
            f"Zrn={impedance_results['R']:.3f}MΩ, "
            f"Zyn={impedance_results['Y']:.3f}MΩ, "
            f"Zbn={impedance_results['B']:.3f}MΩ"
        )

        final_result = f"Pass ({result_text})" if all_pass else f"Fail ({result_text})"

        print(f"[PCB{pcb_index}] RESULT → {final_result}")

        # Send result to UI & DB
        self._finalize(tc, pcb_index, None, None, final_result,
                       {"r_v": "NA", "y_v": "NA", "b_v": "NA"})

    def _fatal_comm_error(self, device, slave_name, exc):
        self._fatal_error = True

        print("[ERROR] ====================================")
        print(f"[ERROR] Device : {device}")
        print(f"[ERROR] Slave  : {slave_name}")
        print(f"[ERROR] Reason : {exc}")

        logger.error(f"Fatal communication error → Device={device}, Slave={slave_name}, Reason={exc}")

        self.error_signal.emit(
            f"Fatal error\nDevice: {device}\nSlave: {slave_name}\n{exc}"
        )

    def _safety_callback(self, reason):
        print(f"[SAFETY] STOP TRIGGERED: {reason}")
        logger.warning(f"Safety Stop Triggered: {reason}")
        self._stop_requested = True
        self.safety_stop_signal.emit(reason)
