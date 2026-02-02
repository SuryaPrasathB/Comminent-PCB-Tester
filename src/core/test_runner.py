# test_runner.py
from PySide6.QtCore import QThread, Signal
import time

from src.core.db_utils import save_test_result
from src.core.drivers.modbus_driver import ModbusRTU

from src.core.config import (
    SLAVE_DEVICES,
    VOLTAGE_TOLERANCE_PERCENT, VOLTAGE_TAPPINGS, CURRENT_TAPPINGS, CURRENT_TOLERANCE_PERCENT, STABILIZATION_TIME, MIN_IMPEDANCE_MOHM
)

from src.core.logger import logger


class TestRunner(QThread):
    result_signal = Signal(dict)
    finished_signal = Signal(str)
    error_signal = Signal(str)
    running_sn_signal = Signal(int)

    def __init__(
            self,
            project_name,
            pcb_serial,
            test_cases,
            com_port,
            start_index=0,
            run_single=False
    ):
        super().__init__()

        self.project_name = project_name
        self.pcb_serial = pcb_serial
        self.test_cases = test_cases
        self.start_index = start_index
        self.run_single = run_single
        self.com_port = com_port

        self._stop_requested = False
        self._fatal_error = False
        self.modbus = None

        print("[TEST] ====================================")
        print("[TEST] TestRunner initialized")
        print(f"[TEST] Project    : {project_name}")
        print(f"[TEST] PCB Serial : {pcb_serial}")
        print(f"[TEST] COM Port   : {com_port}")
        print(f"[TEST] Run Single: {run_single}")

        logger.info("TestRunner initialized")
        logger.info(f"Project={project_name}, PCB={pcb_serial}, COM={com_port}, RunSingle={run_single}")

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
            if self.modbus:
                print("[TEST] Closing Modbus connection")
                logger.info("Closing Modbus connection")
                try:
                    self.modbus.close()
                except Exception:
                    pass

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
        if "Impedance" in tc["desc"]: #change it to dynamic one
            self._sep()
            try:
                print("[TEST] Mode: Impedance test")
                logger.info("Mode: Impedance test")

                # --- PLC Functions ---

                present_slave_name = plc.get("display_name")
                error_msg = "PLC Communication" # If error happens

                # R phase (OFF all)
                for tap in VOLTAGE_TAPPINGS:
                    tap != "NC" and self.modbus.write_coil(plc_slave, coils[f"R_{tap.replace('V', '')}"], False)

                # Y phase (OFF all)
                for tap in VOLTAGE_TAPPINGS:
                    tap != "NC" and self.modbus.write_coil(plc_slave, coils[f"Y_{tap.replace('V', '')}"], False)

                # B phase (OFF all)
                for tap in VOLTAGE_TAPPINGS:
                    tap != "NC" and self.modbus.write_coil(plc_slave, coils[f"B_{tap.replace('V', '')}"], False)

                # ---- Neutral OFF - Neutral (NC = OFF, C = ON) ----
                self.modbus.write_coil(plc_slave, coils["NEUTRAL"], False)

                # OFF all current relays
                for cur in CURRENT_TAPPINGS:
                    cur != "0A" and self.modbus.write_coil(plc_slave, coils[f"CUR_{cur.replace('A', '').replace('.', '_')}"],False)

                # --- Impedence meter functions

                imp = SLAVE_DEVICES["IMP_METER"]
                slave = imp["slave_id"]
                impedance_results = {}  # 🔹 store values in MΩ

                present_slave_name = imp.get("display_name")
                error_msg = "Impedance Measurement" # If error happens

                # ---- Neutral ON - Neutral (NC = OFF, C = ON) ----
                self.modbus.write_coil(plc_slave, coils["IMP1_N"], True)

                for phase, coil_key, reg_key in [
                    ("R", "IMP1_R", "R_N_IMP"),
                    ("Y", "IMP1_Y", "Y_N_IMP"),
                    ("B", "IMP1_B", "B_N_IMP"),
                ]:
                    print(f"[TEST] Switching {phase}-N")
                    logger.info(f"Switching {phase}-N")

                    self.modbus.write_coil(plc_slave, coils["IMP1_R"], False)
                    self.modbus.write_coil(plc_slave, coils["IMP1_Y"], False)
                    self.modbus.write_coil(plc_slave, coils["IMP1_B"], False)

                    self.modbus.write_coil(plc_slave, coils[coil_key], True)
                    time.sleep(STABILIZATION_TIME) #(0.2)

                    #endian = imp.get("endian", "ABCD")
                    endian = imp.get("endian", "ABCD")

                    value = self.modbus.read_float(
                        slave,
                        imp["registers"][reg_key],
                        endian=endian
                    )

                    # ---- Impedance Meter Phase Relays----
                    self.modbus.write_coil(plc_slave, coils["IMP1_R"], False)
                    self.modbus.write_coil(plc_slave, coils["IMP1_Y"], False)
                    self.modbus.write_coil(plc_slave, coils["IMP1_B"], False)

                    # ---- Impedance Meter Neutral Relay----
                    self.modbus.write_coil(plc_slave, coils["IMP1_N"], False)

                    impedance_results[phase] = value

                    print(f"[TEST] {phase}-N = {value:.3f} Ω")
                    logger.info(f"{phase}-N impedance = {value:.3f} Ω")

                # -------------------------------
                # Validation (> minimum MΩ)
                # -------------------------------

                all_pass = True
                for value in impedance_results.values():
                    if value <= MIN_IMPEDANCE_MOHM:
                        all_pass = False

                result_text = (
                    f"Zrn={impedance_results['R']:.3f}MΩ, "
                    f"Zyn={impedance_results['Y']:.3f}MΩ, "
                    f"Zbn={impedance_results['B']:.3f}MΩ"
                )

                if all_pass:
                    self._task_ok("Impedance Measurement")
                    final_result = f"PASS ({result_text})"
                else:
                    self._task_fail("Impedance Measurement", "Impedance below minimum")
                    final_result = f"FAIL ({result_text})"

                ac_vals = {
                    "r_v": f"NA",
                    "y_v": f"NA",
                    "b_v": f"NA"
                }
                self._finalize(tc, None, None, final_result, ac_vals)  # def _finalize(self, tc, v, i, result, ac_vals=None):
                return

            except Exception as e:
                self._task_fail(error_msg,  present_slave_name)
                self._fatal_comm_error("IMP_METER", present_slave_name, e)
                return

        # =================================================
        # 2️⃣ APPLY RELAYS
        # =================================================
        self._sep()
        try:
            print("[TEST] Setting Voltage and Current Relays")
            logger.info("Setting Voltage and Current Relays")

            present_slave_name = plc.get("display_name")

            # ---- Neutral (NC = OFF, C = ON) ----
            self.modbus.write_coil(plc_slave, coils["NEUTRAL"], tc["n"] == "C")

            # =================================================
            # VOLTAGE TAPS
            # =================================================

            # R phase (OFF all)
            for tap in VOLTAGE_TAPPINGS:
                tap != "NC" and self.modbus.write_coil(plc_slave, coils[f"R_{tap.replace('V', '')}"], False)
            # R phase (ON selected)
            tc["r"] != "NC" and self.modbus.write_coil(plc_slave, coils[f"R_{tc['r'].replace('V', '')}"], True)

            # Y phase (OFF all)
            for tap in VOLTAGE_TAPPINGS:
                tap != "NC" and self.modbus.write_coil(plc_slave, coils[f"Y_{tap.replace('V', '')}"], False)
            # Y phase (ON selected)
            tc["y"] != "NC" and self.modbus.write_coil(plc_slave, coils[f"Y_{tc['y'].replace('V', '')}"], True)

            # B phase (OFF all)
            for tap in VOLTAGE_TAPPINGS:
                tap != "NC" and self.modbus.write_coil(plc_slave, coils[f"B_{tap.replace('V', '')}"], False)
            # B phase (ON selected)
            tc["b"] != "NC" and self.modbus.write_coil(plc_slave, coils[f"B_{tc['b'].replace('V', '')}"], True)

            # =================================================
            # CURRENT TAPS
            # =================================================

            # OFF all current relays
            for cur in CURRENT_TAPPINGS:
                cur != "0A" and self.modbus.write_coil(plc_slave,coils[f"CUR_{cur.replace('A', '').replace('.', '_')}"], False)


            # ON selected current relay
            tc["i"] != "0A" and self.modbus.write_coil(plc_slave,coils[f"CUR_{tc['i'].replace('A', '').replace('.', '_')}"], True)


            print("[TEST] Waiting for stabilization (cool-down)")
            logger.info("Waiting for stabilization")
            time.sleep(STABILIZATION_TIME)

            self._task_ok("Setting Voltage and Current Relays")

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
            present_slave_name =  ac.get("display_name")

            r_v = self.modbus.read_float(ac["slave_id"], ac["registers"]["R_VOLTAGE"], endian=endian)
            y_v = self.modbus.read_float(ac["slave_id"], ac["registers"]["Y_VOLTAGE"], endian=endian)
            b_v = self.modbus.read_float(ac["slave_id"], ac["registers"]["B_VOLTAGE"], endian=endian)

            print(f"[TEST] R Phase Voltage = {r_v:.3f} V")
            print(f"[TEST] Y Phase Voltage = {y_v:.3f} V")
            print(f"[TEST] B Phase Voltage = {b_v:.3f} V")

            logger.info(f"AC Voltages → R={r_v:.3f}, Y={y_v:.3f}, B={b_v:.3f}")

            ac_vals = {
                "r_v": f"{r_v:.3f}",
                "y_v": f"{y_v:.3f}",
                "b_v": f"{b_v:.3f}"
            }

            self._task_ok("Reading AC Voltages")

        except Exception as e:
            self._task_fail("Reading AC Voltages", present_slave_name)
            self._fatal_comm_error("AC_METER", present_slave_name, e)
            return

        # =================================================
        # 4️⃣ READ DC METERS
        # =================================================
        self._sep()
        try:
            print("[TEST] Reading DC Voltage and Current")
            logger.info("Reading DC Voltage and Current")

            dc_v = SLAVE_DEVICES["DC_V_METER"]
            dc_v_endian = dc_v.get("endian", "ABCD")
            present_slave_name =  dc_v.get("display_name")
            measured_v = self.modbus.read_float(dc_v["slave_id"], dc_v["registers"]["DC_VOLTAGE"], endian=dc_v_endian)

            dc_i = SLAVE_DEVICES["DC_I_METER"]
            dc_i_endian = dc_i.get("endian", "ABCD")
            present_slave_name =  dc_i.get("display_name")
            measured_i = self.modbus.read_float(dc_i["slave_id"], dc_i["registers"]["DC_CURRENT"], endian=dc_i_endian)

            print(f"[TEST] DC → V={measured_v:.3f}  I={measured_i:.3f}")
            logger.info(f"DC Measurements → V={measured_v:.3f}, I={measured_i:.3f}")

            self._task_ok("Reading DC Voltage and Current")

        except Exception as e:
            self._task_fail("Reading DC Voltage and Current", "DC_METER")
            self._fatal_comm_error("DC_METER", present_slave_name, e)
            return

        # =================================================
        # 5️⃣ VALIDATION
        # =================================================
        try:
            v_str = str(tc["v"].replace("V", "")).strip()  # ensure string + remove spaces
            expected_v = float(v_str)

            i_str = str(tc["i"].replace("A", "")).strip()  # ensure string + remove spaces
            expected_i = float(i_str)

            print(f"[TEST] expected_v: {expected_v}")
            print(f"[TEST] expected_i: {expected_i}")

            voltage_error = ((expected_v - measured_v) / expected_v) * 100
            current_error = ((expected_i - measured_i) / expected_i) * 100

            print(f"[TEST] voltage_error: {voltage_error}")
            print(f"[TEST] current_error: {current_error}")

            result = "Pass" if ((abs(voltage_error) <= VOLTAGE_TOLERANCE_PERCENT) and (
                        abs(current_error) <= CURRENT_TOLERANCE_PERCENT)) else "Fail"

        except Exception as e:
            print(f"[TEST] Exception occurred: {e}")
            logger.error(f"Validation exception: {e}")
            result = "Fail"

        print(f"[TEST] Result = {result}")
        logger.info(f"Test Result = {result}")
        self._finalize(tc, measured_v, measured_i, result, ac_vals)

    # -------------------------------------------------
    def _finalize(self, tc, v, i, result, ac_vals=None):
        v_meas = f"{v:.3f}" if v is not None else "NA"
        i_meas = f"{i:.3f}" if i is not None else "NA"

        #v_exp = f"{tc['v']}" if tc.get("v") is not None else "NA"
        #i_exp = f"{tc['i']}" if tc.get("i") is not None else "NA"

        if not self.run_single:
            print("[TEST] Saving result to database")
            logger.info("Saving test result to database")

            save_test_result(
                self.project_name,
                self.pcb_serial,
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
