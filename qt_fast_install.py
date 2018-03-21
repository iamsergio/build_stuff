#!/usr/bin/env python2

#MIT License

#Copyright (c) 2018 Sergio Martins

#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:

#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.

#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

import os
from os import listdir
from shutil import copy2

def copy_file(src_file, dest_path):
    try:
        copy2(src_file, dst_path)
        return True
    except:
        print "Error: failed to copy " + src_file + " to " + dest_path
        return False

_source_dir = os.path.normcase(os.getenv('QT_SOURCE', ''))
_install_dir = os.path.normcase(os.getenv('QT_INSTALL', ''))
if not _source_dir:
    print "$QT_SOURCE not set"
    exit(1)

_source_dir = os.path.abspath(_source_dir + '/qt5')

if not _install_dir:
    print "$QT_INSTALL not set"
    exit(1)

cwd = os.path.normcase(os.getcwd())
if not cwd.startswith(_source_dir):
    print "You must be inside the Qt source directory"
    print _source_dir
    exit(1)

# From /c/d/sources/qt/qt5/qtbase return /qtbase
rel_path = cwd.replace( _source_dir, '')
rel_path = rel_path[1:] # drop the first /, now it's qtbase

if not rel_path:
    print "You must be inside a module, like qtbase"
    exit(1)

# separate by /
rel_path = rel_path.split(os.sep)

# Our module is the first one, 'qtbase' for example
module_name = rel_path[0]

# now we install stuff
src_base_path = _source_dir + os.sep + module_name + os.sep

stuff_to_install = ['bin', '/plugins/platforms', '/plugins/generic', '/plugins/imageformats', '/plugins/printsupport', '/plugins/sqldrivers']

for stuff in stuff_to_install:
    src_path = os.path.abspath(src_base_path + stuff)
    dst_path = os.path.abspath(_install_dir + os.sep + stuff) # sprinkle abspath to normalize slashes on windows

    if not os.path.exists(src_path):
        continue

    for src_file in listdir(src_path):
        print "Copying " + src_file + "..."
        if not copy_file(src_path + os.sep + src_file, dst_path):
            exit(-1)

print "Done!"
exit(0)
