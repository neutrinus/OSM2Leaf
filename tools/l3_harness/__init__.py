"""L3 harness skeleton: corpus manifest, WinCE stubs, ROM memory map, runner.

This package makes the L3 plan in ``docs/research/l3-ghidra.md`` executable
without vendor data and without Ghidra:

* :mod:`manifest` builds and validates the corpus manifest;
* :mod:`stubs` is the declarative WinCE API stub table;
* :mod:`rommap` turns a ``ce_rom_parse.py`` JSON report into a Ghidra loader
  memory map;
* :mod:`runner` checks the inputs, prints the trace plan, and refuses to run
  (exit ``3``/``4``) when Ghidra or a located reader is missing.

``python3 tools/l3_harness/selftest.py`` exercises all four modules on
synthetic data and never touches the network or the vendor image.
"""

__version__ = "0.1.0"

__all__ = ["manifest", "stubs", "rommap", "runner", "selftest"]
