# How to use Platformio Core on this project

Here is a practical guide to set up your dev environment with `clangd` able to
correctly match the Platformio deps in your favorite editor.

No VSCode, Platformio CLI only.

> Inspired by [this template](https://github.com/ironlungx/nvim-pio/tree/main)

## Prerequisities

- `clangd` ready to be run in your IDE.
- `python` (with no required extra package)

## Instructions

1. At the root of this repository, run this python script.

   ```sh
   python3 conv.py
   # You will be asked to enter the PlatformIO environment ID you are currently
   # working on (for instance, "Actionneurs")
   ```

   This will, init LSP helper files for a usage by agnostic editors. So,

   - A `.ccls` file
   - A `compile_commands.json` file

2. Be sure your IDE's LSP client run `clangd` in background with the
   `--background-index` option

3. If you have edited the deps of the PlatformIO environment or you want to
   develop code for another PlatformIO environment, rerun the `conv.py` script
   to resetup the `clangd` helper files.
