# Passed to AVM's configure as -DCMAKE_PROJECT_INCLUDE=<this file>, so it
# runs right after AVM's project() call without changing the AVM checkout.
#
# MSVC 19.5x (Visual Studio 2026) never finishes compiling
# highbd_variance_avx2.c at /O2; turning the SSA optimizer off for that one
# file works around it. See https://github.com/AOMediaCodec/avm/issues/5532
if(MSVC AND MSVC_VERSION GREATER_EQUAL 1950)
  set_source_files_properties(
    "${CMAKE_SOURCE_DIR}/avm_dsp/x86/highbd_variance_avx2.c"
    PROPERTIES COMPILE_OPTIONS "/d2SSAOptimizer-")
endif()
