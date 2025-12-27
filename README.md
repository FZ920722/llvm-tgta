# llvm-tgta

## 1. Introduction

This tool statically analyze WCET based on LLVM IR.

## 2. Getting Started

There are no dependencies outside of LLVM to build `llvm-tgta`. The following instructions assume you will build LLVM.

- ARG VARIANT="jammy"

1. Initialize
```sh
sudo apt-get update --fix-missing

export DEBIAN_FRONTEND=noninteractive

sudo apt-get -y install --no-install-recommends --fix-missing lldb gcc gdb bear cmake make ninja-build libboost-all-dev git clangd htop wget fish zsh lld time parallel lp-solve liblpsolve55-dev icecc icecream-sundae libcolamd2 clang-tidy gcc-multilib build-essential ccache python3-pip fakeroot

pip3 install numpy pandas -i https://pypi.tuna.tsinghua.edu.cn/simple

ln -s /usr/lib/lp_solve/liblpsolve55.so /usr/lib/liblpsolve55.so

cd /opt

sudo wget -nv https://packages.gurobi.com/9.5/gurobi9.5.2_linux64.tar.gz

sudo tar xfz gurobi9.5.2_linux64.tar.gz

sudo rm -rf gurobi9.5.2_linux64.tar.gz

sudo ln -s gurobi952/linux64/lib/libgurobi95.so /usr/lib/libgurobi.so
```


2. Clone the LLVM and llvm-tgta
```sh
git clone https://github.com/llvm/llvm-project.git -b llvmorg-14.0.6
cd llvm-project
git clone https://github.com/FZ920722/llvm-tgta.git llvm/tools/llvm-tgta
cd llvm
patch -p2 < tools/llvm-tgta/patches/llvm-14.0.6.llvmta.diff
```

3. Configure LLVM.
```sh
cmake \
-G "Ninja" \
-S <llvm-dir> \
-B <build-dir> \
-Wno-dev \
-Wno-suggest-override \
-DCMAKE_C_COMPILER=gcc \
-DCMAKE_CXX_COMPILER=g++ \
-DCMAKE_BUILD_TYPE=Debug \
-DLLVM_ENABLE_EH=ON \
-DLLVM_USE_LINKER=lld \
-DLLVM_ENABLE_RTTI=ON \
-DLLVM_ENABLE_DUMP=ON \
-DLLVM_ENABLE_ASSERTIONS=ON \
-DLLVM_INCLUDE_BENCHMARKS=OFF \
-DLLVM_ENABLE_PROJECTS="clang;lld;lldb" \
-DLLVM_TARGETS_TO_BUILD="AArch64;ARM;PowerPC;X86;RISCV"
```


5. Build `llvm-tgta`
```sh
cmake --build  <build-dir> -- llvm-tgta
或 cd <build-dir> && ninja -j4 llvm-tgta

sudo ninja install 
```


6. 
```sh
export GUROBI_HOME="/home/....../gurobi911/linux64" 
export PATH="${PATH}:${GUROBI_HOME}/bin"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${GUROBI_HOME}/lib"
```

<!-- # Usage -->

<!-- # Acknowledgements 论文引用-->
