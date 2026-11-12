# Windows setup (MSYS2 UCRT64)

Use the "MSYS2 UCRT64" terminal, not MSYS or MINGW64. Do not use WSL for the Windows check.
`.github/workflows/windows.yml` is the reference.

## Packages

    pacman -Syu          # first, if the MSYS2 install is old (reopen the terminal afterwards)
    pacman -S --needed git make autoconf automake flex bison help2man perl python \
        mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-python

## Build Verilator 5.034

    git clone --depth 1 --branch v5.034 https://github.com/verilator/verilator /tmp/verilator
    cd /tmp/verilator
    cp /usr/include/FlexLexer.h src/
    cp /usr/include/FlexLexer.h /ucrt64/include/
    export MSYS2_ARG_CONV_EXCL="-DDEFENV"
    autoconf
    ./configure --prefix=/opt/verilator
    make -j"$(nproc)"
    make install

Do not set `VERILATOR_ROOT`; Verilator rejects it as inconsistent.

## Three Windows fixes (needed after the build)

1. **Kit layout.** The Windows binary looks for `include/` and `bin/verilator_includer` directly
   under the prefix, but `make install` puts them in `share/verilator/`:

        cp -r /opt/verilator/share/verilator/include /opt/verilator/include
        cp -n /opt/verilator/share/verilator/bin/* /opt/verilator/bin/

2. **Native Python first on PATH.** The MSYS `python3` cannot open the `C:/...` paths in
   Verilator's generated makefiles (symptom: empty `Vtb__ALL.cpp`, `undefined reference to WinMain`).

        export PATH=/ucrt64/bin:/opt/verilator/bin:$PATH

3. **C++ standard.** With GCC 16 the default standard gives `undefined reference to
   std::__cxx11::basic_string(...&&)` at link time. Pass `-CFLAGS -std=gnu++17` to every
   `verilator --binary` call:

        verilator --binary --timing -Wall -Wno-fatal -CFLAGS -std=gnu++17 --top-module tb_x x.v tb_x.v
        ./obj_dir/Vtb_x

## Check

    verilator --version   # Verilator 5.034
