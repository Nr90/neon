#!/usr/bin/env python
# Copyright 2014 Nervana Systems Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Top-level control of the building/installation/cleaning of various targets

import optparse
import re
import os
import os.path
import subprocess

p = optparse.OptionParser()
p.add_option("-k", "--kernels", action="store_true", dest="kernels", default=True,
             help="build or update all kernels (default)")
p.add_option("-c", "--clean", action="store_true", dest="clean",
             help="delete all generated files")
p.add_option("-p", "--preprocess", action="store_true", dest="preprocess",
             help="preprocess sass files only (for devel and debug)")
p.add_option("-d", "--dump", action="store_true", dest="dump",
             help="disassemble cubin files only (for devel and debug)")
p.add_option("-j", "--max_concurrent", type="int", default=10,
             help="Concurrently launch a maximum of this many processes.")
opts, args = p.parse_args()

base_dir = os.path.dirname(os.path.realpath(__file__))
cu_dir = os.path.join(base_dir, "kernels", "cu")
sass_dir = os.path.join(base_dir, "kernels", "sass")
pre_dir = os.path.join(base_dir, "kernels", "pre")
cubin_dir = os.path.join(base_dir, "kernels", "cubin")
dump_dir = os.path.join(base_dir, "kernels", "dump")
nvcc_opts = ["nvcc", "-arch sm_50", "-cubin"]  # TODO require 52 for hpool and hconv kenels
maxas_opts_i = ["maxas.pl", "-i", "-w"]
maxas_opts_p = ["maxas.pl", "-p"]
dump_opts = ["nvdisasm", "-raw"]

include_re = re.compile(r'^<INCLUDE\s+file="([^"]+)"\s*/>')


def extract_includes(name, includes=None):
    if not includes:
        includes = list()
    sass_file = os.path.join(sass_dir, name)
    includes.append(sass_file)
    sass = open(sass_file, "r")
    for line in sass:
        match = include_re.search(line)
        if match:
            extract_includes(match.group(1), includes)
    return includes

for d in (cubin_dir, pre_dir, dump_dir):
    if not os.path.exists(d):
        os.mkdir(d)

compile_cubins = []
build_cubins = []
build_pre = []
dump_cubins = []

for cu_name in sorted(os.listdir(cu_dir)):
    if cu_name[-3:] != ".cu":
        continue

    kernel_name = cu_name[:-3]
    components = kernel_name.split("_")
    maxas_i = maxas_opts_i + ["-k " + kernel_name]
    maxas_p = maxas_opts_p + []
    try:
        components.remove("vec")
        maxas_i.append("-Dvec 1")
        maxas_p.append("-Dvec 1")
    except ValueError:
        pass

    sass_name = "_".join(components) + ".sass"
    cubin_name = kernel_name + ".cubin"
    pre_name = kernel_name + "_pre.sass"
    dump_name = kernel_name + "_dump.sass"

    cu_file = os.path.join(cu_dir, cu_name)
    sass_file = os.path.join(sass_dir, sass_name)
    pre_file = os.path.join(pre_dir, pre_name)
    cubin_file = os.path.join(cubin_dir, cubin_name)
    dump_file = os.path.join(dump_dir, dump_name)

    if opts.clean:
        for f in (cubin_file, pre_file, dump_file):
            if os.path.exists(f):
                os.remove(f)
        continue

    if not os.path.exists(sass_file):
        # TODO print warning?
        continue

    pre_age = os.path.getmtime(pre_file) if os.path.exists(pre_file) else 0
    cubin_age = os.path.getmtime(cubin_file) if os.path.exists(cubin_file) else 0
    dump_age = os.path.getmtime(dump_file) if os.path.exists(dump_file) else 0

    if opts.kernels and os.path.getmtime(cu_file) > cubin_age:
        compile_cubins.append(nvcc_opts + ["-o %s" % cubin_file, cu_file])

    if opts.dump and cubin_age > 0 and cubin_age > dump_age:
        dump_cubins.append(dump_opts + [cubin_file, ">", dump_file])

    if opts.kernels or opts.preprocess:
        for include in extract_includes(sass_name):
            if not os.path.exists(include):
                # TODO print warning?
                break
            include_age = os.path.getmtime(include)
            if opts.preprocess:
                if include_age > pre_age:
                    build_pre.append(maxas_p + [sass_file, pre_file])
                    break
            elif opts.kernels:
                if include_age > cubin_age:
                    build_cubins.append(maxas_i + [sass_file, cubin_file])
                    break


def run_commands(commands, max_concurrent=25):
    if len(commands) > 0:
        i = 0
        while i < len(commands):
            command_batch = commands[i:i + max_concurrent]
            procs = []
            for cmdlist in command_batch:
                cmdline = " ".join(cmdlist)
                proc = subprocess.Popen(cmdline, shell=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                procs.append((proc, cmdline))

            for proc, cmdline in procs:
                code = proc.wait()
                print cmdline
                if code:
                    print proc.stderr.read()
                output = proc.stdout.read()
                if output:
                    print output
            i += max_concurrent

run_commands(compile_cubins, opts.max_concurrent)
run_commands(build_cubins, opts.max_concurrent)
run_commands(build_pre, opts.max_concurrent)
run_commands(dump_cubins, opts.max_concurrent)
