#!/bin/bash

app=${0##*/}

# Don't run as root
if [[ ${EUID} == 0 ]]; then
    echo "DON'T run this script as root"
    echo "Aborting"
    exit 1
fi

# Require bash v4
if [[ ${BASH_VERSINFO} -lt 4 ]]; then
    echo "This script requires at least bash v4.0"
    echo "Aborting"
    exit 9
fi

if [[ ${1} == --noshortcut ]]; then
    shift
    createShortcut=
else
    createShortcut=1
fi

# Set colors
declare -A c
c[reset]='\033[0;0m'   c[BOLD]='\033[0;0m\033[1;1m'
c[dgrey]='\033[0;30m'  c[DGREY]='\033[1;30m'  c[bg_DGREY]='\033[40m'
c[red]='\033[0;31m'    c[RED]='\033[1;31m'    c[bg_RED]='\033[41m'
c[green]='\033[0;32m'  c[GREEN]='\033[1;32m'  c[bg_GREEN]='\033[42m'
c[orange]='\033[0;33m' c[ORANGE]='\033[1;33m' c[bg_ORANGE]='\033[43m'
c[blue]='\033[0;34m'   c[BLUE]='\033[1;34m'   c[bg_BLUE]='\033[44m'
c[purple]='\033[0;35m' c[PURPLE]='\033[1;35m' c[bg_PURPLE]='\033[45m'
c[cyan]='\033[0;36m'   c[CYAN]='\033[1;36m'   c[bg_CYAN]='\033[46m'
c[lgrey]='\033[0;37m'  c[LGREY]='\033[1;37m'  c[bg_LGREY]='\033[47m'

Print() {
    local color=${1}
    shift
    [[ -n ${color} ]] || color=null
    case "${color}" in
        S)  printf "${c[BOLD]}" ;;
        R)  printf "${c[RED]}" ;;
        r)  printf "${c[red]}" ;;
        G)  printf "${c[GREEN]}" ;;
        g)  printf "${c[green]}" ;;
        B)  printf "${c[BLUE]}" ;;
        b)  printf "${c[blue]}" ;;
        C)  printf "${c[CYAN]}" ;;
        c)  printf "${c[cyan]}" ;;
        O)  printf "${c[ORANGE]}" ;;
        o)  printf "${c[orange]}" ;;
        P)  printf "${c[PURPLE]}" ;;
        p)  printf "${c[purple]}" ;;
        0)  printf "${c[reset]}" ;;
        n)  : ;;
        null) printf "\n"; return ;;
        *)  printf "DEBUG: Print(): INVALID COLOR '${color}' SPECIFIED"
    esac
    if [[ -n ${@} ]]; then
        # Only print reset & newline if args specified
        printf "${@}${c[reset]}\n"
    fi
}

usage="Usage: ${app} [--noshortcut]
Installs all needed dependencies using dnf/yum (Fedora) & pip
Optionally creates a shortcut of ~/bin/ravshello when finished"

# Print help
if [[ ${1} == -h || ${1} == --help ]]; then
    Print n "${usage}"
    exit
else
    Print b "${usage}"
fi

# Check python version
declare -A pyVers
pyVers[major]=$( python -c 'import sys; print(sys.version_info[0])' )
pyVers[minor]=$( python -c 'import sys; print(sys.version_info[1])' )
pyVers[micro]=$( python -c 'import sys; print(sys.version_info[2])' )
[[ ${pyVers[major]} == 2 && ${pyVers[minor]} == 7 ]] \
    || { Print R "Error: Python 2.7 required"; exit 8; }

# Should we use dnf or yum?
if command -v dnf; then
    yum="dnf"
elif command -v yum; then
    yum="yum"
else
    Print R "Error: Neither dnf nor yum are present" >&2
    Print o "Aborting" >&2
fi >/dev/null

# Make sure we're in the right place
if [[ ! -r ./ravshello.py ]]; then
    Print R "Error: ${app} must be run from within the cloned ravshello source tree"
    exit 1
fi

# Where to place the runtime version
dir=~/.local/share/ravshello
if [[ -d ${dir} ]]; then
    Print o "Notice: application dir (${dir}) already exists; wiping it"
    rm -rf ${dir}
fi
mkdir -p ${dir}

continue_or_quit() {
    if [[ ${1} == yumcheck ]]; then
        [[ -n ${yum} ]] && return 0
        Print R "Neither yum nor dnf appear to be available"
        [[ -n ${2} ]] && Print r "You'll need to install '${2}' on your own"
    elif [[ ${1} == failedinstall ]]; then
        local j=
        [[ -n ${2} ]] && j="of '${2}' "
        Print R "Error: Installation ${j}appeared to fail"
    else
        Print R "${@}"
    fi
    read -ep "Continue in spite of this (Enter) or abort (q)? [Y|q] "
    [[ ${REPLY} == q ]] && exit 5
    return 1
}

# List of Fedora rpm names we need
reqdRpms="python-pip PyYAML python-dateutil pyparsing python-urwid"
[[ ${pyVers[micro]} -lt 9 ]] && reqdRpms+=" pyOpenSSL python-pyasn1-modules python-ndg_httpsclient"
rpmList=
for rpm in ${reqdRpms}; do
    rpm -q ${rpm} >/dev/null || rpmList+="${rpm} "
done

if [[ -n ${rpmList} ]]; then
    # Check for missing packages and offer to install them
    Print C "\nThe following packages are required and must be installed\nNote for RHEL7: EPEL and optional channels needed"
    Print S "  ${rpmList}\n"
    continue_or_quit yumcheck
    if ! sudo ${yum} install ${rpmList}; then
        continue_or_quit failedinstall
    fi
    Print
fi

pipNames="requests"
# The requests module doesn't have dependencies to speak of AND we want the latest version
# So let's send it straight to our target dir whether it's already installed or not
Print C "\nUsing pip to install the following modules directly to ${dir}/"
Print S "  ${pipNames}\n"
Print b
if pip install -t ${dir} ${pipNames}; then
    Print 0
else
    continue_or_quit "Warning: pip install failed"
fi

Print C "\nDownloading rsaw's stable fork of ravello_sdk"
Print b
curl -o ${dir}/ravello_sdk.py https://raw.githubusercontent.com/ryran/python-sdk/ravshello-stable/lib/ravello_sdk.py
Print 0

Print C "\nDownloading rsaw's stable + modified fork of configshell_fb"
Print b
git clone https://github.com/ryran/configshell-fb.git ${dir}/rsaw-configshell-fb
ln -s rsaw-configshell-fb/configshell_fb ${dir}/configshell_fb
Print 0

Print C "\nCopying source from CWD"
cp -a * ${dir}

Print G "\nDONE WITH DEPENDENCY RESOLUTION!\n"

if [[ -n ${createShortcut} ]]; then
    Print C "Creating an executable '~/bin/ravshello' symlink"
    mkdir -p ~/bin
    ln -svf ${dir}/ravshello.py ~/bin/ravshello
else
    Print C "Skipping creation of '~/bin/ravshello' symlink"
    Print n "You can execute ${dir}/ravshello.py directly"
fi
    
Print P "\nNote: any time you pull updates to the ravshello git repo, you should re-run this script"
