#!/usr/bin/env python2

import os, sys, platform
import pprint
import subprocess
import socket
import json
import string
import atexit
import time

_build_stuff_dir = os.getenv('BUILD_STUFF_DIR') + "/"
_build_stuff_file = _build_stuff_dir + "/build_stuff.json"
_build_stuff_build_dir = os.getenv('BUILD_STUFF_BUILD_DIR') + "/"
_extra_config_opts = os.getenv('EXTRA_CONFIGURE_OPTS')
_remove_config_opts=os.getenv("BUILD_STUFF_REMOVE_CONFIG")
_default_make = "make -j12"
_tried_to_build=False
_src_prefix = os.getenv('BUILD_STUFF_SRC_DIR') + "/"
_install_prefix = os.getenv('BUILD_STUFF_INSTALL_DIR') + "/"
_root_dir = os.getenv('BUILD_STUFF_ROOT_DIR') + "/"
_repos = {}
_patches = {}
_configure_only = False
_clean_only = False
_repo_groups = {}
_kits = {}
_toolchains = {}
_success = False
_kit = os.getenv('BUILD_STUFF_KIT')
_prefix = os.getenv('BUILD_STUFF_PREFIX')
_repo = ""
_branch = os.getenv('BUILD_STUFF_BRANCH')
_variantName = ""
_pull = False
_readWerrorFlags = True
_no_configure = False
_no_notify = False
_clean = True
_debug = os.getenv('BUILD_STUFF_IS_DEBUG') == "1"
_static = False
_post_messages = []
_notify_tool = ""
_docs = False
_nuke = False
_all = False
_nuked_paths = []
_completed_master_repos_setup = []
_timesForRepo = {}
_culprit = ""
_no_patches = False
_clazy = False
_build_tests = False
_distcc = False
_original_CXXFlags = "" # original CXX env variable

VALID_GENERATORS = ['configure', 'qmake', 'cmake']
VALID_REPO_TOOLS = ['git', 'bzr']
VALID_OPTIONS = ['--pull', '--variant-name', '--no-configure', '--no-notify', '--docs', '--configure-only', '--clean-only', '--nuke', '--static', '--tests', '--no-werror', '--clazy', '--no-patches', '--all', '--print', '--conf', '-config']
VALID_OSES = ['windows', 'linux', 'osx']

if os.getenv("BUILD_STUFF_MAKE_TOOL"):
    _default_make = os.getenv("BUILD_STUFF_MAKE_TOOL")

if _extra_config_opts is None:
    _extra_config_opts = ""

if _remove_config_opts is None:
    _remove_config_opts = ""

if _prefix is None:
    _prefix = _kit

def open_editor(filename):
    editor = os.getenv('BUILD_STUFF_EDITOR')
    if not editor:
        editor = 'kate'

    os.system(editor + " " + filename)

if '--config' in sys.argv or '--conf' in sys.argv:
    open_editor(_build_stuff_file)
    sys.exit(0)

if _branch is None:
    print "BUILD_STUFF_BRANCH isn't set"
    sys.exit(-1)

if _debug is None:
    _debug = False

if not _root_dir:
    print "BUILD_STUFF_ROOT_DIR isn't set"
    sys.exit(-1)

if not _build_stuff_build_dir:
    print "BUILD_STUFF_BUILD_DIR isn't set"
    sys.exit(-1)

if not _build_stuff_dir:
    print "BUILD_STUFF_DIR isn't set"
    sys.exit(-1)

if not _install_prefix:
    print "BUILD_STUFF_INSTALL_DIR isn't set"
    sys.exit(-1)

if not _src_prefix:
    print "BUILD_STUFF_SRC_DIR isn't set"
    sys.exit(-1)

if not _kit:
    print "BUILD_STUFF_KIT isn't set"
    sys.exit(-1)


def at_exit_handler():
    global _timesForRepo, _no_notify, _notify_tool, _tried_to_build, _culprit
    for m in _post_messages:
        print m

    for r in _timesForRepo:
        print "%s took %0.0f seconds" % (r, _timesForRepo[r])

    msg = ""
    if _success:
        msg = "Success!"
    else:
        msg = "Error!"
    print msg

    if not _no_notify and _tried_to_build:
        if _notify_tool:
            run_command(_notify_tool, False)
        else:
            print "No notify tool set"

    if _culprit:
        print "culprit: " + _culprit

atexit.register(at_exit_handler)

if not _build_stuff_file:
    print "Set env variable BUILD_STUFF_FILE, point it to your json file\n"
    sys.exit(-1)

class Repo:
    def __init__(self):
        self.name        = ""
        self.src_dir     = ""
        self.install_dir = ""
        self.tool        = ""
        self.werror_flags = ""
        self.generator   = ""
        self.prefix      = ""
        self.masterRepo  = ""
        self.env         = ""
        self.extra_args  = ""
        self.out_of_source = True
        self.build_tests = False
        self.branch_remapping = {}
        self.hide_from_hosts = []
        self.hidden = False
        self.has_submodules = False

class Config:
    def __init__(self):
        self.name        = ""
        self.disable_tests_argument = ""
        self.configures  = {} # indexed by host
        self.is_cross_compile = False

class Toolchain:
    def __init__(self):
        self.name     = ""
        self.qt_spec  = ""
        self.env_file = ""
        self.make = ""

def platform_name():
    plat = platform.system()
    if plat == "Linux":
        return "linux"
    elif plat == "Windows":
        return "windows"
    elif plat == "Darwin":
        return "osx"
    else:
        _post_messages.append("Unknown platform " + plat)
        sys.exit(-1)

def configures():
    configs = []
    for c in _kits:
        if platform_name() in _kits[c].configures:
            configs.append(c)

    return configs

def fancy_group_string(g):
    repos = _repo_groups[g]
    text = "["

    for r in repos:
        text += r
        if r != repos[-1]:
            text += ","

    text += "]"
    return text

def printUsage():
    print "Usage:"
    print sys.argv[0] + " <config> <repo|group> <branch> [--pull|--debug|--no-configure|--no-notify|--tests|--variantName]"
    print sys.argv[0] + " <repo|group> <branch> [--pull] # Executes these actions but doesn't build"

    print "Available configs:"
    configs = configures()
    for c in configs:
        print "    " + c

    print "\nAvailable repos:"
    plat_name = platform_name();
    for r in _repos:
        if plat_name not in _repos[r].hide_from_hosts:
            repo = _repos[r]
            if not repo.hidden:
                print "    " + r

    print "\nAvailable groups:"

    max_group_length = 0
    for g in _repo_groups:
        if len(g) > max_group_length:
            max_group_length = len(g)

    for g in _repo_groups:
        if g:
            print "    " + g.ljust(max_group_length) + " " + fancy_group_string(g)

    print
    _no_notify = True
    sys.exit(0)

def slash():
    if platform_name() == "windows":
        return "\\"
    return "/"

def normalize(path):
    slash_char = slash()
    if not path.endswith(slash_char):
        path += slash_char
    return path


def load_json_repo(json_file_name):
    f = open(_build_stuff_dir + "/" + json_file_name, 'r')
    contents = f.read()
    f.close()

    decoded = json.loads(contents)
    if 'repos' not in decoded:
        return

    hidden = False
    if 'hidden' in decoded:
        hidden = decoded['hidden']

    for repo in decoded['repos']:
        for mandatory_property in ['src_dir', 'name', 'tool', 'generator']:
            if mandatory_property not in repo:
                _post_messages.append("Missing " + mandatory_property + " property in json file")
                sys.exit(-1)
        r = Repo()
        r.name = repo['name']
        r.src_dir = repo['src_dir']
        if 'install_dir' in repo:
            r.install_dir = repo['install_dir']

        r.tool = repo['tool']
        r.generator = repo['generator']
        r.hidden = hidden

        if 'out_of_source' in repo:
            r.out_of_source = repo['out_of_source']
        elif platform_name() == "windows":
            r.out_of_source = False # not implemented on windows yet

        if 'build_tests' in repo:
            r.build_tests = repo['build_tests']

        if "env" in repo:
            r.env = repo["env"]

        if (r.generator == 'configure' or r.generator == 'cmake') and not r.install_dir:
            _post_messages.append("Missing install_dir for repo " + r.name)
            sys.exit(-1)

        if "prefix" in repo:
            r.prefix = repo["prefix"]

        if "has_submodules" in repo:
            r.has_submodules = repo["has_submodules"]

        if "extra_args" in repo:
            r.extra_args = repo["extra_args"]

        if "werror_flags" in repo:
            r.werror_flags = repo["werror_flags"]

        if "masterRepo" in repo:
            if r.prefix:
                _post_messages.append("repo " + r.name + " can't have both prefix and masterRepo")
                sys.exit(-1)
            r.masterRepo = repo["masterRepo"]
            if not _repos[r.masterRepo].prefix:
                _post_messages.append("master repo " + r.masterRepo + " doesn't have prefix")
                sys.exit(-1)

        if r.generator == "configure" and not r.prefix:
            _post_messages.append("Missing prefix for repo: " + r.name)
            sys.exit(-1)

        if "branch_remapping" in repo:
            r.branch_remapping = repo["branch_remapping"]

        if "hide_from_hosts" in repo:
            r.hide_from_hosts = repo["hide_from_hosts"]

        _repos[r.name] = r


def load_json_repos():
    json_files = os.listdir(_build_stuff_dir)
    for filename in json_files:
        if not filename.endswith(".json") or filename == "build_stuff.json":
            continue
        load_json_repo(filename)

def loadJson():
    f = open(_build_stuff_file, 'r')
    contents = f.read()
    f.close()

    global _src_prefix
    global _notify_tool
    global _build_stuff_build_dir

    decoded = json.loads(contents)
    for mandatory_property in ['configs', 'toolchains', 'default_make']:
        if mandatory_property not in decoded:
            _post_messages.append("Missing " + mandatory_property + " property in json file")
            sys.exit(-1)

    _default_make = decoded['default_make']

    if not _install_prefix:
        _post_messages.append("Invalid install_dir")
        sys.exit(-1)

    if "notify_tool" in decoded:
        if platform_name() in decoded["notify_tool"]:
            _notify_tool = decoded["notify_tool"][platform_name()]

    load_json_repos()

    for toolchain in decoded['toolchains']:
        for mandatory_property in ['name']:
            if mandatory_property not in toolchain:
                _post_messages.append("Missing " + mandatory_property + " property in json file")
                sys.exit(-1)
        t = Toolchain()
        t.name = toolchain["name"]
        if "qt_spec" in toolchain:
            t.qt_spec = toolchain["qt_spec"]
        if "env" in toolchain:
            t.env_file = toolchain["env"]
        if "make" in toolchain:
            t.make = toolchain["make"]

        _toolchains[t.name] = t

    for config in decoded['configs']:
        for mandatory_property in ['name', 'configure']:
            if mandatory_property not in config:
                _post_messages.append("Missing " + mandatory_property + " property in json file")
                sys.exit(-1)
        c = Config()
        c.name = config['name']

        if "disable_tests_argument" in config:
            c.disable_tests_argument = config['disable_tests_argument']

        if "is_cross_compile" in config:
            c.is_cross_compile = config['is_cross_compile']

        for conf in config['configure']:
            c.configures[conf["host"]] = conf["command"]

        _kits[c.name] = c

    for group in decoded['repo_groups']:
        for mandatory_property in ["name", "repos"]:
            if mandatory_property not in group:
                _post_messages.append("Missing " + mandatory_property + " property in json file")
                sys.exit(-1)
        for r in group["repos"]:
            if r not in _repos:
                _post_messages.append("Unknown repo " + r)
                sys.exit(-1)
        _repo_groups[group["name"]] = group["repos"]

    if "patches" in decoded:
        for p in decoded["patches"]:
            if p not in _repos:
                _post_messages.append("Repo " + p + " is unknown")
                sys.exit(-1)
            _patches[p] = decoded["patches"][p]

def shell_script_suffix():
    if platform_name() == 'windows':
        return ".bat"
    else:
        return ".source"

def replace_env_variable(text, variable_name):
    value = os.getenv(variable_name)
    if value:
        return text.replace("$" + variable_name, value)
    return text


def replace_variables(config, text):
    c = _kits[config]
    if _debug:
        text = text.replace("$isDebug", "d")
    else:
        text = text.replace("$isDebug", "")

    if _static:
        text = text.replace("$isStatic", "s")
    else:
        text = text.replace("$isStatic", "")

    if _variantName:
        text = text.replace("$variant", "_" + _variantName)
    else:
        text = text.replace("$variant", "")

    text = text.replace("$branch", _branch)
    text = text.replace("$config", c.name)
    text = text.replace("$root", _root_dir)
    text = text.replace("$prefix", _prefix)
    text = text.replace("$shellScriptSuffix", shell_script_suffix())
    return text

def install_prefix(config, repo):
    c = _kits[config]
    r = _repos[repo]
    prefix = r.prefix
    prefix = replace_variables(config, prefix)

    return prefix

def parseCommandLine():
    if len(sys.argv) < 2:
        _post_messages.append("Arg count is less than 3")
        printUsage()

    global _repo, _kit, _pull, _clean, _debug, _branch, _variantName, _no_configure, _docs, _configure_only, _clean_only,  _nuke, _static, _build_tests, _readWerrorFlags, _clazy, _no_patches, _all, _distcc, _print_only

    arguments = sys.argv[1:] # exclude file name

    _repo = sys.argv[1]

    if not _repo:
        _post_messages.append("You must specify a valid repo name!\n")
        printUsage();

    if "," in _repo:
        repos = _repo.split(",")
        for r in repos:
            if r not in _repos:
                _post_messages.append("Invalid repo: " + r)
                printUsage();
    else:
        if _repo not in _repos and _repo not in _repo_groups:
            _post_messages.append("Invalid repo: " + _repo)
            printUsage();

    _no_patches = "--no-patches" in sys.argv
    _clazy = "--clazy" in sys.argv
    _distcc = "--distcc" in sys.argv
    _pull  = "--pull" in sys.argv
    _build_tests = "--tests" in sys.argv
    _no_configure = "--no-configure" in sys.argv
    _configure_only = "--configure-only" in sys.argv
    _all = "--all" in sys.argv
    _clean_only = "--clean-only" in sys.argv
    _no_notify = "--no-notify" in sys.argv
    _docs = "--docs" in sys.argv
    _nuke = "--nuke" in sys.argv
    _static = "--static" in sys.argv
    _print_only = "--print" in sys.argv
    _readWerrorFlags = "--no-werror" not in sys.argv

    if '--variantName' in arguments:
        variantNameIndex =  arguments.index('--variantName')
        if len(arguments) > variantNameIndex + 1:
            _variantName = arguments[variantNameIndex + 1]
            del arguments[variantNameIndex + 1]
            del arguments[variantNameIndex]
        else:
            _post_messages.append("--variantName needs an argument")
            sys.exit(-1)

    if _clean and _no_configure:
        _post_messages.append("clean is incompatible with --no-configure\nThe later allows you to run only make/make install, which won't work if you clean")
        sys.exit(-1)

    if _configure_only and _no_configure:
        _post_messages.append("--configure-only is incompatible with --no-configure")
        sys.exit(-1)

    if _configure_only and _clean_only:
        _post_messages.append("--configure-only is incompatible with --clean-only")
        sys.exit(-1)

    if _all and not _clean_only:
        _post_messages.append("--all must be used with --clean-only")
        sys.exit(-1)

    if _distcc and _clazy:
        _post_messages.append("--distcc is incompatible with --clazy")
        sys.exit(-1)

    for option in sys.argv:
        if option in VALID_OPTIONS:
            arguments.remove(option)

    arguments.remove(_repo)
    if not _kit in configures():
        _post_messages.append("Invalid kit: " + _kit)
        sys.exit(-1)

    if arguments:
        _post_messages.append("Invalid extra arguments: " + string.join(arguments))
        printUsage()

def tmp_dir():
    if platform_name() == "windows":
        return os.getenv('TEMP') + "\\"
    else:
        return "/tmp/"

def log_command(command, print_command = False):
    if print_command:
        print command
    os.system('echo ' + command + ' >> ' + tmp_dir() + "command.log")

def build_dir(repo):
    r = _repos[repo]
    if r.out_of_source:
        return shadow_build_dir(repo)
    return src_dir(repo)

def change_dir(directory):
    if os.getcwd() == directory:
        return True;

    command = "[" + os.getcwd() + "] $] " + 'cd ' + directory
    log_command(command, False)
    success = True
    try:
        os.chdir(directory)
    except:
        success = False
    if not success:
        _post_messages.append("Failed to change directory to " + directory)
        sys.exit(-1)
    return success

def shadow_build_dir(repo):
    return _build_stuff_build_dir + "/" + _repos[repo].src_dir

def src_dir(repo):
    directory =  _src_prefix + _repos[repo].src_dir
    if not os.path.exists(directory):
        _post_messages.append("Directory doesn't exist: " + directory)
        sys.exit(-1)
    if not os.path.isdir(directory):
        _post_messages.append("Path isn't a directory: " + directory)
        sys.exit(-1)

    return directory

def run_command(command, silent = False, logfile = ""):
    out = ""
    print "[" + os.getcwd() + "] $] " + command
    if _print_only:
        return True
    log_command(command)
    if silent:
        if logfile:
            logfile = tmp_dir() + logfile
            _post_messages.append("Log at " + logfile)
            if platform_name() == "windows":
                out = "> " + logfile
            else:
                out = "&> " + logfile

    command += " " + out

    success = 0 == os.system(command)
    if not success:
        print "Error running command: " + command
    return success

def git_clean(repo):
    change_dir(src_dir(repo))
    r = _repos[repo]
    if r.has_submodules and not run_command("git submodule foreach git clean -fdx", True):
        return False
    if not run_command("git clean -fdx", True, "git-clean-" + repo + ".log"):
        return False
    if not run_command("git checkout ."):
        return False

    return True

def bzr_clean(repo):
    change_dir(src_dir(repo))
    if not run_command("bzr clean-tree --force", True, "bzr-clean-" + repo + ".log"):
        return False

    return True

def apply_patches(repo):
    if repo in _patches:
        branch = real_branch(repo, _branch)
        if branch in _patches[repo]:
            change_dir(src_dir(repo))
            patches = _patches[repo][branch]
            for p in patches:
                if not p:
                    continue
                if not _clean and not run_command("git checkout ."):
                    _post_messages.append("!! Error running git checkout . in " + src_dir(repo))
                    sys.exit(-1)
                if not run_command("git apply " + _root_dir + "/windows-linux-shared/" + p, True):
                    _post_messages.append("!! Error applying patch " + p + "; in=" + src_dir(repo))
                    sys.exit(-1)

    return True

def real_branch(repo, fakeBranch):
    r = _repos[repo]
    if fakeBranch in r.branch_remapping:
        return r.branch_remapping[fakeBranch]
    return fakeBranch

def git_checkout(repo):
    change_dir(src_dir(repo))
    return run_command("git checkout " + real_branch(repo, _branch), True, "git-checkout-" + repo + ".log")

def git_pull(repo):
    change_dir(src_dir(repo))
    return run_command("git pull", True, "git-pull-" + repo + ".log")

def git_fetch(repo):
    change_dir(src_dir(repo))
    return run_command("git fetch origin", True, "git-fetch-" + repo + ".log")

def bzr_pull(repo):
    change_dir(src_dir(repo))
    return run_command("bzr pull", True, "bzr-pull-" + repo + ".log")

def checkout(repo):
    r = _repos[repo]
    if r.tool == "git":
        return git_checkout(repo)
    elif r.tool == "bzr":
        pass
    else:
        print "Unimplemented tool: " + r.tool
        sys.exit(-1)

    return True

def clean_shadow_build_dir(repo):
    r = _repos[repo]
    if r.out_of_source:
        d = build_dir(repo) + "/*"
        if "data/build" not in d: # Safety so we don't rm -rf something else
            print "Refusing to rm -rf: " + d
            return False
        return run_command("rm -rf " + d, True)
    return True

def clean(repo):
    r = _repos[repo]

    if not clean_shadow_build_dir(repo):
        return False

    if r.tool == "git":
        return git_clean(repo)
    elif r.tool == "bzr":
        return bzr_clean(repo)
    else:
        print "Unimplemented tool: " + r.tool
        sys.exit(-1)

    return True

def pull(repo):
    r = _repos[repo]
    if r.tool == "git":
        return git_pull(repo)
    elif r.tool == "bzr":
        return bzr_pull(repo)
    else:
        _post_messages.append("Unimplemented tool: " + r.tool)
        sys.exit(-1)

    return True

def source(filename):
    print "[" + os.getcwd() + "] $] Sourcing " + filename
    if not os.path.exists(filename):
        _post_messages.append("File does not exist: " + filename)
        sys.exit(-1)

    command = ""

    if platform_name() == "windows":
        command = ['cmd', '/C', filename + ' && set']
    else:
        command = ['bash', '-c', 'source ' + filename + ' && env']

    # print "Sourcing " + filename
    proc = subprocess.Popen(command, stdout = subprocess.PIPE)

    for line in proc.stdout:
        (key, _, value) = line.partition("=")
        os.environ[key] = value.strip()
    proc.communicate()

def path_char():
    if platform_name() == "windows":
        return ";"
    return ":"

def complete_install_prefix(config, repo):
    r = _repos[repo]
    return _install_prefix + normalize(r.install_dir) + install_prefix(config, repo)

def nuke_install(config, repo):
    global _nuked_paths
    path = complete_install_prefix(config, repo)
    if path not in _nuked_paths:
        _nuked_paths.append(path)
        if platform_name() == "linux" or platform_name() == "osx":
            print "Would run rm -rf " + path
            assert(False)
            # run_command("rm -rf " + path, True)
        else:
            print "Not implemented for windows yet"
            assert(False)

def setup_path(config, repo):
    r = _repos[repo]
    if r.masterRepo and r.masterRepo not in _completed_master_repos_setup:
        pathToAdd = complete_install_prefix(config, r.masterRepo) + slash() + "bin" + path_char()
        os.environ["PATH"] = pathToAdd + os.environ["PATH"]
        _completed_master_repos_setup.append(r.masterRepo)

def remove_opts_from_configure(command):
    splitted_rm = _remove_config_opts.split(" ")
    splitted = command.split(" ")

    for opt in splitted_rm:
        try:
            splitted.remove(opt)
        except:
            print opt

    return string.join(splitted)

def configure_command(config, repo):
    c = _kits[config]
    r = _repos[repo]
    command = c.configures[platform_name()]
    command = remove_opts_from_configure(command)

    if _debug:
        command += " -debug "
    else:
        command += " -release "

    if _static:
        command += " -static"

    masterRepo = repo
    if r.masterRepo:
        masterRepo = r.masterRepo

    prefix = complete_install_prefix(config, masterRepo)
    command += " -prefix " + prefix
    if c.is_cross_compile:
        command += " -extprefix " + prefix

    if r.out_of_source:
        command = src_dir(repo) + "/" + command

    command = command.replace('$EXTRA_CONFIGURE_OPTS', _extra_config_opts)
    command = replace_env_variable(command, "ANDROID_NDK")
    command = replace_env_variable(command, "ANDROID_SDK")


    return command

def cmake_command(config, repo):
    c = _kits[config]
    r = _repos[repo]
    command = "cmake . "
    if r.out_of_source:
        command = "cmake " + src_dir(repo) + " "

    if _debug:
        command += "-DCMAKE_BUILD_TYPE=Debug"
    else:
        command += "-DCMAKE_BUILD_TYPE=RELWITHDEBINFO"

    masterRepo = repo
    if r.masterRepo:
        masterRepo = r.masterRepo

    prefix = complete_install_prefix(config, masterRepo)
    command += " -DCMAKE_INSTALL_PREFIX=" + prefix

    if make_tool(config, repo) == "jom":
        command += ' -G "NMake Makefiles JOM"'
    if make_tool(config, repo) == "nmake":
        command += ' -G "NMake Makefiles"'

    command += " -DCMAKE_EXPORT_COMPILE_COMMANDS=ON"
    command += " " + r.extra_args

    if c.disable_tests_argument and not (r.build_tests or _build_tests):
        command += " " + c.disable_tests_argument

    # print "Running cmake. CXX=" + os.environ['CXX']
    return command

def configure(config, repo):
    r = _repos[repo]

    bld_dir = build_dir(repo)

    if not os.path.exists(bld_dir):
        os.makedirs(bld_dir)

    change_dir(bld_dir)

    if r.generator == 'qmake':
        qmake_cmd = 'qmake ' + src_dir(repo) + " " + r.extra_args
        if not run_command(qmake_cmd):
            sys.exit(-1)
    elif r.generator == 'configure':
        if not run_command(configure_command(config, repo), True, "configure-" + repo + ".log"):
            sys.exit(-1)
    elif r.generator == 'cmake':
        if not run_command(cmake_command(config, repo), True, "cmake-" + repo + ".log"):
            sys.exit(-1)
    else:
        _post_messages.append("Unimplemented generator: " + r.generator)
        sys.exit(-1)

    return True

def make_tool(config, repo):
    return _default_make

def apply_CXX_flags(r):
    global _original_CXXFlags
    os.environ['CXXFLAGS'] = _original_CXXFlags
    if _readWerrorFlags and r.werror_flags and _branch == 'master': # Hack, master only, since I didn't fix the warnings in other branches
        os.environ['CXXFLAGS'] = _original_CXXFlags + " " + r.werror_flags

def build(config, repo):
    global _docs
    change_dir(build_dir(repo))
    r = _repos[repo]
    make = make_tool(config, repo)

    if not run_command(make, True, "make-" + repo + ".log"):
        sys.exit(-1)
    if not run_command(make + " install", True, "install-" + repo + ".log"):
        sys.exit(-1)

    if _docs:
         if not run_command(make + " docs", True, "docs-" + repo + ".log"):
             sys.exit(-1)
         if not run_command(make + " install_docs", True, "install_docs-" + repo + ".log"):
             sys.exit(-1)

    return True

if "CXXFLAGS" in os.environ:
    _original_CXXFlags = os.environ['CXXFLAGS']

loadJson()
parseCommandLine()

if _all:
    requested_repos = _repos.keys()
else:
    requested_repos = _repo.split(",")

repos = []


for r in requested_repos:
    if r in _repos:
        repos.append(r)
    elif r in _repo_groups:
        repos += _repo_groups[r]
    else: # TODO por recursivo
        _post_messages.append("Unknown repo " + r)
        sys.exit(-1)

for r in repos:
    if _clean or _clean_only:
        if not clean(r):
            sys.exit(-1)

if _clean_only:
    _success = True
    sys.exit(0)

for r in repos:
    uses_git = _repos[r].tool == "git"
    if _pull:
        if uses_git and _branch != 'master' and not git_fetch(r): # // Fetch before checkout, in case there are new branches in the remote
            sys.exit(-1)

    if not checkout(r):
        sys.exit(-1)

if _pull:
    for r in repos:
        if not pull(r):
            sys.exit(-1)

os.environ['VERBOSE'] = '1'
os.environ['CONTAINER_STATS_DISABLED'] = '1'

_tried_to_build = True
for r in repos:
    startTime = time.time()

    if _nuke:
        nuke_install(_kit, r)

    setup_path(_kit, r)
    repo = _repos[r]

    if repo.env:
        source(replace_variables(_kit, repo.env))

    apply_CXX_flags(repo)
    if False and not _no_patches:
        apply_patches(r)
    if not _no_configure and not configure(_kit, r):
        sys.exit(-1)

    if not _configure_only:
        if not build(_kit, r):
            _culprit = r
            sys.exit(-1)
    elapsedTime = time.time() - startTime
    _timesForRepo[r] = elapsedTime

_success = True

sys.exit(0)
