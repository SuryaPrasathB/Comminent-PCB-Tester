# test_runner.py
import math
import threading
import time

from PySide6.QtCore import QObject, Signal

import random
from src.core.db_utils import save_test_result
from src.core.drivers.modbus_driver import ModbusRTU
from src.core.safety_monitor import SafetyMonitor

from src.core.config import (
    SLAVE_DEVICES,
    VOLTAGE_TOLERANCE_PERCENT, VOLTAGE_TAPPINGS, CURRENT_TAPPINGS,
    MIN_IMPEDANCE_MOHM, VLL_TO_TAP, SIMULATION_MODE
)

from src.core.logger import logger
from src.ui.settings_manager import SettingsManager

class TestSignals(QObject):
    # sn, pcb_index, r_v, y_v, b_v, measured_v, measured_i, result
    result_signal = Signal(int, int, str, str, str, float, float, str)
    finished_signal = Signal(str)
    error_signal = Signal(str)
    running_sn_signal = Signal(int)
    safety_stop_signal = Signal(str)

_test_signal_refs = []

class TestRunner:

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
        self.signals = TestSignals()
        _test_signal_refs.append(self.signals)
        self._thread = threading.Thread(target=self.run, daemon=True)

        self.project_name = project_name
        self.pcb_serials  = pcb_serial  # tuple now
        self.test_cases   = test_cases
        self.start_index  = start_index
        self.run_single   = run_single
        self.com_port     = com_port
        
        valid_pcbs = []
        for pcb in active_pcbs:
            idx = pcb - 1
            if idx < len(pcb_serial):
                serial = pcb_serial[idx]
                if serial and "NG" in serial.upper():
                    print(f"[TEST] PCB {pcb} QR is NG. Skipping this PCB.")
                else:
                    valid_pcbs.append(pcb)
            else:
                valid_pcbs.append(pcb)
        
        self.active_pcbs = tuple(valid_pcbs)

        self._stop_requested = False
        self._fatal_error = False
        self.modbus = None
        self.safety_monitor = None
        self.safety_stop_event = None
        self.db_conn = None

        print("[TEST] ====================================")
        print("[TEST] TestRunner initialized")
        print(f"[TEST] Project    : {project_name}")
        print(f"[TEST] PCB Serial : {pcb_serial}")
        print(f"[TEST] COM Port   : {com_port}")
        print(f"[TEST] Run Single : {run_single}")
        print(f"[TEST] Active PCBs: {active_pcbs}")

        logger.info("TestRunner initialized")
        logger.info(f"Project={project_name}, PCB={pcb_serial}, COM={com_port}, RunSingle={run_single}, ActivePCBs={active_pcbs}")

        # Load dynamic test parameters from SettingsManager
        self.settings = SettingsManager().get_setting("test_parameters", {})
        self.stabilization_time = float(self.settings.get("stabilization_time", 2.0))
        self.current_tolerance_percent = float(self.settings.get("current_tolerance_percent", 20.0))
        self.zero_current_limit = float(self.settings.get("zero_current_limit", 0.2))

        raw_limits = self.settings.get("limit_table", {
            "0.0": {"v_upper": 5.75, "v_lower": 5.40},
            "0.5": {"v_upper": 5.75, "v_lower": 5.40},
            "1.25": {"v_upper": 5.75, "v_lower": 5.30},
            "2.5": {"v_upper": 5.75, "v_lower": 5.10}
        })

        # Convert string keys to floats for easier lookup later
        self.limit_table = {}
        for k, v in raw_limits.items():
            try:
                self.limit_table[float(k)] = v
            except ValueError:
                pass

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

    def _interruptible_sleep(self, seconds):
        """Sleeps interruptibly, allowing immediate exit if stop is requested."""
        if seconds <= 0: return
        if self.safety_stop_event:
            self.safety_stop_event.wait(seconds)
        else:
            time.sleep(seconds)

    # -------------------------------------------------
    def start(self):
        self._thread.start()

    def isRunning(self):
        return self._thread.is_alive()

    def wait(self, timeout=None):
        if timeout:
            self._thread.join(timeout / 1000.0)
            return not self._thread.is_alive()
        else:
            self._thread.join()
            return True

    def run(self):
        threading.current_thread().name = "TestRunner"
        print("[TEST] ====================================")
        print("[TEST] Test execution started")
        logger.info("Test execution started")

        if not self.active_pcbs:
            print("[TEST] No valid PCBs to test (e.g. all NG). Aborting run.")
            logger.warning("No valid PCBs to test. Aborting run.")
            self._fatal_error = True

        try:
            from src.core.db_utils import connect_db
            self.db_conn = connect_db()
            
            print(f"[TEST] Opening Modbus RTU on {self.com_port}")
            logger.info(f"Opening Modbus RTU on {self.com_port}")

            from src.core.drivers.modbus_manager import ModbusManager
            self.modbus = ModbusManager.get_client(port=self.com_port, timeout=2.0)

            # -------------------------------------------------
            # START SAFETY MONITOR
            # -------------------------------------------------
            self.safety_stop_event = threading.Event()
            self.safety_monitor = SafetyMonitor(
                self.modbus,
                self.safety_stop_event
            )
            # Connect using queued connection implicitly via Qt when cross-thread
            self.safety_monitor.signals.safety_alert_signal.connect(self._safety_callback)
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
                total_start = time.time()
                count = 0
                for tc in self.test_cases[self.start_index:]:
                    if self._stop_requested or self._fatal_error:
                        break
                    case_start = time.time()
                    self._execute_test(tc)
                    # Idle time to let the bus breathe for SafetyMonitor/QR
                    self._interruptible_sleep(0.1)
                    case_duration = time.time() - case_start
                    logger.info(f"Test case SN={tc['sn']} took {case_duration:.2f}s")
                    count += 1
                
                total_duration = time.time() - total_start
                logger.info(f"Total execution of {count} test cases took {total_duration:.2f}s ({total_duration/60:.2f} mins)")

        except Exception as e:
            logger.error(f"Fatal Modbus error: {e}")
            self._fatal_comm_error("Modbus", "-", e)
        except BaseException as be:
            logger.error(f"CRITICAL BASE EXCEPTION in TestRunner: {be}")
            import traceback
            logger.error(traceback.format_exc())
            self._fatal_error = True

        finally:
            if self.db_conn:
                try:
                    self.db_conn.close()
                except Exception as e:
                    logger.warning(f"Error closing DB connection: {e}")
                self.db_conn = None
                
            # STOP SAFETY MONITOR
            if self.safety_stop_event:
                self.safety_stop_event.set()
            if self.safety_monitor:
                try:
                    self.safety_monitor.wait(10000)
                    if self.safety_monitor.isRunning():
                        logger.warning("SafetyMonitor failed to wait in time")
                except Exception as e:
                    logger.warning(f"Error waiting SafetyMonitor: {e}")

            # SAFETY: FORCE MAINS OFF (always)
            if self.modbus:
                try:
                    plc = SLAVE_DEVICES["PLC"]
                    plc_slave = plc["slave_id"]
                    coils = plc["coils"]

                    print("[PLC] MAINS OFF (final safety)")
                    logger.info("MAINS OFF (final safety)")

                    self.modbus.write_coil( plc_slave,coils["MAIN_CONTACTOR"],False)
                    self.modbus.sleep_worker(2.0)
                    time.sleep(0.5)                    # 2️⃣ Turn OFF all relays in a batch (addresses 1-31 are contiguous relays)
                    # We avoid writing to 35, 102+ which are inputs
                    start_cleanup = time.time()
                    logger.info("Performing batch relay reset (Addresses 1-31)")
                    try:
                        # Create a list of 31 'False' values
                        reset_vals = [False] * 31
                        self.modbus.write_coils(plc_slave, 1, reset_vals)
                    except Exception as batch_e:
                        logger.warning(f"Batch reset failed, falling back to sequential: {batch_e}")
                        # Fallback just in case
                        for name, addr in coils.items():
                            try:
                                if addr <= 31: # Only reset outputs
                                    self.modbus.write_coil(plc_slave, addr, False)
                            except Exception: pass
                    cleanup_duration = time.time() - start_cleanup
                    logger.info(f"Cleanup finished in {cleanup_duration:.4f}s")


                except Exception as e:
                    logger.warning(f"Failed to turn MAINS OFF safely: {e}")

            # CLOSE MODBUS CONNECTION
            if self.modbus:
                print("[TEST] Modbus connection kept open by manager")
                logger.info("Modbus connection kept open by manager")
                # try:
                #     self.modbus.close()
                # except Exception:
                #     pass

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

            try:
                self._safe_emit(self.signals.finished_signal, status)
            except Exception as e:
                logger.error(f"Failed to emit finished_signal: {e}")

    # -------------------------------------------------
    def _execute_test(self, tc):
        sn = tc["sn"]

        self.signals.running_sn_signal.emit(sn)

        self._sep()
        print(f"[TEST] Executing Test SN : {sn}")
        print(f"[TEST] Description       : {tc['desc']}")
        print(f"[TEST] R={tc['r']} Y={tc['y']} B={tc['b']} N={tc['n']}")

        logger.info(f"Executing Test SN={sn} | {tc['desc']}")

        plc = SLAVE_DEVICES["PLC"]
        plc_slave = plc["slave_id"]
        coils = plc["coils"]

        # PREVENT HOT SWITCHING: Always ensure MAINS is OFF before any new test case configures relays
        print("[PLC] MAINS OFF (pre-test safety)")
        self.modbus.write_coil(plc_slave, coils["MAIN_CONTACTOR"], False)
        self.modbus.sleep_worker(2.0)

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
            # Reset ALL transformer taps (COMMON) sequentially
            # -------------------------------------------------
            t_addrs = [addr for name, addr in coils.items() if name.startswith("T_")]
            if t_addrs:
                print(f"[PLC] Resetting ALL transformer taps sequentially")
                for tap_addr in sorted(t_addrs):
                    self.modbus.write_coil(plc_slave, tap_addr, False)
                    time.sleep(0.05) # Tiny delay to prevent bus/relay overload

            # -------------------------------------------------
            # Decide voltage to apply (first non-NC phase)
            # -------------------------------------------------
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
            cur_addrs = [addr for name, addr in coils.items() if name.startswith("CUR1_") or name.startswith("CUR2_")]
            if cur_addrs:
                print(f"[PLC] Resetting ALL current relays sequentially")
                for c_addr in sorted(cur_addrs):
                    self.modbus.write_coil(plc_slave, c_addr, False)
                    time.sleep(0.05)

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
            logger.info(f"Waiting for stabilization ({self.stabilization_time}s)")
            self._interruptible_sleep(self.stabilization_time)

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
            self.modbus.sleep_worker(2.0)

            # Calculate extra stabilization time for high voltages
            extra_delay = 0.0
            if selected_voltage:
                import re
                match = re.search(r'\d+', selected_voltage)
                if match and int(match.group()) >= 400:
                    extra_delay = 1.0
                    
            if extra_delay > 0:
                print(f"[TEST] High voltage selected (>400V), adding {extra_delay}s extra settling time")
                logger.info(f"High voltage selected (>400V), adding {extra_delay}s extra settling time")
                
            # Allow contactor + transformer to settle
            self._interruptible_sleep(self.stabilization_time + extra_delay)

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
                    measured_rn = expected_v + random.uniform(-5, 5)
                    measured_yn = expected_v + random.uniform(-5, 5)
                    measured_bn = expected_v + random.uniform(-5, 5)
                else:
                    # Batch read 3 phases (142, 144, 146)
                    vals = self.modbus.read_floats(ac["slave_id"], ac["registers"]["R_N_VOLTAGE"], count=3, endian=endian)
                    measured_rn, measured_yn, measured_bn = vals[0], vals[1], vals[2]

                print(f"[TEST] R-N Voltage = {measured_rn:.3f} V")
                print(f"[TEST] Y-N Voltage = {measured_yn:.3f} V")
                print(f"[TEST] B-N Voltage = {measured_bn:.3f} V")

                logger.info(
                    f"AC Voltages (P-N) → R-N={measured_rn:.3f}, Y-N={measured_yn:.3f}, B-N={measured_bn:.3f}"
                )

                ac_vals = {
                    "r_v": f"{measured_rn:.3f}",
                    "y_v": f"{measured_yn:.3f}",
                    "b_v": f"{measured_bn:.3f}",
                }

            else:
                print("[TEST] Neutral NC → Reading Phase-to-Phase  1")
                logger.info("Neutral NC → Reading Phase-to-Phase Voltages")

                if SIMULATION_MODE:
                    measured_ry = expected_v + random.uniform(-5, 5)
                    measured_yb = expected_v + random.uniform(-5, 5)
                    measured_br = expected_v + random.uniform(-5, 5)
                else:
                    # Batch read 3 phases (134, 136, 138)
                    vals = self.modbus.read_floats(ac["slave_id"], ac["registers"]["R_Y_VOLTAGE"], count=3, endian=endian)
                    measured_ry, measured_yb, measured_br = vals[0], vals[1], vals[2]

                print(f"[TEST] R-Y Voltage = {measured_ry:.3f} V")
                print(f"[TEST] Y-B Voltage = {measured_yb:.3f} V")
                print(f"[TEST] B-R Voltage = {measured_br:.3f} V")

                logger.info(f"AC Voltages (P-P) → R-Y={measured_ry:.3f}, Y-B={measured_yb:.3f}, B-R={measured_br:.3f}")

                ac_vals = {
                    "r_v": f"{measured_ry:.3f}",
                    "y_v": f"{measured_yb:.3f}",
                    "b_v": f"{measured_br:.3f}",
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
                    # Batch read V and I (2999, 3001)
                    vals = self.modbus.read_floats(dc_v["slave_id"], dc_v["registers"]["DC_VOLTAGE"], count=2, endian=dc_v.get("endian", "ABCD"))
                    measured_v, measured_i = vals[0], vals[1]

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
                if expected_i not in self.limit_table:
                    logger.warning(f"No limits defined for load {expected_i}A. Falling back to default.")

                limits = self.limit_table.get(expected_i, {"v_upper": 5.75, "v_lower": 5.40})
                v_upper = limits.get("v_upper", 5.75)
                v_lower = limits.get("v_lower", 5.40)

            # -----------------------------------------
            # Current limits
            # -----------------------------------------
            if expected_i == 0.0:
                i_upper = self.zero_current_limit
                i_lower = -self.zero_current_limit
            else:
                tol = expected_i * (self.current_tolerance_percent / 100)
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
                },
                conn=self.db_conn
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

        self.signals.result_signal.emit(
            tc["sn"], pcb_index, tc['v'], tc['i'], tc['v'], v_meas, i_meas, result
        )

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
                # Reset ALL impedance relays for this PCB
                imp_pcb_addrs = [addr for name, addr in coils.items() if name.startswith(f"IMP{pcb_index}_")]
                if imp_pcb_addrs:
                    start_imp = min(imp_pcb_addrs)
                    count_imp = max(imp_pcb_addrs) - start_imp + 1
                    self.modbus.write_coils(plc_slave, start_imp, [False] * count_imp)

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

            # Always reset phases first (prevent leakage path) - Batch Write
            phase_addrs = [coils[r_coil], coils[y_coil], coils[b_coil]]
            start_p = min(phase_addrs)
            # Assuming they are contiguous (they usually are based on generate_plc_coils)
            # If not contiguous, write_coils still works but we need a bigger range or just individual calls.
            # Let's check config.py: IMP1_R, Y, B, N are contiguous.
            self.modbus.write_coils(plc_slave, start_p, [False, False, False])

            time.sleep(0.02)

            # Enable selected phase
            print(f"[PCB{pcb_index}] Closing relay {coil_key}")
            self.modbus.write_coil(plc_slave, coils[coil_key], True)

            # Stabilization time for megger
            logger.info(f"Waiting for megger stabilization ({self.stabilization_time}s)")
            self._interruptible_sleep(self.stabilization_time)

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
        # Batch reset all impedance relays
        all_imp_addrs = [coils[test_en], coils[r_coil], coils[y_coil], coils[b_coil], coils[n_coil]]
        start_all = min(all_imp_addrs)
        end_all = max(all_imp_addrs)
        count_all = end_all - start_all + 1
        # To be safe, we just write False to the whole range
        self.modbus.write_coils(plc_slave, start_all, [False] * count_all)

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

        self._safe_emit(self.signals.error_signal, 
            f"Fatal error\nDevice: {device}\nSlave: {slave_name}\n{exc}"
        )

    def _safety_callback(self, reason):
        print(f"[SAFETY] STOP TRIGGERED: {reason}")
        logger.warning(f"Safety Stop Triggered: {reason}")
        self._stop_requested = True
        self._safe_emit(self.signals.safety_stop_signal, reason)

    def _safe_emit(self, signal, *args):
        try:
            signal.emit(*args)
        except Exception as e:
            logger.warning(f"Failed to emit signal: {e}")
