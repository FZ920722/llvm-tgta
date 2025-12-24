#!/usr/bin/env python3

import os
import re
import json
import shutil
import subprocess
import pandas as pd

from argparse import ArgumentParser
from multiprocessing import Semaphore, Pool


# os.getcwd()
# os.path.isdir()
# os.path.abspath()
# os.path.dirname(CODE_DIRS[0])
# FILERE = re.compile(r'Loop in file (.*) near line (.*)')
# LOOPRE = re.compile(r'\w*_Pragma\(\s*\"loopbound\s*min\s*(\d+)\s*max\s*(\d+)\s*\"\s*\).*')

global LLVMTA_SOURCE

# "-march=armv8-a",
# "-mcpu=arm7tdmi"
# "-O0-disable-O0-optnone",
LLVMTA_SOURCE = [
    "llvmta",
    "-O0",
    "-float-abi=hard",
    "-mattr=-neon,+vfp2",
    "-disable-tail-calls",
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
    "--core-numbers=1",
    "-debug-only=",
    "/home/fyj/DiskN/WCET_Tool/Data/_AFile/ccl.ll"
]


if __name__ == "__main__":
    global WORK_PATH, IRFILE_PATH, ENTRYS_PATH
    parser = ArgumentParser(description='Preprocessing')
    parser.add_argument('-i', '--irfile',  type=str,   help='The ir file')
    parser.add_argument('-s', '--source',  type=str,   help='The Paht of workspace')
    parser.add_argument('-e', '--entrys',   type=str,   help='Entry points list file')

    args = parser.parse_args()

    print(args.source)
    print(args.irfile)
    print(args.entrys)
    WORK_PATH = args.source
    IRFILE_PATH = args.irfile
    ENTRYS_PATH = args.entrys

    # IRFILE_PATH = os.path.join(ROOT_PATH, "Data", "_IRFile")
    # AFILE_PATH = os.path.join(ROOT_PATH, "Data", "_AFile")
    # OFILE_PATH = os.path.join(ROOT_PATH, "Data", "_OFile")
    # """
    # if os.path.exists(AFILE_PATH):
    #     shutil.rmtree(AFILE_PATH)
    # os.mkdir(AFILE_PATH)

    # shutil.copy(os.path.join(IRFILE_PATH, "optimized.ll"), os.path.join(AFILE_PATH, "optimized.ll"))
    # # 生成新的IR文件,删除有内链汇编的函数;
    # os.chdir(AFILE_PATH)
    # """
    # if os.path.exists(OFILE_PATH):
    #     shutil.rmtree(OFILE_PATH)
    # os.mkdir(OFILE_PATH)

    # for _entry_point in ["hello_main",]:
    #     print(f"================= Analyzing {_entry_point} =================")
    #     # (1) 构建工作区
    #     WORK_SPACE_PATH = os.path.join(OFILE_PATH, _entry_point)
    #     if os.path.exists(WORK_SPACE_PATH):
    #         shutil.rmtree(WORK_SPACE_PATH)
    #     os.mkdir(WORK_SPACE_PATH)

    #     os.chdir(WORK_SPACE_PATH)
    #     # (2) 构建CoreInfo.json
    #     CORE_INFO_PATH =  os.path.join(WORK_SPACE_PATH, "CoreInfo.json")
    #     with open(CORE_INFO_PATH, 'w', encoding='utf-8') as f:
    #         json.dump([{"core": 0,  "tasks": [{"function": _entry_point}]}], f, indent=4, ensure_ascii=False)

    #     # (3) 构建外部函数汇总
    #     if os.system(' '.join(LLVMTA_SOURCE + ["--ta-output-unknown-extfuncs",
    #                                            f"--core-info={CORE_INFO_PATH}",
    #                                            f"--ta-analysis-entry-point={_entry_point}",])) != 0:
    #         exit(1)

        # if os.path.getsize('ExtFuncAnnotations.csv') > 0:
        #     df = pd.read_csv('ExtFuncAnnotations.csv', header=None)
        #     for index, row in df.iterrows():
        #         row[0] = row[0].replace("<start address>", "1")
        #         row[0] = row[0].replace("<max cycles/accesses/hits/misses>", "1/1/1/1")
        #     df.to_csv('ExtFuncAnnotations.csv', index=False, header=0)

        # # (4) 构建循环边界汇总
        # if os.system(' '.join(LLVMTA_SOURCE + ["--ta-output-unknown-loops",
        #                                        f"--core-info={CORE_INFO_PATH}",
        #                                        f"--ta-analysis-entry-point={_entry_point}",])) != 0:
        #     exit(1)
        # if os.path.getsize('LoopAnnotations.csv') > 0:
        #     df = pd.read_csv('LoopAnnotations.csv', header=None)
        #     for index, row in df.iterrows():
        #         row[0] = row[0].replace("|-1", "|1")
        #     df.to_csv('LoopAnnotations.csv', index=False, header=0)
        # shutil.copy("LoopAnnotations.csv", "LLoopAnnotations.csv")

        # # (5) WCET分析
        # if os.system(' '.join(LLVMTA_SOURCE + [f"--core-info={CORE_INFO_PATH}",
        #                                        f"--ta-analysis-entry-point={_entry_point}",
        #                                         "--ta-restart-after-external",
        #                                         "--ta-loop-bounds-file=LoopAnnotations.csv",
        #                                         "--ta-loop-lowerbounds-file=LLoopAnnotations.csv",
        #                                         "--ta-extfunc-annotation-file=ExtFuncAnnotations.csv",])) != 0:
        #     exit(1)



