#include <memory>

#include "llvm/ADT/Triple.h"
#include "llvm/ADT/ScopeExit.h"

#include "llvm/IR/Module.h"
#include "llvm/IR/Verifier.h"
#include "llvm/IR/DataLayout.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/DiagnosticInfo.h"
#include "llvm/IR/DiagnosticPrinter.h"
#include "llvm/IR/LegacyPassManager.h"

#include "llvm/CodeGen/CommandFlags.h"
#include "llvm/CodeGen/TargetPassConfig.h"
#include "llvm/CodeGen/MachineModuleInfo.h"
#include "llvm/CodeGen/MachineFunctionPass.h"
#include "llvm/CodeGen/LinkAllCodegenComponents.h"

#include "llvm/MC/TargetRegistry.h"
#include "llvm/MC/SubtargetFeature.h"

#include "llvm/Support/Host.h"
#include "llvm/Support/InitLLVM.h"
#include "llvm/Support/WithColor.h"
#include "llvm/Support/SourceMgr.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/TargetSelect.h"
#include "llvm/Support/ManagedStatic.h"
#include "llvm/Support/ToolOutputFile.h"

#include "llvm/Target/TargetMachine.h"
#include "llvm/Target/TargetLoweringObjectFile.h"

#include "llvm/Pass.h"
#include "llvm/InitializePasses.h"
#include "llvm/IRReader/IRReader.h"
#include "llvm/Transforms/Utils/Cloning.h"
#include "llvm/Analysis/TargetLibraryInfo.h"

// MODIFICATION: include headers needed to trigger timing analysis
#include "LLVMPasses/TimingAnalysisPasses.h"
#include "LLVMPasses/MachineFunctionCollector.h"
// END MODIFICATION
using namespace llvm;

static codegen::RegisterCodeGenFlags CGF;

static cl::opt<std::string> InputFilename(
  cl::Positional,
  cl::init("-"),
  cl::desc("input ir"));

static cl::opt<char> OptLevel("O",
  cl::Prefix,
  cl::ZeroOrMore,
  cl::init(' '),
  cl::desc("Determine optimization level. [-O0, -O1, -O2, or -O3] (default = '-O2')"));

namespace {
  static ManagedStatic<std::vector<std::string>> RunPassNames;

  struct RunPassOption {
    void operator=(const std::string &Val) const {
      if (Val.empty())
        return;
      SmallVector<StringRef, 8> PassNames;
      StringRef(Val).split(PassNames, ',', -1, false);
      for (auto PassName : PassNames)
        RunPassNames->push_back(std::string(PassName));
    }
  };
} // namespace

struct LLCDiagnosticHandler : public DiagnosticHandler {
  bool *HasError;
  LLCDiagnosticHandler(bool *HasErrorPtr) : HasError(HasErrorPtr) {}
  bool handleDiagnostics(const DiagnosticInfo &DI) override {
    if (DI.getKind() == llvm::DK_SrcMgr) {
      const auto &DISM = cast<DiagnosticInfoSrcMgr>(DI);
      const SMDiagnostic &SMD = DISM.getSMDiag();

      if (SMD.getKind() == SourceMgr::DK_Error)
        *HasError = true;

      SMD.print(nullptr, errs());

      // For testing purposes, we print the LocCookie here.
      if (DISM.isInlineAsmDiag() && DISM.getLocCookie())
        WithColor::note() << "!srcloc = " << DISM.getLocCookie() << "\n";

      return true;
    }

    if (DI.getSeverity() == DS_Error)
      *HasError = true;

    if (auto *Remark = dyn_cast<DiagnosticInfoOptimizationBase>(&DI))
      if (!Remark->isEnabled())
        return true;

    DiagnosticPrinterRawOStream DP(errs());
    errs() << LLVMContext::getDiagnosticMessagePrefix(DI.getSeverity()) << ": ";
    DI.print(DP);
    errs() << "\n";
    return true;
  }
};

static int compileModule(char **, LLVMContext &);

static bool addPass(PassManagerBase &, const char *, StringRef, TargetPassConfig &);

// main - Entry point
int main(int argc, char **argv) {
  InitLLVM X(argc, argv);

  // (1) Initialize targets first, so that --version shows registered targets.
  InitializeAllTargets();
  InitializeAllTargetMCs();
  InitializeAllAsmPrinters();
  InitializeAllAsmParsers();

  // (2) Initialize codegen and IR passes used by llc so that the -print-after, -print-before, and -stop-after options work.
  PassRegistry *Registry = PassRegistry::getPassRegistry();
  initializeCore(*Registry);
  initializeCodeGen(*Registry);
  initializeLoopStrengthReducePass(*Registry);
  initializeLowerIntrinsicsPass(*Registry);
  initializeEntryExitInstrumenterPass(*Registry);
  initializePostInlineEntryExitInstrumenterPass(*Registry);
  initializeUnreachableBlockElimLegacyPassPass(*Registry);
  initializeConstantHoistingLegacyPassPass(*Registry);
  initializeScalarOpts(*Registry);
  initializeVectorization(*Registry);
  initializeScalarizeMaskedMemIntrinLegacyPassPass(*Registry);
  initializeExpandReductionsPass(*Registry);
  initializeExpandVectorPredicationPass(*Registry);
  initializeHardwareLoopsPass(*Registry);
  initializeTransformUtils(*Registry);
  initializeReplaceWithVeclibLegacyPass(*Registry);

  // (3) Initialize debugging passes.
  initializeScavengerTestPass(*Registry);

  // (4) Register the target printer for --version.
  cl::AddExtraVersionPrinter(TargetRegistry::printRegisteredTargetsForVersion);

  // (5) 参数跟新配置；
  cl::ParseCommandLineOptions(argc, argv, "llvm system compiler\n");

  LLVMContext Context;
  Context.setDiscardValueNames(false);

  // (5) Set a diagnostic handler that doesn't exit on the first error
  bool HasError = false;
  Context.setDiagnosticHandler(std::make_unique<LLCDiagnosticHandler>(&HasError));

  // (*) 核心代码：
  if (int RetVal = compileModule(argv, Context))
    return RetVal;

  return 0;
}

static int compileModule(char **argv, LLVMContext &Context) {
  // Load the module to be compiled.
  Triple TheTriple;
  SMDiagnostic Err;
  std::unique_ptr<Module> M;

  // -mattr
  auto MAttrs = codegen::getMAttrs();
  std::string CPUStr = codegen::getCPUStr(), FeaturesStr = codegen::getFeaturesStr();

  CodeGenOpt::Level OLvl = CodeGenOpt::Default;
  switch (OptLevel) {
    default:
      WithColor::error(errs(), argv[0]) << "invalid optimization level.\n";
      return 1;
    case ' ':
      break;
    case '0':
      OLvl = CodeGenOpt::None;
      break;
    case '1':
      OLvl = CodeGenOpt::Less;
      break;
    case '2':
      OLvl = CodeGenOpt::Default;
      break;
    case '3':
      OLvl = CodeGenOpt::Aggressive;
      break;
  }

  TargetOptions Options;
  auto InitializeOptions = [&](const Triple &TheTriple) {
    Options = codegen::InitTargetOptionsFromCodeGenFlags(TheTriple);
    Options.BinutilsVersion = TargetMachine::parseBinutilsVersion("");
    Options.DisableIntegratedAS = false;
    Options.MCOptions.ShowMCEncoding = false;
    Options.MCOptions.MCUseDwarfDirectory = true;
    Options.MCOptions.AsmVerbose = true;
    Options.MCOptions.PreserveAsmComments = true;
    // Options.MCOptions.SplitDwarfFile = "";
  };

  Optional<Reloc::Model> RM = codegen::getExplicitRelocModel();

  const Target *TheTarget = nullptr;
  std::unique_ptr<TargetMachine> Target;

  // If user just wants to list available options, skip module loading
  auto SetDataLayout = [&](StringRef DataLayoutTargetTriple) -> Optional<std::string> {
    // If we are supposed to override the target triple, do so now.
    std::string IRTargetTriple = DataLayoutTargetTriple.str();
    TheTriple = Triple(IRTargetTriple);
    if (TheTriple.getTriple().empty())
      TheTriple.setTriple(sys::getDefaultTargetTriple());
    std::string Error;
    TheTarget = TargetRegistry::lookupTarget(codegen::getMArch(), TheTriple, Error);
    if (!TheTarget) {
      WithColor::error(errs(), argv[0]) << Error;
      exit(1);
    }
    // On AIX, setting the relocation model to anything other than PIC is considered a user error.
    if (TheTriple.isOSAIX() && RM.hasValue() && *RM != Reloc::PIC_)
      WithColor::error(errs(), argv[0]) << "invalid relocation model, AIX only supports PIC" << InputFilename;

    InitializeOptions(TheTriple);
    Target = std::unique_ptr<TargetMachine>(TheTarget->createTargetMachine(TheTriple.getTriple(), CPUStr, FeaturesStr, Options, RM, codegen::getExplicitCodeModel(), OLvl));
    assert(Target && "Could not allocate target machine!");
    return Target->createDataLayout().getStringRepresentation();
  };

  M = parseIRFile(InputFilename, Err, Context, SetDataLayout);
  if (!M) {
    Err.print(argv[0], WithColor::error(errs(), argv[0]));
    return 1;
  }
  assert(M && "Should have exited if we didn't have a module!");

  if (codegen::getFloatABIForCalls() != FloatABI::Default)
    Options.FloatABIType = codegen::getFloatABIForCalls();

  // Figure out where we are going to send the output.
  StringRef IFN = InputFilename;

  std::error_code EC;
  sys::fs::OpenFlags OpenFlags = sys::fs::OF_None;
  std::unique_ptr<ToolOutputFile> Out = std::make_unique<ToolOutputFile>(std::string(IFN.drop_back(3)) + ".s", EC, OpenFlags);

  if (EC)
    return -1;

  if (!Out)
    return 1;

  // Ensure the filename is passed down to CodeViewDebug.
  Target->Options.ObjectFilenameForDebug = Out->outputFilename();

  std::unique_ptr<ToolOutputFile> DwoOut;

  // Build up all of the passes that we want to do to the module.
  legacy::PassManager PM;

  // Add an appropriate TargetLibraryInfo pass for the module's triple.
  TargetLibraryInfoImpl TLII(Triple(M->getTargetTriple()));

  PM.add(new TargetLibraryInfoWrapperPass(TLII));

  // Verify module immediately to catch problems before doInitialization() is called on any passes.
  if (verifyModule(*M, &errs()))
    WithColor::error(errs(), argv[0]) << "input module cannot be verified" << InputFilename;

  // Override function attributes based on CPUStr, FeaturesStr, and command line flags.
  codegen::setFunctionAttributes(CPUStr, FeaturesStr, *M);

  if (mc::getExplicitRelaxAll() && codegen::getFileType() != CGFT_ObjectFile)
    WithColor::warning(errs(), argv[0]) << ": warning: ignoring -mc-relax-all because filetype != obj";

  {
    raw_pwrite_stream *OS = &Out->os();
    // Manually do the buffering rather than using buffer_ostream, so we can memcmp the contents in CompileTwice mode
    SmallVector<char, 0> Buffer;
    const char *argv0 = argv[0];
    LLVMTargetMachine &LLVMTM = static_cast<LLVMTargetMachine &>(*Target);
    MachineModuleInfoWrapperPass *MMIWP = new MachineModuleInfoWrapperPass(&LLVMTM);

    // Construct a custom pass pipeline that starts after instruction selection.
    if (!RunPassNames->empty()) {
      TargetPassConfig &TPC = *LLVMTM.createPassConfig(PM);
      if (TPC.hasLimitedCodeGenPipeline()) {
        WithColor::warning(errs(), argv[0]) << "run-pass cannot be used with " << TPC.getLimitedCodeGenPipelineReason(" and ") << ".\n";
        return 1;
      }

      TPC.setDisableVerify(false);
      PM.add(&TPC);
      PM.add(MMIWP);
      TPC.printAndVerify("");
      for (const std::string &RunPassName : *RunPassNames) {
        if (addPass(PM, argv0, RunPassName, TPC))
          return 1;
      }
      TPC.setInitialized();
      PM.add(createPrintMIRPass(*OS));
      PM.add(createFreeMachineFunctionPass());
    }
    else if (Target->addPassesToEmitFile(PM, *OS, DwoOut ? &DwoOut->os() : nullptr, codegen::getFileType(), false, MMIWP)) {
      WithColor::warning(errs(), argv[0]) << "target does not support generation of this file type";
    }
    const_cast<TargetLoweringObjectFile *>(LLVMTM.getObjFileLowering())->Initialize(MMIWP->getMMI().getContext(), *Target);
    // MODIFICATION: Add the passes needed for timing analysis to the pass manager
    for (auto TAPass : getTimingAnalysisPasses(*Target)) {
      PM.add(TAPass);
    }
    // END MODIFICATION

    // Before executing passes, print the final values of the LLVM options.
    cl::PrintOptionValues();

    // If requested, run the pass manager over the same module again, to catch any bugs due to persistent state in the passes. Note that opt has the same functionality, so it may be worth abstracting this out in the future.
    SmallVector<char, 0> CompileTwiceBuffer;

    PM.run(*M); // * * * * *

    auto HasError = ((const LLCDiagnosticHandler *)(Context.getDiagHandlerPtr()))->HasError;
    if (*HasError)
      return 1;
  }

  // Declare success.
  Out->keep();
  if (DwoOut)
    DwoOut->keep();
  return 0;
}

static bool addPass(PassManagerBase &PM, const char *argv0, StringRef PassName, TargetPassConfig &TPC) {
  if (PassName == "none")
    return false;

  const PassRegistry *PR = PassRegistry::getPassRegistry();
  const PassInfo *PI = PR->getPassInfo(PassName);
  if (!PI) {
    WithColor::error(errs(), argv0) << "run-pass " << PassName << " is not registered.\n";
    return true;
  }

  Pass *P;
  if (PI->getNormalCtor())
    P = PI->getNormalCtor()();
  else {
    WithColor::error(errs(), argv0) << "cannot create pass: " << PI->getPassName() << "\n";
    return true;
  }
  std::string Banner = std::string("After ") + std::string(P->getPassName());
  TPC.addMachinePrePasses();
  PM.add(P);
  TPC.addMachinePostPasses(Banner);

  return false;
}
