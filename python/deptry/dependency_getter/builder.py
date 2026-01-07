from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from deptry.dependency_getter.pep621.base import PEP621DependencyGetter
from deptry.dependency_getter.pep621.pdm import PDMDependencyGetter
from deptry.dependency_getter.pep621.poetry import PoetryDependencyGetter
from deptry.dependency_getter.pep621.uv import UvDependencyGetter
from deptry.dependency_getter.requirements_files import RequirementsTxtDependencyGetter
from deptry.exceptions import DependencySpecificationNotFoundError
from deptry.utils import load_pyproject_toml

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from deptry.dependency_getter.base import DependencyGetter


@dataclass
class DependencyGetterBuilder:
    """
    Class to detect how dependencies are specified, in this specific order:
    - pyproject.toml found, with a [tool.poetry] section
    - pyproject.toml found, with a [tool.uv.dev-dependencies] section
    - pyproject.toml found, with a [tool.pdm.dev-dependencies] section
    - pyproject.toml found, with a [project] section
    - requirements.txt found
    """

    config: Path
    package_module_name_map: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    optional_dependencies_dev_groups: tuple[str, ...] = ()
    requirements_files: tuple[str, ...] = ()
    using_default_requirements_files: bool = True
    requirements_files_dev: tuple[str, ...] = ()

    def build(self) -> DependencyGetter:
        pyproject_toml_found = self._project_contains_pyproject_toml()

        if pyproject_toml_found:
            pyproject_toml = load_pyproject_toml(self.config)

            if self._project_uses_poetry(pyproject_toml):
                return PoetryDependencyGetter(
                    self.config, self.package_module_name_map, self.optional_dependencies_dev_groups
                )

            # Check if this is a UV project OR if we're in a UV workspace
            if self._project_uses_uv(pyproject_toml) or self._project_is_in_uv_workspace():
                return UvDependencyGetter(
                    self.config, self.package_module_name_map, self.optional_dependencies_dev_groups
                )

            if self._project_uses_pdm(pyproject_toml):
                return PDMDependencyGetter(
                    self.config, self.package_module_name_map, self.optional_dependencies_dev_groups
                )

            if self._project_uses_pep_621(pyproject_toml):
                return PEP621DependencyGetter(
                    self.config, self.package_module_name_map, self.optional_dependencies_dev_groups
                )

        check, requirements_files = self._project_uses_requirements_files()
        if check:
            return RequirementsTxtDependencyGetter(
                self.config, self.package_module_name_map, requirements_files, self.requirements_files_dev
            )

        raise DependencySpecificationNotFoundError(self.requirements_files)

    def _project_contains_pyproject_toml(self) -> bool:
        if self.config.exists():
            logging.debug("pyproject.toml found!")
            return True
        else:
            logging.debug("No pyproject.toml found.")
            return False

    @staticmethod
    def _project_uses_poetry(pyproject_toml: dict[str, Any]) -> bool:
        try:
            pyproject_toml["tool"]["poetry"]
            logging.debug(
                "pyproject.toml contains a [tool.poetry] section, so Poetry is used to specify the"
                " project's dependencies."
            )
        except KeyError:
            logging.debug(
                "pyproject.toml does not contain a [tool.poetry] section, so Poetry is not used to specify"
                " the project's dependencies."
            )
            return False
        else:
            return True

    @staticmethod
    def _project_uses_pdm(pyproject_toml: dict[str, Any]) -> bool:
        try:
            pyproject_toml["tool"]["pdm"]["dev-dependencies"]
            logging.debug(
                "pyproject.toml contains a [tool.pdm.dev-dependencies] section, so PDM is used to specify the project's"
                " dependencies."
            )
        except KeyError:
            logging.debug(
                "pyproject.toml does not contain a [tool.pdm.dev-dependencies] section, so PDM is not used to specify"
                " the project's dependencies."
            )
            return False
        else:
            return True

    @staticmethod
    def _project_uses_uv(pyproject_toml: dict[str, Any]) -> bool:
        """
        Check if the project uses UV for dependency management.

        UV projects can be detected by:
        - Having [tool.uv.dev-dependencies]
        - Having [tool.uv.sources] (workspace packages)
        - Having [tool.uv.workspace] (workspace root)
        - Having [tool.uv] section in general
        """
        try:
            uv_config = pyproject_toml["tool"]["uv"]

            # Check for any UV-specific configuration
            has_dev_deps = "dev-dependencies" in uv_config
            has_sources = "sources" in uv_config
            has_workspace = "workspace" in uv_config

            if has_dev_deps or has_sources or has_workspace:
                logging.debug(
                    "pyproject.toml contains [tool.uv] configuration (dev-dependencies=%s, sources=%s, workspace=%s), "
                    "so uv is used to specify the project's dependencies.",
                    has_dev_deps,
                    has_sources,
                    has_workspace,
                )
                return True
        except KeyError:
            pass

        logging.debug(
            "pyproject.toml does not contain [tool.uv] configuration, so uv is not used to specify the"
            " project's dependencies."
        )
        return False

    def _project_is_in_uv_workspace(self) -> bool:
        """
        Check if this project is a member of a UV workspace by looking for a
        workspace root in parent directories.

        Returns True if a parent directory contains a pyproject.toml with
        [tool.uv.workspace] section.
        """
        current_path = self.config.parent
        for parent in current_path.parents:
            parent_pyproject = parent / "pyproject.toml"
            if parent_pyproject.exists():
                try:
                    parent_data = load_pyproject_toml(parent_pyproject)
                    if "tool" in parent_data and "uv" in parent_data["tool"] and "workspace" in parent_data["tool"]["uv"]:
                        logging.debug(
                            "Found UV workspace root at %s, treating this project as a UV workspace member",
                            parent
                        )
                        return True
                except Exception as e:
                    logging.debug("Could not read parent pyproject.toml at %s: %s", parent_pyproject, e)
                    continue
        return False

    @staticmethod
    def _project_uses_pep_621(pyproject_toml: dict[str, Any]) -> bool:
        if pyproject_toml.get("project"):
            logging.debug(
                "pyproject.toml contains a [project] section, so PEP 621 is used to specify the project's dependencies."
            )
            return True

        logging.debug(
            "pyproject.toml does not contain a [project] section, so PEP 621 is not used to specify the project's"
            " dependencies."
        )
        return False

    def _project_uses_requirements_files(self) -> tuple[bool, tuple[str, ...]]:
        """
        Tools like `pip-tools` and `uv` work with a setup in which a `requirements.in` is compiled into a `requirements.txt`, which then
        contains pinned versions for all transitive dependencies. If the user did not explicitly specify the argument `requirements-files`,
        but there is a `requirements.in` present, it is highly likely that the user wants to use the `requirements.in` file so we set
        `requirements-files` to that instead.
        """
        if self.using_default_requirements_files and Path("requirements.in").is_file():
            logging.info(
                "Detected a 'requirements.in' file in the project and no 'requirements-files' were explicitly specified. "
                "Automatically using 'requirements.in' as the source for the project's dependencies. To specify a different source for "
                "the project's dependencies, use the '--requirements-files' option."
            )
            return True, ("requirements.in",)

        check = any(Path(requirements_files).is_file() for requirements_files in self.requirements_files)
        if check:
            logging.debug(
                "Dependency specification found in '%s'. Will use this to determine the project's dependencies.\n",
                ", ".join(self.requirements_files),
            )
            return True, self.requirements_files
        return False, ()
