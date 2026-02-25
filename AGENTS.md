# Repository Guidelines

## Project Structure & Module Organization
- `lcus_usb_relay_module_controller/__init__.py`: packaged library API (`Device`) for LCUS relay boards.
- `example.py`: minimal serial control example for quick validation.
- `relay.py`: Tkinter desktop control panel with sequencing and status polling.
- `cp_power_gui_config.json`: persisted GUI settings (COM port, channel map, delays).
- `setup.py` and `README.md`: package metadata and usage docs.
- Generated outputs (`build/`, `relay.dist/`, `relay.onefile-build/`, `relay.exe`) are build artifacts; avoid manual edits there.

## Build, Test, and Development Commands
```powershell
pip install .                                         # install package from source
python example.py                                     # run serial control example
python relay.py                                       # launch GUI relay controller
pip uninstall lcus-usb-relay-module-controller        # remove installed package
python -m py_compile lcus_usb_relay_module_controller\__init__.py relay.py
```
Use `pip install .` to pull `pyserial` automatically from `install_requires`.

## Coding Style & Naming Conventions
- Target Python 3 and follow PEP 8 for new/modified code.
- Use 4-space indentation for new code, `snake_case` for functions/variables, `PascalCase` for classes, and `UPPER_CASE` for constants.
- Keep serial protocol bytes/checksum logic explicit and close to IO methods.
- Preserve backward compatibility for the public API (`Device`, `device.channel[...]` semantics).

## Testing Guidelines
- No automated test suite is currently committed.
- Validate behavior with hardware-in-loop checks on a connected LCUS board:
  - Run `python example.py` and verify channel toggling.
  - Confirm `query_relay_status()` matches physical relay state.
  - For GUI changes, verify ON/OFF/RESET flows and config save/load in `cp_power_gui_config.json`.
- If adding tests, place them under `tests/` and run with `pytest`.

## Commit & Pull Request Guidelines
- Keep commit subjects short, imperative, and scoped (examples from history: `Fix typo`, `Update README.md`).
- Prefer separate commits for source changes vs. generated binaries/package artifacts.
- PRs should include:
  - concise change summary,
  - tested board/model and COM setup,
  - evidence of verification (console output or screenshots for GUI changes),
  - linked issue/reference when applicable.
