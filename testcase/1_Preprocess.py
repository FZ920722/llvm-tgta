#!/usr/bin/env python3

import re
import os
import copy
import json
import shlex
import shutil
import pandas as pd

from argparse import ArgumentParser
from multiprocessing import Semaphore, Pool

# - fvp-armv8r:nsh
# - qemu-armv8a:nsh
# - qemu-armv7a:nsh
# - qemu-armv7r:nsh
# - fvp-armv8r-aarch32:nsh

def IRCompile(_param):
    global SPACE_PATH
    _dn, _dd = _param
    _sfname, _ssuffix = os.path.splitext(os.path.basename(_dd['file']))
    _source_compiler = os.path.basename(_dd['arguments'][0])
    if _source_compiler != "cc" and _ssuffix not in [".s", ".S"]:
        # (1) 指令分析
        _temp_target, _, _, _temp_compiler = _source_compiler.split('-')
        # -marm -march=armv4t -mfloat-abi=hard
        _temp_sl = [f"--target={_temp_target}", "-w", "-S", "-emit-llvm", "-gline-tables-only", "-O0", "-Xclang", \
                    "-disable-O0-optnone", "-fno-builtin", "-fno-jump-tables", "-fno-optimize-sibling-calls"] + \
                    [_ditem for _ditem in _dd['arguments'][1:] if not _ditem.startswith(('-g', '-O', '-fvisibility=', '-mlong-calls', ))]
        _temp_sl[-2] = os.path.join(SPACE_PATH, f"{_sfname}.ll")
        if _temp_compiler == 'gcc':
            _temp_sl = ['clang'] + _temp_sl
        elif _temp_compiler == 'g++':
            _temp_sl = ['clang++'] + _temp_sl
        else:
            exit(1)
        _temp_sl[-1] = os.path.join(_dd['directory'], _temp_sl[-1])

        # (2) 指令执行
        os.chdir(_dd['directory'])
        _temp_ss = shlex.join(_temp_sl)
        if os.system(_temp_ss + "> ~/data.log") != 0:
            print( _temp_ss + '\n')
            exit(1)


if __name__ == "__main__":
    global CPU_COUNT, NUTTX_PATH, SPACE_PATH

    CPU_COUNT =  os.cpu_count()

    parser = ArgumentParser(description='preprocess')

    parser.add_argument('-s', '--space',    type=str,   help='The address of work space')
    parser.add_argument('-n', '--nuttx',    type=str,   help='The address of nuttx project')
    parser.add_argument('-p', '--platform', type=str,   help='The compile target of platform')

    args = parser.parse_args()

    SPACE_PATH = args.space
    NUTTX_PATH = args.nuttx

    print(f"================= 1_Preprorcess =================")
    if os.path.exists(SPACE_PATH):
        shutil.rmtree(SPACE_PATH)
    os.makedirs(SPACE_PATH)

    print("S1. compile_commands.json Generate")
    os.chdir(NUTTX_PATH)
    if os.system(f"make distclean") != 0:
        exit(1)

    if os.system(f"./tools/configure.sh -l {args.platform}") != 0:
        exit(1)

    if os.system(f"bear make -j{CPU_COUNT}") != .0:
        exit(1)

    print("S2. IR Generate")
    with open(os.path.abspath(os.path.join(NUTTX_PATH, 'compile_commands.json')), "r", encoding="utf-8") as f:
        loaded_data = json.load(f)
    print(len(loaded_data))

    with Pool(processes=CPU_COUNT) as pool:
        pool.map(IRCompile, zip(range(len(loaded_data)), loaded_data))

    print("S3. IR Link")
    os.chdir(SPACE_PATH)
    if os.system(f"llvm-link *.ll -o unoptimized.ll") != 0:
        exit(1)

    print("S4. IR optimize")
    if os.system(  "opt \
                    -S unoptimized.ll \
                    -mem2reg \
                    -indvars \
                    -loop-simplify \
                    -inline \
                    -instcombine \
                    -globaldce \
                    -dce \
                    -lowerswitch \
                    -simplifycfg \
                    -o optimized.ll") != 0:
        exit(1)

    print(f"S5. IR Preprorcess")
    if os.system(  "opt \
                    -S optimized.ll \
                    -passes=helloworld \
                    -o new_optimized.ll") != 0:
        exit(1)
