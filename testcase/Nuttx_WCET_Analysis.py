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


def IRCompile(_param):
    global IRFILE_PATH
    _dn, _dd = _param
    # print(_dn)
    _sfname, _ssuffix = os.path.splitext(os.path.basename(_dd['file']))
    _source_compiler = os.path.basename(_dd['arguments'][0])
    if _source_compiler != "cc" and _ssuffix not in [".s", ".S"]:
        # (1) 指令分析
        _temp_target, _, _, _temp_compiler = _source_compiler.split('-')
        # -marm -march=armv4t -mfloat-abi=hard
        _temp_sl = [f"--target={_temp_target}", "-w", "-S", "-emit-llvm", "-gline-tables-only", "-O0", "-Xclang", \
                    "-disable-O0-optnone", "-fno-builtin", "-fno-jump-tables", "-fno-optimize-sibling-calls"] + \
                    [_ditem for _ditem in _dd['arguments'][1:] if not _ditem.startswith(('-g', '-O', '-fvisibility=', '-mlong-calls', ))]
        _temp_sl[-2] = os.path.join(IRFILE_PATH, f"{_sfname}.ll")
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
        if os.system(_temp_ss + "> ~/data.log") != 0:   # " >/dev/null | tee -a {_log_txt}",
            print( _temp_ss + '\n')
            exit(1)


if __name__ == "__main__":
    global CPU_COUNT, SPACE_PATH, NUTTX_PATH, ENTRYS_PATH, IRFILE_PATH, OPFILE_PATH, LLVMTA_SOURCE, IR_TARGET_PATH

    CPU_COUNT =  os.cpu_count()
    LLVMTA_SOURCE = [
        "llvmta",
        "-O0",
        "-float-abi=hard",
        "-mattr=-neon,+vfp2",
        "-disable-tail-calls",
        # "-march=armv8-a",
        # "-mcpu=arm7tdmi"
        # "-O0-disable-O0-optnone",
        "--ta-quiet=true",
        "--ta-strict=false",
        "--ta-lpsolver-effort=maximal",
        "--ta-icache-persistence=conditionalmust",
        "--ta-dcache-persistence=conditionalmust",
        "--ta-l2cache-persistence=conditionalmust",
        "--ta-num-callsite-tokens=3",
        "--ta-memory-type=separatecaches",
        "--ta-muarch-type=outoforder",
        "--ta-unblock-stores=true",
        "--ta-dcache-write-back=true",
        "--ta-dcache-write-allocate=true",
        "--ta-array-analysis=true",
        "--shared-cache-Persistence-Analysis=false",
        "--ta-dcache-assoc=8",
        "--ta-dcache-nsets=128",
        "--ta-dcache-linesize=64",
        "--ta-icache-assoc=8",
        "--ta-icache-nsets=128",
        "--ta-icache-linesize=64",
        "--ta-l2cache-assoc=8",
        "--ta-l2cache-nsets=1024",
        "--ta-l2cache-linesize=64",
        "--ta-mem-latency=100",
        "--ta-lpsolver=lpsolve",
        "--core-numbers=1",
        "-debug-only="
    ]

    parser = ArgumentParser(description='llvm-ta to nuttx')
    parser.add_argument('-s', '--space',   type=str,   help='The address of work space')
    parser.add_argument('-n', '--nuttx',   type=str,   help='The address of nuttx project')
    parser.add_argument('-e', '--entrys',   type=str,   help='The entry points list file path')
    parser.add_argument('-p', '--platform',   type=str,   help='The compile target of platform')
    # - fvp-armv8r:nsh
    # - qemu-armv8a:nsh
    # - qemu-armv7a:nsh
    # - qemu-armv7r:nsh
    # - fvp-armv8r-aarch32:nsh

    args = parser.parse_args()
    SPACE_PATH = args.space
    NUTTX_PATH = args.nuttx
    ENTRYS_PATH = args.entrys


    print(f"================= STEP 1 Compile =================")
    IRFILE_PATH= os.path.join(SPACE_PATH, "_IRFile")
    if os.path.exists(IRFILE_PATH):
        shutil.rmtree(IRFILE_PATH)
    os.makedirs(IRFILE_PATH)

    os.chdir(NUTTX_PATH)
    if os.system(f"make distclean") != 0:
        exit(1)

    if os.system(f"./tools/configure.sh -l {args.platform}") != 0:
        exit(1)

    if os.system(f"bear make -j{CPU_COUNT}") != 0:
        exit(1)


    print(f"================= STEP 2 Preprorcess =================")
    print("S2.1 IR Generate")
    with open(os.path.abspath(os.path.join(NUTTX_PATH, 'compile_commands.json')), "r", encoding="utf-8") as f:
        loaded_data = json.load(f)
    # print(len(loaded_data))

    with Pool(processes=CPU_COUNT) as pool:
        pool.map(IRCompile, zip(range(len(loaded_data)), loaded_data))

    os.chdir(IRFILE_PATH)
    print("S2.2 IR Link")
    if os.system(f"llvm-link *.ll -o unoptimized.ll") != 0:
        exit(1)

    print("S2.3 IR optimize")
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

    print(f"S2.4 IR Preprorcess")
    if os.system(  "opt \
                    -S optimized.ll \
                    -passes=helloworld \
                    -o new_optimized.ll") != 0:
        exit(1)

    IR_TARGET_PATH = os.path.join(IRFILE_PATH, "new_optimized.ll")

    print(f"================= STEP 3 Analysis =================")
    OPFILE_PATH= os.path.join(SPACE_PATH, "_OFile")
    if os.path.exists(OPFILE_PATH):
        shutil.rmtree(OPFILE_PATH)
    os.makedirs(OPFILE_PATH)

    os.chdir(OPFILE_PATH)

    for _entry_point in ["hello_main",]:
        # print(f"================= Analyzing {_entry_point} =================")
        entry_work_space = os.path.join(OPFILE_PATH, _entry_point)
        if os.path.exists(entry_work_space):
            shutil.rmtree(entry_work_space)
        os.mkdir(entry_work_space)
        os.chdir(entry_work_space)

        print(f"S3.1 Construct CoreInfo.json")
        core_info_path =  os.path.join(entry_work_space, "CoreInfo.json")
        with open(core_info_path, 'w', encoding='utf-8') as f:
            json.dump([{"core": 0,  "tasks": [{"function": _entry_point}]}], f, indent=4, ensure_ascii=False)

        print(f"S3.2 Extfuncs Generate")
        if os.system(' '.join(LLVMTA_SOURCE + ["--ta-output-unknown-extfuncs",
                                               f"--core-info={core_info_path}",
                                               f"--ta-analysis-entry-point={_entry_point}",
                                               IR_TARGET_PATH])) != 0:
            exit(1)

        if os.path.getsize('ExtFuncAnnotations.csv') > 0:
            df = pd.read_csv('ExtFuncAnnotations.csv', header=None)
            for index, row in df.iterrows():
                row[0] = row[0].replace("<start address>", "1")
                row[0] = row[0].replace("<max cycles/accesses/hits/misses>", "1/1/1/1")
            df.to_csv('ExtFuncAnnotations.csv', index=False, header=0)

        print(f"S3.3 LoopsBound Generate")
        if os.system(' '.join(LLVMTA_SOURCE + ["--ta-output-unknown-loops",
                                               f"--core-info={core_info_path}",
                                               f"--ta-analysis-entry-point={_entry_point}",
                                               IR_TARGET_PATH])) != 0:
            exit(1)
        if os.path.getsize('LoopAnnotations.csv') > 0:
            df = pd.read_csv('LoopAnnotations.csv', header=None)
            for index, row in df.iterrows():
                row[0] = row[0].replace("|-1", "|1")
            df.to_csv('LoopAnnotations.csv', index=False, header=0)
        shutil.copy("LoopAnnotations.csv", "LLoopAnnotations.csv")

        print(f"S3.4 WCET Analyze")
        if os.system(' '.join(LLVMTA_SOURCE + [f"--core-info={core_info_path}",
                                               f"--ta-analysis-entry-point={_entry_point}",
                                                "--ta-restart-after-external",
                                                "--ta-loop-bounds-file=LoopAnnotations.csv",
                                                "--ta-loop-lowerbounds-file=LLoopAnnotations.csv",
                                                "--ta-extfunc-annotation-file=ExtFuncAnnotations.csv",
                                                IR_TARGET_PATH])) != 0:
            exit(1)
