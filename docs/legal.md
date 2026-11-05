# Data handling and licensing

## Code

All code in this repository is licensed under the **GNU General Public
License, version 3 or later** (GPL-3.0-or-later). See [`../LICENSE`](../LICENSE).

## OpenStreetMap-derived data

Any data generated from OpenStreetMap is distributed under the **Open Data
Commons Open Database License 1.0 (ODbL-1.0)**.

- Attribution: "© OpenStreetMap contributors".
- Share-alike applies to derived databases.
- See <https://www.openstreetmap.org/copyright> and
  <https://opendatacommons.org/licenses/odbl/1-0/>.

Do not mix OSM-derived data with vendor data in a way that would suggest the
vendor data is ODbL-licensed, or vice versa.

## Vendor data (Nissan / Clarion / Hitachi)

Original map images, SD card dumps, extracted filesystems, firmware, `.DAT`,
`.cmp`, `.ind`, voice packs, icons and any other proprietary content are
**not part of this repository** and are **not redistributed**.

They are kept in:

- `archive/` — git-ignored, local only; or
- a working directory outside the repository
  (for this project: `/home/marek/projekty/leafre-work/`).

What may be committed:

- scripts and tools,
- documentation of the format,
- SHA-256 hashes and byte offsets,
- tiny synthetic fixtures that do not reproduce vendor content,
- short hexdumps strictly necessary to document a field.

What must not be committed:

- whole images or archives,
- extracted map databases,
- firmware or DLLs,
- voice/icon assets,
- any file whose primary value is the vendor's data.

## Reverse engineering

The reverse engineering is performed for **interoperability and research**:
reading a map format in order to build a compatible replacement. It is not
intended to circumvent a technological protection measure, to redistribute
the vendor's data, or to enable piracy of map updates.

Laws differ by jurisdiction. Before distributing anything derived from
vendor data, or anything that modifies a vehicle system, review the applicable
rules. This document is not legal advice.

## Trademarks

Nissan, Leaf, Clarion, Hitachi and other names are trademarks of their
respective owners. This project is not affiliated with or endorsed by them.

## Safety and warranty

The software and documentation are provided "as is", without warranty of any
kind. Modifying a map SD card can render the navigation unit unusable.
Always keep a verified backup of the original card and test on a spare card.
