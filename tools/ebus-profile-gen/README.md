# ebus-profile-gen

Dev-only generator that reads ebusd-configuration TypeSpec (.tsp) files (including includes/templates) and emits raw JSON output into `tools/ebus-profile-gen/generated/` (gitignored). The user then saves/curates profiles and commands where they want via `--out-profiles` and `--out-commands`.

## Purpose

Read ebusd-configuration `.tsp` files for a device, parse registers/fields, group into canonical profiles (to deduplicate), and emit JSON shaped to our firmware constraints.

## Constraints

- **No trailing underscores** in any emitted JSON field names
- **Heap-free shape**: values must fit FixedString/StaticVector assumptions (ProfileFS<24> etc.). Avoid emitting runtime strings we don't need
- **write id semantics**: commands that are writable must carry the write-side keys (`wpbsb`/`wdx`) per our decision (derive from tsp write semantics); NN is derived at runtime
- **Deterministic**: sort keys, stable formatting to keep diffs readable
- **Dev-only**: never linked into PlatformIO build, no runtime dependency in firmware

## Layout

```
tools/ebus-profile-gen/
├── README.md                    # this file
├── __init__.py
├── generate.py                  # generator entry point
├── resolver.py                  # include/template resolution
├── tsp_parser.py                # minimal TypeSpec subset parser
├── model.py                     # internal IR (FieldIR/ProfileIR/CommandIR/FamilyIR)
├── mapper.py                    # tsp → our schema + profile grouping
├── emitter.py                   # write raw generated JSON
├── validate.py                  # enforce constraints
├── requirements.txt             # dev deps (stdlib by default)
├── ebusd-configuration/         # ebusd-configuration repo (checkout or symlink — gitignored)
├── ebus-typespec/               # ebus-typespec library (checkout or symlink — gitignored)
    └── generated/                   # raw generator output (gitignored)
        ├── <tsp_stem>.profiles.json # flat data profile entries (data_profiles.json schema)
        └── <tsp_stem>.json          # command entries (config/simulation.json schema)
```

### Input Repositories

#### ebusd-configuration (input)

This directory holds the ebusd-configuration repository (TypeSpec `.tsp` files). It is **gitignored** — you check it out or link it yourself:

```bash
# Option 1: check out directly
git clone https://github.com/john30/ebusd-configuration.git tools/ebus-profile-gen/ebusd-configuration

# Option 2: link to an existing checkout
ln -s /path/to/ebusd-configuration tools/ebus-profile-gen/ebusd-configuration
```

The CLI reads `.tsp` files from here via `--ebusd-root` (defaults to `tools/ebus-profile-gen/ebusd-configuration`).

#### ebus-typespec (input)

This directory holds the ebus-typespec TypeSpec library that provides the type definitions, decorators, and templates used by ebusd-configuration. It is **gitignored** — you check it out or link it yourself:

```bash
# Option 1: check out directly
git clone https://github.com/john30/ebus-typespec tools/ebus-profile-gen/ebus-typespec

# Option 2: link to an existing checkout
ln -s /path/to/ebus-typespec tools/ebus-profile-gen/ebus-typespec
```

The parser uses type definitions from this library (e.g., `Ebus.Num.UCH`, `Ebus.Num.D2C`, `Ebus.Str.IGN`, etc.) to properly resolve field types in the `.tsp` files.

### Output: `generated/` (raw, gitignored)

By default the CLI writes raw generated output to `tools/ebus-profile-gen/generated/`, using the tsp basename (e.g. `08.ehp.tsp` → `08.ehp.profiles.json` / `08.ehp.json`):

- `<tsp_stem>.profiles.json` — flat entries `{name, datatype, unit, divider, digits, min, max}` matching the `profiles/data_profiles.json` schema. These can be copied to `profiles/data_profiles_user.json` (the overlay) at compile time.
- `<tsp_stem>.json` — command entries matching `config/simulation.json` schema:
  `{key, name, zz, pbsb, [dx], [nn], wpbsb, [wdx], interval, master, fields: [{name, profile, position, ha_profile, [bits], [const]}]}`.
  `wpbsb`/`wdx` are omitted for read-only commands, `interval` defaults to 0 (passive only), `master` defaults to false, `ha_profile` is empty — fill these in by hand (exception: fields carrying a `bits` map get `ha_profile: "binary_sensor"` automatically — one HA binary_sensor per bit).
  `bits` appears on byte-grouped bitfield fields (consecutive `BI0`–`BI7` children collapsed into one `UINT8` byte) as a map of sub-field name to bit index within that byte.
  `zz` is the destination byte. An explicit `@zz` on the command or an
  inherited model takes precedence; otherwise it comes from `--zz`, a leading
  two-digit hex address in the tsp filename (e.g. `52.` → `52`), a numeric
  commented `// @zz(0x...)` in the entry file, or the fallback `08`. Upstream
  ebusd configuration uses the filename address as the default and its CSV
  emitter leaves that address out of each row; the generator mirrors this
  defaulting behavior. The read id splits into `pbsb` (`PB SB`, always
  present, `""` for write-only) and `dx` (the `Dx...` tail, 0–4 bytes), the
  write id into `wpbsb`/`wdx` with the same layout (concatenated ids are 2–6
  bytes). The tail is the resolved `@base`/`@inherit` D bytes plus the model's
  own `@ext` bytes (no default `0x0d` is invented); read NN is derived as
  `len(dx)` (= `len(id)-2`) unless an explicit `nn` override is given (the
  runtime write NN also counts the appended value bytes). Write-only commands
  carry an empty `pbsb` (`""`) and the addressing in `wpbsb`/`wdx` alone.
  `key` is prefixed (default: the full lowercased tsp stem, e.g.
      `08.ehp.tsp` → `08.ehp_`), with a sequential id appended (e.g.
      `08.ehp_001`). The full stem is preserved — `52.mc2.mc.4.tsp` →
      `52.mc2.mc.4_050` — so keys stay unique per (slave, file, id) even when
      different units carry registers of the same name (see
      `config/README.md`). Use `--key-prefix` to override the default prefix.
  `const` is a fixed wire-byte hex value from `@constValue`; the firmware
  auto-pads it on writes and rejects client-supplied values for that field.

`@inherit` resolves both addressing and payload fields. Parent fields are
combined in decorator order, followed by fields declared on the child.
Same-name fields override in place (child metadata wins), allowing generic
parent fields to be specialized without duplicating a wire field. Inherited
fillers and constants therefore retain their byte positions and write bytes.
Ambiguous parent names fail closed unless namespace and file context resolve
to exactly one parent; no command is emitted from a partially resolved
inheritance chain.

This directory is **gitignored** — raw output never gets committed by accident.

### Saving profiles and commands (manual, on purpose)

Profiles are **not** auto-merged into `profiles/`. You add them on purpose by hand:

```bash
# Generate raw output to generated/
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp

# Output: generated/08.ehp.profiles.json and generated/08.ehp.json

# Then copy profiles you want to keep into the overlay (manual step)
cp tools/ebus-profile-gen/generated/08.ehp.profiles.json profiles/data_profiles_user.json

# Commands: save wherever you want, upload to adapter later
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp \
  --out-commands config/private/vaillant-08-ehp-commands.json

# Custom key prefix
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp \
  --key-prefix vaillant_ \
  --out-commands config/private/vaillant-08-ehp-commands.json
```

At compile time, `scripts/generate_data_profiles.py` merges `profiles/data_profiles.json` + `profiles/data_profiles_user.json` into `include/app/data_profile_gen.hpp`.

## Usage

```bash
# From explicit tsp path (relative to ebusd-root)
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp

# Save outputs to custom locations
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp \
  --out-profiles my-profiles.json \
  --out-commands my-commands.json

# Custom key prefix
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp \
  --key-prefix vaillant_ \
  --out-commands my-commands.json

# Override the destination address (a hexadecimal byte)
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp \
  --zz 52
```

## Conversion scope

The generator implements a subset of the ebusd TypeSpec model and emits
firmware-schema JSON; it does not compile arbitrary TypeSpec or guarantee a
faithful conversion of every source command. It resolves template and
`@inherit` addressing and payload fields, expands composite fields, maps
supported datatypes and field metadata, and emits bit maps and `@constValue`
wire bytes.

Important boundaries:

- Validation rejects unsupported/defaulted datatype mappings, unresolved
  profiles, ID/WID values outside the firmware's 2–6-byte range, duplicate
  address IDs, and commands exceeding the 13-field firmware limit.
- `@in`/`@out` decorators are applied to field inclusion for read/write
  commands. `@in` fields belong to read payloads, `@out` fields belong to write
  payloads; an optional `writeOnly` argument keeps a field on the requested side
  (`true`) or read side (`false`).
- Profile mappings cover only recognized type/unit/scaling combinations.
  `ha_profile` defaults to empty; bit-map fields are assigned
  `binary_sensor`.
- Command names use the upstream TypeSpec model name verbatim. The
  slash-based hierarchy in hand-curated `config/*.json` files is not generated.

## Defaults

- `--ebusd-root`: `tools/ebus-profile-gen/ebusd-configuration`
- `--ebus-typespec-root`: `tools/ebus-profile-gen/ebus-typespec`
- `--key-prefix`: derived from the full lowercased tsp stem (e.g.
  `08.ehp.tsp` → `08.ehp_`, `52.mc2.mc.4.tsp` → `52.mc2.mc.4_`); override
  with `--key-prefix` to use a different stem or strip the slave address
- `--zz`: optional hexadecimal destination byte override (`00`–`ff`); absent
  an override, the generator derives ZZ from the filename prefix, then a
  numeric commented `// @zz(0x...)` in the entry file, and finally falls back
  to `08`. Explicit command/model `@zz` metadata takes precedence.
- `--out-generated`: `tools/ebus-profile-gen/generated/`
- `--validate`: true (fail on constraint violations)
- `--log`: `<out-generated>/<tsp_stem>.conversion.jsonl` (write; gitignored)
- `--log-level`: `info` (min severity written; `debug|info|warn|error`)
- `--no-log`: disable conversion log writing

## Conversion log (`generated/<tsp_stem>.conversion.jsonl`)

The generator emits a structured JSONL conversion log alongside the two output
files. One record per decision (parse/resolve/template/profile/command/emit),
so you can debug *what* was converted and *why* something was skipped or
defaulted:

```
{"stage":"parse","severity":"warn","reason":"scalar redefined ...","scalar":"cntstarts","line":8,...}
{"stage":"resolve","severity":"warn","reason":"type has no TypeSpec→library mapping ...","input_type":"phaseok","datatype":"phaseok",...}
{"stage":"command","severity":"warn","reason":"zz+id collides ...","zz":"08","id":"b5090d0800","name":"source","duplicate":...}
```

Each record carries `stage`, `severity`, `reason`, `classification` (`native` /
`profile` / `unsupported` / `defaulted`), `action`, plus context
(`model`, `field`, `scalar`, `key`, `name`, `zz`, `id`, `profile`,
`line`, `namespace`, `source`). The CLI prints a severity summary plus the
top warnings to stderr, with the full detail in the JSONL file.

Use `--log-level warn` to suppress debug noise, `--no-log` to skip writing the
file, or `--log <path>` to override the location. Validation (`--validate`)
fails on defaulted/unsupported type mappings, emitted template definitions,
zz+id collisions, commands with neither an `id` nor a `wid` (or an `id`/`wid`
outside the 2-6 byte range), referenced profiles that do not exist, and
trailing underscores — treating the generator output as ready to use only when
none of those are present.

## Testing

`test_golden_ids.py` runs the full resolve→parse→map pipeline in-process and
asserts representative command ids/wids against the archived eBUS ground
truth (concatenation model, BI gate, write-only `id: ""`):

```bash
python3 tools/ebus-profile-gen/test_golden_ids.py
```

