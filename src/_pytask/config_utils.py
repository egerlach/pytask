"""Contains helper functions for the configuration."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from typing import Sequence

import click
from _pytask.shared import parse_paths

if sys.version_info >= (3, 11):  # pragma: no cover
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


__all__ = ["find_project_root_and_config", "read_config", "set_defaults_from_config"]


def set_defaults_from_config(
    context: click.Context,
    param: click.Parameter,  # noqa: ARG001
    value: Any,
) -> Path | None:
    """Set the defaults for the command-line interface from the configuration."""
    # pytask will later walk through all configuration hooks, even the ones not related
    # to this command. They might expect the defaults coming from their related
    # command-line options during parsing. Here, we add their defaults to the
    # configuration.
    command_option_names = [option.name for option in context.command.params]
    commands = context.parent.command.commands  # type: ignore[union-attr]
    all_defaults_from_cli = {
        option.name: option.default
        for name, command in commands.items()
        for option in command.params
        if name != context.info_name and option.name not in command_option_names
    }
    context.params.update(all_defaults_from_cli)

    if value:
        context.params["config"] = value
        context.params["root"] = context.params["config"].parent
    else:
        if not context.params["paths"]:
            context.params["paths"] = (Path.cwd(),)

        context.params["paths"] = parse_paths(context.params["paths"])
        (
            context.params["root"],
            context.params["config"],
        ) = find_project_root_and_config(context.params["paths"])

    if context.params["config"] is None:
        return None

    config_from_file = read_config(context.params["config"])

    if context.default_map is None:
        context.default_map = {}
    context.default_map.update(config_from_file)
    context.params.update(config_from_file)

    return context.params["config"]


def find_project_root_and_config(
    paths: Sequence[Path] | None,
) -> tuple[Path, Path | None]:
    """Find the project root and configuration file from a list of paths.

    The process is as follows:

    1. Find the common base directory of all paths passed to pytask (default to the
       current working directory).
    2. Starting from this directory, look at all parent directories, and return the file
       if it is found.
    3. If a directory contains a ``.git`` directory/file, or the ``pyproject.toml``
       file, stop searching.

    """
    try:
        common_ancestor = Path(os.path.commonpath(paths))  # type: ignore[arg-type]
    except ValueError:
        common_ancestor = Path.cwd()

    if common_ancestor.is_file():
        common_ancestor = common_ancestor.parent

    config_path = None
    root = None
    parent_directories = [common_ancestor, *list(common_ancestor.parents)]

    for parent in parent_directories:
        path = parent.joinpath("pyproject.toml")

        if path.exists():
            try:
                read_config(path)
            except (tomllib.TOMLDecodeError, OSError) as e:  # pragma: no cover
                raise click.FileError(
                    filename=str(path), hint=f"Error reading {path}:\n{e}"
                ) from None
            except KeyError:
                pass
            else:
                config_path = path
                root = config_path.parent
                break

        # If you hit a the top of a repository, stop searching further.
        if parent.joinpath(".git").exists():
            root = parent
            break

    if root is None:
        root = common_ancestor

    return root, config_path


def read_config(
    path: Path, sections: str = "tool.pytask.ini_options"
) -> dict[str, Any]:
    """Read the configuration from a ``*.toml`` file.

    Raises
    ------
    tomllib.TOMLDecodeError
        Raised if ``*.toml`` could not be read.
    KeyError
        Raised if the specified sections do not exist.

    """
    sections_ = sections.split(".")

    config = tomllib.loads(path.read_text(encoding="utf-8"))

    for section in sections_:
        config = config[section]

    # Only convert paths when possible. Otherwise, we defer the error until the click
    # takes over.
    if (
        "paths" in config
        and isinstance(config["paths"], list)
        and all(isinstance(p, str) for p in config["paths"])
    ):
        config["paths"] = [path.parent.joinpath(p).resolve() for p in config["paths"]]

    return config
