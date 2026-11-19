# Copyright © 2018, VideoLAN and dav2d authors
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

#
# Build definition for the dav2d tests
#

# Leave subdir if tests are disabled
if not get_option('enable_tests')
    subdir_done()
endif

checkasm_dependency = dependency('checkasm',
    fallback: ['checkasm', 'checkasm_dep'],
    required: false
)

if is_asm_enabled and checkasm_dependency.found()

    checkasm_args = [
        '-DCHECKASM_HAVE_GENERIC=@0@'.format(cdata.get('HAVE_C11_GENERIC'))
    ]

    checkasm_sources = files(
        'checkasm/checkasm.c',
        'checkasm/bacp.c',
        'checkasm/msac.c',
        'checkasm/pal.c',
        'checkasm/refmvs.c',
    )

    checkasm_tmpl_sources = files(
        'checkasm/ccso.c',
        'checkasm/cdef.c',
        'checkasm/deblock.c',
        'checkasm/filmgrain.c',
        'checkasm/ipred.c',
        'checkasm/itx.c',
        'checkasm/looprestoration.c',
        'checkasm/mc.c',
        'checkasm/stx.c',
    )

    checkasm_bitdepth_objs = []
    foreach bitdepth : dav2d_bitdepths
        checkasm_bitdepth_lib = static_library(
            'checkasm_bitdepth_@0@'.format(bitdepth),
            checkasm_tmpl_sources,
            include_directories: dav2d_inc_dirs,
            dependencies : [stdatomic_dependencies, checkasm_dependency],
            c_args: ['-DBITDEPTH=@0@'.format(bitdepth)] + checkasm_args,
            install: false,
            build_by_default: false,
        )
        checkasm_bitdepth_objs += checkasm_bitdepth_lib.extract_all_objects(recursive: true)
    endforeach

    link_args = []
    if host_machine.system() == 'windows'
      # MS link.exe and LLD default to an 1 MB stack; binutils ld defaults to
      # 2 or 4 MB depending on bitness. Explicitly set a larger stack, as
      # checkasm tests often can have large buffers on the stack. 8 MB should
      # match common defaults on unix.
      stack_size = 8 * 1024 * 1024
      if cc.get_argument_syntax() == 'msvc'
        link_args += '-stack:@0@'.format(stack_size)
      else
        link_args += '-Wl,--stack,@0@'.format(stack_size)
      endif
    endif

    checkasm = executable('checkasm',
        checkasm_sources,

        objects: [
            checkasm_bitdepth_objs,
            libdav2d.extract_all_objects(recursive: true),
            ],

        include_directories: dav2d_inc_dirs,
        build_by_default: false,
        dependencies: [
            thread_dependency,
            libm_dependency,
            checkasm_dependency,
            ],
        c_args: checkasm_args,
        link_args: link_args,
        )

    test('checkasm', checkasm, suite: 'checkasm', timeout: 180, args: '-v')
    benchmark('checkasm', checkasm, suite: 'checkasm', timeout: 3600, args: '--bench')
endif

c99_extension_flag = cc.first_supported_argument(
    '-Werror=c11-extensions',
    '-Werror=c99-c11-compat',
    '-Wc11-extensions',
    '-Wc99-c11-compat',
)

# dav2d_api_headers
foreach header : dav2d_api_headers
    target = header + '_test'

    header_test_exe = executable(target,
        'header_test.c',
        include_directories: dav2d_inc_dirs,
        c_args: ['-DDAV2D_TEST_HEADER="@0@"'.format(header), c99_extension_flag],
        build_by_default: true
    )

    test(target, header_test_exe, suite: 'headers')
endforeach


# fuzzing binaries
subdir('libfuzzer')

# seek stress test binary, depends on dav2d cli tool
if (get_option('enable_tools') and get_option('enable_seek_stress'))
    seek_stress_sources = files('seek_stress.c')
    seek_stress = executable('seek_stress',
        seek_stress_sources, rev_target,
        objects: [
            dav2d.extract_objects('dav2d_cli_parse.c'),
            dav2d_input_objs.extract_objects('input/input.c', 'input/ivf.c'),
        ],
        include_directories: [dav2d_inc_dirs, include_directories('../tools')],
        link_with: libdav2d,
        dependencies: [
            thread_dependency,
            rt_dependency,
            getopt_dependency,
            libm_dependency,
        ],
    )
endif

# Include dav2d test data repository with additional tests
if get_option('testdata_tests')
    subdir('dav2d-test-data')
endif
