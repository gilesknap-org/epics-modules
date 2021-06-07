"""
Provide a basic CLI for managing a set of EPICS support modules
"""

import os
import re
import subprocess
from pathlib import Path

import click

# note requirement for enviroment variable EPICS_BASE
EPICS_BASE = Path(str(os.getenv("EPICS_BASE")))
EPICS_ROOT = EPICS_BASE.parent
# all support modules will reside under this directory
SUPPORT = Path(f"{EPICS_ROOT}/support/")
# the global RELEASE file which lists all support modules
RELEASE = Path(f"{SUPPORT}/configure/RELEASE")
# global MODULES file used to determine order of build
MODULES = Path(f"{SUPPORT}/configure/MODULES")

PARSE_MACROS = re.compile(r"^([A-Z_a-z0-9]*)\s*=\s*(.*)$", flags=re.M)


@click.group(invoke_without_command=True)
@click.version_option()
@click.pass_context
def cli(ctx):
    """command line interface functions for epics support module management"""

    # if no command is supplied, print the help message
    if ctx.invoked_subcommand is None:
        click.echo(cli.get_help(ctx))


@cli.command()
@click.argument("organization")
@click.argument("module")
@click.argument("macro")
@click.argument("tag")
@click.argument("server", required=False)
def add(
    organization: str,
    module: str,
    macro: str,
    tag: str,
    server: str,
):
    """
    pull a support module from a repo and add it to the global dependencies
    list in EPICS_BASE/configure/RELEASE

    arguments:

        server:       defaults to github, can be replaced with url of any git server

        organization: organization where the module resides

        module:       module name of the epics support module

        macro:        the name used to refer to this module in configure/RELEASE

        tag:          the git tag of the specific version to pull
    """
    server = server or "github.com"
    dash_tag = tag.replace(".", "-")
    sub_folder = f"{SUPPORT}/{module}-{dash_tag}"

    git_args = (
        f"git clone -q --branch {tag} --depth 1 "
        f"https://{server}/{organization}/{module}.git {sub_folder}"
    )
    print(git_args)

    git_args = git_args.split(" ")
    process = subprocess.run(git_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    if process.returncode != 0:
        raise RuntimeError(process.stdout)

    with RELEASE.open("a") as stream:
        stream.write(f"{macro}=$(SUPPORT)/{module}-{dash_tag}\n")


@cli.command()
@click.argument("url")
@click.argument("module")
@click.argument("macro")
@click.argument("tag")
def add_tar(
    url: str,
    module,
    macro: str,
    tag: str,
):
    """
    pull a tarred support module from a repo and add it to the global
    dependencies list in EPICS_BASE/configure/RELEASE

    arguments:

        url:    url to a tar file

        module: module name of the epics support module

        macro:  the name used to refer to this module in configure/RELEASE

        tag:    the git tag of the specific version to pull
    """
    dash_tag = tag.replace(".", "-")
    sub_folder = f"{SUPPORT}/{module}-{dash_tag}"
    url = url.format(TAG=tag)

    wget_args = f"wget {url}"
    print(wget_args)
    p = subprocess.run(
        wget_args.split(" "), stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if p.returncode != 0:
        raise RuntimeError(p.stdout)

    tar_file = url.split("/")[-1]
    tar_args = f"tar zxf {tar_file}"
    print(tar_args)
    p = subprocess.run(
        tar_args.split(" "), stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if p.returncode != 0:
        raise RuntimeError(p.stdout)

    new_folder = Path(tar_file[0:tar_file.find(".tar")])
    Path(tar_file).unlink()
    new_folder.rename(sub_folder)

    with RELEASE.open("a") as stream:
        stream.write(f"{macro}=$(SUPPORT)/{module}-{dash_tag}\n")


@cli.command()
def init():
    """
    bootstrap dependency management by creating EPICS_ROOT/support/configure/RELEASE
    to include macros defining the location of EPICS_BASE and SUPPORT
    """
    if not RELEASE.parent.exists():
        RELEASE.parent.mkdir()

    header = f"""
SUPPORT={SUPPORT}
-include $(TOP)/configure/SUPPORT.$(EPICS_HOST_ARCH)
EPICS_BASE={EPICS_BASE}
-include $(TOP)/configure/EPICS_BASE
-include $(TOP)/configure/EPICS_BASE.$(EPICS_HOST_ARCH)
"""
    RELEASE.write_text(header)

    print(f"created {RELEASE}")


@cli.command()
def dependencies():
    """
    update the dependecies of all support modules so that they are all
    consistent within EPICS_ROOT/support
    """

    # parse the global release file
    versions = {}
    text = RELEASE.read_text()
    for match in PARSE_MACROS.findall(text):
        versions[match[0]] = match[1]

    # find all the configure folders
    configure_folders = SUPPORT.glob("*/configure")
    for configure in configure_folders:
        release_files = configure.glob("RELEASE*")
        # iterate over all release files
        for rel in release_files:
            orig_text = text = rel.read_text()
            # find any occurences of global macros and replace with global value
            for macro, val in versions.items():
                replace = re.compile(f"^({macro}*\\s*=[ \t]*)(.*)$", flags=re.M)
                text = replace.sub(r"\1" + val, text)
            if orig_text != text:
                print(f"updating {rel}")
                rel.write_text(text)

    # generate the MODULES file for inclusion into the root Makefile
    # it simply defines a variable to hold each of the support module
    # directories in the order they are presented in RELEASE, except that
    # the IOC is always listed last if present.
    s = "$(SUPPORT)/"
    modules = [module[len(s):] for module in versions.values() if module.startswith(s)]
    if "IOC" in versions:
        modules.append(versions["IOC"])
    modlist = f'MODULES := {" ".join(modules)}\n'
    MODULES.write_text(modlist)


if __name__ == "__main__":
    cli()
    # for quick debugging of e.g. dependencies function change to:
    # cli(["dependencies"])
