import argparse
import json
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from queue import Queue, Empty
from typing import Dict, Optional, Tuple

import serial
import serial.tools.list_ports

import tkinter as tk
from tkinter import ttk, messagebox


CONFIG_DIR = Path.home() / ".cp_relay_ui"
CONFIG_PATH = CONFIG_DIR / "cp_power_gui_config.json"


@dataclass
class AppConfig:
    relay_control_port: str = "COM5"
    baudrate: int = 9600

    # Map physical relay channels (1-based, per LCUS manuals) to functions
    power_relay_channel: int = 1
    usb_relay_channel: int = 2

    # If wired via NC instead of NO, logical meaning may invert
    invert_power: bool = False
    invert_usb: bool = False

    # Sequencing
    power_to_usb_delay_s: float = 1.0
    inter_command_delay_s: float = 0.05  # 50ms is commonly recommended


def ensure_config_file_exists() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        default_cfg = AppConfig()
        CONFIG_PATH.write_text(json.dumps(asdict(default_cfg), indent=2), encoding="utf-8")


class LcusRelayBoard:
    """
    Minimal LCUS USB-serial relay controller.

    Protocol (commonly documented):
      - Set relay: [0xA0, channel, op, checksum] where checksum = sum of first 3 bytes (mod 256)
      - Query: 0xFF
    """
    def __init__(self, port_name: str, baudrate: int = 9600, timeout_s: float = 1.0):
        self.port_name = port_name
        self.baudrate = baudrate
        self.timeout_s = timeout_s
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()  # serialize writes/reads on the port

    @property
    def is_open(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    def open(self) -> None:
        if self.is_open:
            return
        self._ser = serial.Serial(
            port=self.port_name,
            baudrate=self.baudrate,
            bytesize=8,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout_s,
            write_timeout=self.timeout_s,
        )

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            try:
                self._ser.flush()
            finally:
                self._ser.close()

    def _write(self, payload: bytes) -> None:
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Relay control serial port is not open.")
        self._ser.write(payload)

    def set_relay(self, channel_1_based: int, on: bool) -> None:
        """
        Energize (on=True) or de-energize (on=False) the relay.
        """
        channel = channel_1_based & 0xFF
        op = 0x01 if on else 0x00
        start = 0xA0
        checksum = (start + channel + op) & 0xFF
        frame = bytes([start, channel, op, checksum])

        with self._lock:
            self._ser.reset_input_buffer()
            self._write(frame)

    def query_status(self, relay_count: int = 2) -> Dict[int, bool]:
        """
        Returns {channel_1_based: is_on}.

        Tolerant parsing:
          - If response contains ASCII 'CH', parse lines like 'CH1:ON'
          - Else interpret first N bytes as 0/1 for each channel
        """
        with self._lock:
            self._ser.reset_input_buffer()
            self._write(b"\xFF")
            # Let device respond; then read whatever is available up to timeout.
            time.sleep(0.02)
            data = self._ser.read(256)

        status: Dict[int, bool] = {}

        if not data:
            return status

        # Heuristic: ASCII response
        if b"CH" in data:
            try:
                text = data.decode("ascii", errors="ignore")
                for line in text.splitlines():
                    line = line.strip()
                    # Examples described in manuals: "CH1:ON", "CH2:OFF"
                    if line.upper().startswith("CH") and ":" in line:
                        left, right = line.split(":", 1)
                        ch_str = left.upper().replace("CH", "").strip()
                        if ch_str.isdigit():
                            ch = int(ch_str)
                            status[ch] = right.strip().upper().startswith("ON")
            except Exception:
                pass
        else:
            # Binary response: first N bytes are channel states 0/1.
            for i in range(min(relay_count, len(data))):
                status[i + 1] = (data[i] == 0x01)

        return status


class ControlPanelSequencer:
    def __init__(self, board: LcusRelayBoard, cfg: AppConfig):
        self.board = board
        self.cfg = cfg
        self._seq_lock = threading.Lock()

    def _logical_to_physical(self, logical_on: bool, invert: bool) -> bool:
        # If invert=True, relay "ON" means logical "OFF" (NC wiring, etc.)
        return logical_on ^ invert

    def set_power(self, on: bool) -> None:
        self.board.set_relay(
            self.cfg.power_relay_channel,
            self._logical_to_physical(on, self.cfg.invert_power),
        )

    def set_usb(self, on: bool) -> None:
        self.board.set_relay(
            self.cfg.usb_relay_channel,
            self._logical_to_physical(on, self.cfg.invert_usb),
        )

    def sequence_on(self) -> None:
        with self._seq_lock:
            self.set_usb(False)
            time.sleep(self.cfg.inter_command_delay_s)
            self.set_power(True)
            time.sleep(self.cfg.power_to_usb_delay_s)
            self.set_usb(True)

    def sequence_off(self) -> None:
        with self._seq_lock:
            self.set_power(False)
            time.sleep(self.cfg.inter_command_delay_s)
            self.set_usb(False)

    def sequence_reset(self) -> None:
        with self._seq_lock:
            self.set_power(False)
            time.sleep(self.cfg.inter_command_delay_s)
            self.set_usb(False)
            time.sleep(self.cfg.inter_command_delay_s)
            self.set_power(True)
            time.sleep(self.cfg.power_to_usb_delay_s)
            self.set_usb(True)

    def read_logical_status(self) -> Tuple[Optional[bool], Optional[bool]]:
        """
        Returns (power_on, usb_on) as logical states, if readable.
        """
        raw = self.board.query_status(relay_count=2)
        if not raw:
            return (None, None)

        def phys_to_logical(phys: bool, inv: bool) -> bool:
            return phys ^ inv

        power_phys = raw.get(self.cfg.power_relay_channel)
        usb_phys = raw.get(self.cfg.usb_relay_channel)

        power_log = None if power_phys is None else phys_to_logical(power_phys, self.cfg.invert_power)
        usb_log = None if usb_phys is None else phys_to_logical(usb_phys, self.cfg.invert_usb)
        return (power_log, usb_log)


def load_config() -> AppConfig:
    ensure_config_file_exists()
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return AppConfig(**data)
        except Exception:
            pass
    default_cfg = AppConfig()
    save_config(default_cfg)
    return default_cfg


def save_config(cfg: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CP Power Sequencer (LCUS-2)")
        icon = tk.PhotoImage(file="reviews_4142441.png")  # PNG
        self.iconphoto(True, icon)            # True => apply to all future toplevels too

        self.cfg = load_config()
        self.board = LcusRelayBoard(self.cfg.relay_control_port, self.cfg.baudrate, timeout_s=1.0)
        self.seq = ControlPanelSequencer(self.board, self.cfg)

        self.worker_q: Queue = Queue()
        self.last_error: Optional[str] = None

        self._build_ui()
        self._connect_board()

        # periodic status refresh
        self.after(500, self._tick_status)
        self.after(100, self._tick_worker_queue)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        main = ttk.Frame(self, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        btns = ttk.Frame(main)
        btns.grid(row=0, column=0, sticky="ew")
        btns.columnconfigure(0, weight=1)

        self.btn_on = ttk.Button(btns, text="ON", command=lambda: self._run_sequence("on"))
        self.btn_off = ttk.Button(btns, text="OFF", command=lambda: self._run_sequence("off"))
        self.btn_reset = ttk.Button(btns, text="RESET", command=lambda: self._run_sequence("reset"))
        self.btn_cfg = ttk.Button(btns, text="Config…", command=self._open_config_dialog)
        self.btn_help = ttk.Button(btns, text="Help", command=self._show_help)

        self.btn_on.grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        self.btn_off.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        self.btn_reset.grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        self.btn_cfg.grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        self.btn_help.grid(row=0, column=4, padx=4, pady=4, sticky="ew")

        status = ttk.LabelFrame(main, text="Status", padding=10)
        status.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.var_port = tk.StringVar()
        self.var_port_open = tk.StringVar()
        self.var_power = tk.StringVar()
        self.var_usb = tk.StringVar()
        self.var_error = tk.StringVar()

        ttk.Label(status, text="Relay control port:").grid(row=0, column=0, sticky="w")
        ttk.Label(status, textvariable=self.var_port).grid(row=0, column=1, sticky="w")

        ttk.Label(status, text="Port state:").grid(row=1, column=0, sticky="w")
        ttk.Label(status, textvariable=self.var_port_open).grid(row=1, column=1, sticky="w")

        ttk.Label(status, text="Power:").grid(row=2, column=0, sticky="w")
        ttk.Label(status, textvariable=self.var_power).grid(row=2, column=1, sticky="w")

        ttk.Label(status, text="USB-Serial:").grid(row=3, column=0, sticky="w")
        ttk.Label(status, textvariable=self.var_usb).grid(row=3, column=1, sticky="w")

        ttk.Label(status, text="Last error:").grid(row=4, column=0, sticky="w")
        ttk.Label(status, textvariable=self.var_error).grid(row=4, column=1, sticky="w")

    def _connect_board(self):
        self.var_port.set(self.cfg.relay_control_port)
        try:
            self.board.open()
            self.last_error = None
        except Exception as e:
            self.last_error = repr(e)

    def _set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for b in (self.btn_on, self.btn_off, self.btn_reset, self.btn_cfg, self.btn_help):
            b.config(state=state)

    def _run_sequence(self, which: str):
        def worker():
            try:
                if not self.board.is_open:
                    self.board.open()

                if which == "on":
                    self.seq.sequence_on()
                elif which == "off":
                    self.seq.sequence_off()
                elif which == "reset":
                    self.seq.sequence_reset()
                else:
                    raise ValueError(f"Unknown sequence {which!r}")

                self.worker_q.put(("ok", which))
            except Exception as e:
                self.worker_q.put(("err", repr(e)))

        self._set_buttons_enabled(False)
        threading.Thread(target=worker, daemon=True).start()

    def _tick_worker_queue(self):
        try:
            msg = self.worker_q.get_nowait()
            kind = msg[0]
            if kind == "err":
                self.last_error = msg[1]
            else:
                self.last_error = None
        except Empty:
            pass
        finally:
            self._set_buttons_enabled(True)
            self.after(100, self._tick_worker_queue)

    def _tick_status(self):
        self.var_port_open.set("OPEN" if self.board.is_open else "CLOSED")
        if self.last_error:
            self.var_error.set(self.last_error)
        else:
            self.var_error.set("-")

        power, usb = (None, None)
        if self.board.is_open:
            try:
                power, usb = self.seq.read_logical_status()
            except Exception as e:
                self.last_error = repr(e)

        self.var_power.set("UNKNOWN" if power is None else ("ON" if power else "OFF"))
        self.var_usb.set("UNKNOWN" if usb is None else ("ON" if usb else "OFF"))

        self.after(700, self._tick_status)

    def _open_config_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Configuration")
        dlg.transient(self)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        ports = [p.device for p in serial.tools.list_ports.comports()]
        port_var = tk.StringVar(value=self.cfg.relay_control_port)

        pwr_var = tk.IntVar(value=self.cfg.power_relay_channel)
        usb_var = tk.IntVar(value=self.cfg.usb_relay_channel)

        inv_pwr = tk.BooleanVar(value=self.cfg.invert_power)
        inv_usb = tk.BooleanVar(value=self.cfg.invert_usb)

        delay_var = tk.DoubleVar(value=self.cfg.power_to_usb_delay_s)

        ttk.Label(frame, text="Relay control COM port:").grid(row=0, column=0, sticky="w")
        port_box = ttk.Combobox(frame, textvariable=port_var, values=ports, width=18)
        port_box.grid(row=0, column=1, sticky="w")

        ttk.Label(frame, text="Power relay channel (1..8):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(frame, from_=1, to=8, textvariable=pwr_var, width=5).grid(row=1, column=1, sticky="w", pady=(8, 0))

        ttk.Label(frame, text="USB relay channel (1..8):").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(frame, from_=1, to=8, textvariable=usb_var, width=5).grid(row=2, column=1, sticky="w")

        ttk.Checkbutton(frame, text="Invert Power logic (NC wiring)", variable=inv_pwr).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(frame, text="Invert USB logic (NC wiring)", variable=inv_usb).grid(row=4, column=0, columnspan=2, sticky="w")

        ttk.Label(frame, text="Delay Power→USB (seconds):").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(frame, from_=0.0, to=10.0, increment=0.1, textvariable=delay_var, width=7).grid(row=5, column=1, sticky="w", pady=(8, 0))

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))

        def on_save():
            try:
                new_cfg = AppConfig(
                    relay_control_port=port_var.get().strip() or self.cfg.relay_control_port,
                    baudrate=self.cfg.baudrate,
                    power_relay_channel=int(pwr_var.get()),
                    usb_relay_channel=int(usb_var.get()),
                    invert_power=bool(inv_pwr.get()),
                    invert_usb=bool(inv_usb.get()),
                    power_to_usb_delay_s=float(delay_var.get()),
                    inter_command_delay_s=self.cfg.inter_command_delay_s,
                )
                save_config(new_cfg)
                self.cfg = new_cfg

                # Rebuild controller objects
                try:
                    self.board.close()
                except Exception:
                    pass

                self.board = LcusRelayBoard(self.cfg.relay_control_port, self.cfg.baudrate, timeout_s=1.0)
                self.seq = ControlPanelSequencer(self.board, self.cfg)
                self._connect_board()

                dlg.destroy()
            except Exception as e:
                messagebox.showerror("Config error", repr(e), parent=dlg)

        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).grid(row=0, column=0, padx=6)
        ttk.Button(btn_row, text="Save", command=on_save).grid(row=0, column=1)

    def _show_help(self):
        message = (
            "CP Power Sequencer Help\n\n"
            "GUI actions:\n"
            "- ON: Power on, then enable USB after configured delay.\n"
            "- OFF: Disable power and USB.\n"
            "- RESET: Power cycle, then re-enable USB.\n\n"
            "Configuration:\n"
            f"- Config file: {CONFIG_PATH}\n"
            "- Use 'Config…' to set COM port, channel mapping, and delays.\n\n"
            "Command-line mode:\n"
            "- python relay.py --action ON\n"
            "- python relay.py --action OFF\n"
            "- python relay.py --action RESET"
        )
        messagebox.showinfo("Help", message, parent=self)

    def _on_close(self):
        try:
            self.board.close()
        except Exception:
            pass
        self.destroy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CP Relay Controller", add_help=True)
    parser.add_argument(
        "-a",
        "--action",
        type=str.upper,
        choices=("ON", "OFF", "RESET"),
        help="Run headless action (no GUI), then exit.",
    )
    return parser.parse_args()


def run_headless_action(action: str) -> int:
    cfg = load_config()
    board = LcusRelayBoard(cfg.relay_control_port, cfg.baudrate, timeout_s=1.0)
    seq = ControlPanelSequencer(board, cfg)

    try:
        board.open()
        if action == "ON":
            seq.sequence_on()
        elif action == "OFF":
            seq.sequence_off()
        elif action == "RESET":
            seq.sequence_reset()
        else:
            raise ValueError(f"Unknown action {action!r}")
        print(f"Action {action} completed on {cfg.relay_control_port}.")
        return 0
    except Exception as e:
        print(f"Failed to run action {action}: {e!r}", file=sys.stderr)
        return 1
    finally:
        try:
            board.close()
        except Exception:
            pass


def main() -> int:
    args = parse_args()
    if args.action:
        return run_headless_action(args.action)
    # if args.help:
    #     args.print_help()
    #     return 0

    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
