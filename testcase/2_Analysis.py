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


if __name__ == "__main__":
    global LLVMTA_SOURCE, IRFILE_PATH, ENTRYS_PATH, MAX_EXTFUNC_BOUND, SPACE_PATH
    #  , IRFILE_PATH, OPFILE_PATH

    LLVMTA_SOURCE = [
        "llvmta",
        "-O0",
        "-float-abi=hard",
        "-mattr=-neon,+vfp2",
        "-disable-tail-calls",
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

    parser = ArgumentParser(description='analysis')
    # (1) work-space
    parser.add_argument('-s', '--space',        type=str,   help='The address of work space')
    # (2) json
    parser.add_argument('-e', '--entrys',       type=str,   help='The entry points list file path')
    # (3) loop max bound
    parser.add_argument('-ml', '--maxloopbound',     type=str,   help='The entry points list file path')
    # (4) extfunc max bound
    parser.add_argument('-mf', '--maxextfuncbound',  type=str,   help='The entry points list file path')
    # (5) ir
    parser.add_argument('-ir', '--IntermediateRepresentation', type=str,   help='The address of nuttx project')

    args = parser.parse_args()

    SPACE_PATH = args.space
    ENTRYS_PATH = args.entrys
    MAX_LOOPBOUND = args.maxloopbound
    MAX_EXTFUNC_BOUND = args.maxextfuncbound
    IRFILE_PATH = args.IntermediateRepresentation


    print(f"================= 2_Analysis =================")

    if os.path.exists(SPACE_PATH):
        shutil.rmtree(SPACE_PATH)
    os.makedirs(SPACE_PATH)

    with open(os.path.abspath(ENTRYS_PATH), "r", encoding="utf-8") as f:
        loaded_data = json.load(f)

    for _x in loaded_data['Tasks']:
        _entry_point = _x["TaskName"]
        _relative_deadline = _x["Period"]
        print(f"\nentry point:{_entry_point}\trDDL:{_relative_deadline}ms")

        _entry_work_space = os.path.join(SPACE_PATH, _entry_point)
        if os.path.exists(_entry_work_space):
            shutil.rmtree(_entry_work_space)
        os.mkdir(_entry_work_space)
        os.chdir(_entry_work_space)

        print(f"S1. Construct CoreInfo.json")
        _core_info_path =  os.path.join(_entry_work_space, "CoreInfo.json")
        with open(_core_info_path, 'w', encoding='utf-8') as f:
            json.dump([{"core": 0,  "tasks": [{"function": _entry_point}]}], f, indent=4, ensure_ascii=False)

        print(f"S2. Extfuncs Generate")
        if os.system(' '.join(LLVMTA_SOURCE + ["--ta-output-unknown-extfuncs",
                                              f"--core-info={_core_info_path}",
                                              f"--ta-analysis-entry-point={_entry_point}",
                                              IRFILE_PATH])) != 0:
            exit(1)    

        if os.path.getsize('ExtFuncAnnotations.csv') > 0:
            df = pd.read_csv('ExtFuncAnnotations.csv', header=None)
            for index, row in df.iterrows():
                row[0] = row[0].replace("<start address>", "1")
                row[0] = row[0].replace("<max cycles/accesses/hits/misses>", f"{MAX_EXTFUNC_BOUND}/1/1/1")
            df.to_csv('ExtFuncAnnotations.csv', index=False, header=0)

        print(f"S3. LoopsBound Generate")
        if os.system(' '.join(LLVMTA_SOURCE + ["--ta-output-unknown-loops",
                                              f"--core-info={_core_info_path}",
                                              f"--ta-analysis-entry-point={_entry_point}",
                                              IRFILE_PATH])) != 0:
            exit(1)

        if os.path.getsize('LoopAnnotations.csv') > 0:
            df = pd.read_csv('LoopAnnotations.csv', header=None)
            for index, row in df.iterrows():
                row[0] = row[0].replace("|-1", f"|{MAX_LOOPBOUND}")
            df.to_csv('LoopAnnotations.csv', index=False, header=0)
        shutil.copy("LoopAnnotations.csv", "LLoopAnnotations.csv")

        print(f"S4. WCET Analyze")
        if os.system(' '.join(LLVMTA_SOURCE + [f"--core-info={_core_info_path}",
                                               f"--ta-analysis-entry-point={_entry_point}",
                                                "--ta-restart-after-external",
                                                "--ta-loop-bounds-file=LoopAnnotations.csv",
                                                "--ta-loop-lowerbounds-file=LLoopAnnotations.csv",
                                                "--ta-extfunc-annotation-file=ExtFuncAnnotations.csv",
                                                IRFILE_PATH])) != 0:
            exit(1)
