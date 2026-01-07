from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from deptry.dependency_getter.pep621.base import PEP621DependencyGetter
from deptry.utils import load_pyproject_toml

if TYPE_CHECKING:
    from deptry.dependency import Dependency


@dataclass
class UvDependencyGetter(PEP621DependencyGetter):
    """
    Class to get dependencies that are specified according to PEP 621 from a `pyproject.toml` file for a project that
    uses uv for its dependency management.

    This class adds support for UV workspaces by:
    1. Reading [tool.uv.sources] to find workspace packages
    2. Looking for workspace root with [tool.uv.workspace]
    3. Extracting all workspace members
    """

    def _get_dev_dependencies(
        self,
        dependency_groups_dependencies: dict[str, list[Dependency]],
        dev_dependencies_from_optional: list[Dependency],
    ) -> list[Dependency]:
        """
        Retrieve dev dependencies from pyproject.toml, which in uv are specified as:

        [tool.uv]
        dev-dependencies = [
            "pytest==8.3.2",
            "pytest-cov==5.0.0",
            "tox",
        ]

        Dev dependencies marked as such from optional dependencies are also added to the list of dev dependencies found.
        """
        dev_dependencies = super()._get_dev_dependencies(dependency_groups_dependencies, dev_dependencies_from_optional)

        pyproject_data = load_pyproject_toml(self.config)

        dev_dependency_strings: list[str] = []
        try:
            dev_dependency_strings = pyproject_data["tool"]["uv"]["dev-dependencies"]
        except KeyError:
            logging.debug("No section [tool.uv.dev-dependencies] found in pyproject.toml")

        return [*dev_dependencies, *self._extract_pep_508_dependencies(dev_dependency_strings)]

    def _get_workspace_packages(self) -> set[str]:
        """
        Extract workspace packages from [tool.uv.sources] and [tool.uv.workspace].

        Returns a set of package names that are workspace members, which should be
        treated as known first-party imports.
        """
        workspace_packages: set[str] = set()

        pyproject_data = load_pyproject_toml(self.config)

        # 1. Check [tool.uv.sources] in current pyproject.toml
        try:
            sources = pyproject_data["tool"]["uv"]["sources"]
            for package_name, source_config in sources.items():
                if isinstance(source_config, dict) and source_config.get("workspace") is True:
                    workspace_packages.add(package_name)
                    logging.debug(f"Found workspace package in [tool.uv.sources]: {package_name}")
        except KeyError:
            logging.debug("No [tool.uv.sources] section found in pyproject.toml")

        # 2. Check if this is a workspace root (has [tool.uv.workspace])
        try:
            workspace_members = pyproject_data["tool"]["uv"]["workspace"]["members"]
            logging.debug(f"Found workspace root with {len(workspace_members)} members")

            # Add all workspace member names (extracting package names from paths)
            for member_path in workspace_members:
                # Try to read the member's pyproject.toml to get its actual package name
                member_pyproject_path = self.config.parent / member_path / "pyproject.toml"
                if member_pyproject_path.exists():
                    try:
                        member_data = load_pyproject_toml(member_pyproject_path)
                        package_name = member_data.get("project", {}).get("name")
                        if package_name:
                            workspace_packages.add(package_name)
                            logging.debug(f"Found workspace member package: {package_name} from {member_path}")
                    except Exception as e:
                        logging.debug(f"Could not read package name from {member_pyproject_path}: {e}")
                        # Fallback: use the last part of the path as package name
                        fallback_name = Path(member_path).name.replace("_", "-")
                        workspace_packages.add(fallback_name)
                        logging.debug(f"Using fallback package name: {fallback_name}")
        except KeyError:
            logging.debug("No [tool.uv.workspace] section found in pyproject.toml")

        # 3. Try to find workspace root in parent directories
        current_path = self.config.parent
        for parent in current_path.parents:
            parent_pyproject = parent / "pyproject.toml"
            if parent_pyproject.exists():
                try:
                    parent_data = load_pyproject_toml(parent_pyproject)
                    workspace_members = parent_data["tool"]["uv"]["workspace"]["members"]
                    logging.debug(f"Found workspace root at {parent} with {len(workspace_members)} members")

                    # Add all workspace member packages
                    for member_path in workspace_members:
                        member_pyproject_path = parent / member_path / "pyproject.toml"
                        if member_pyproject_path.exists():
                            try:
                                member_data = load_pyproject_toml(member_pyproject_path)
                                package_name = member_data.get("project", {}).get("name")
                                if package_name:
                                    workspace_packages.add(package_name)
                                    logging.debug(f"Found workspace package from parent: {package_name}")
                            except Exception:
                                pass
                    break  # Found workspace root, stop searching
                except KeyError:
                    continue  # Not a workspace root, keep searching

        if workspace_packages:
            logging.info(f"Detected {len(workspace_packages)} UV workspace packages: {', '.join(sorted(workspace_packages))}")

        return workspace_packages

    def get(self) -> DependenciesExtract:
        """
        Override get() to inject workspace packages as dependencies.

        Workspace packages are treated as regular dependencies since they should be
        available for import but not flagged as missing.
        """
        # Get workspace packages
        workspace_packages = self._get_workspace_packages()

        # Get regular dependencies (this also adds the module's own package via base class)
        result = super().get()

        # For workspace packages that ARE declared in dependencies, enhance them with proper module names
        # This helps deptry recognize them even if they're not installed in site-packages
        from deptry.dependency import Dependency
        from deptry.dependency_getter.base import DependenciesExtract

        enhanced_dependencies = []
        for dep in result.dependencies:
            # Check if this dependency is a workspace package
            # Normalize both the dependency name and workspace package names for comparison
            dep_normalized = dep.name.replace("-", "_").lower()
            is_workspace = False

            logging.debug(f"Checking dependency '{dep.name}' (normalized: '{dep_normalized}')")

            for ws_pkg in workspace_packages:
                ws_pkg_normalized = ws_pkg.replace("-", "_").lower()
                if dep_normalized == ws_pkg_normalized:
                    is_workspace = True
                    logging.debug(f"  -> Matched with workspace package '{ws_pkg}'")
                    # Recreate the dependency with both hyphenated and underscored module names
                    # This ensures deptry can match imports like "hasura_auth" or "hasura-auth"
                    module_names = [
                        ws_pkg,  # Original workspace name
                        ws_pkg.replace("-", "_"),  # Underscored version
                        ws_pkg.replace("_", "-"),  # Hyphenated version
                        dep.name,  # Declared name
                        dep.name.replace("-", "_"),  # Declared name underscored
                    ]
                    enhanced_dep = Dependency(
                        name=dep.name,
                        definition_file=self.config,
                        module_names=list(set(module_names)),  # Remove duplicates
                    )
                    enhanced_dependencies.append(enhanced_dep)
                    logging.debug(f"Enhanced workspace package dependency: {dep.name} with modules {module_names}")
                    break

            if not is_workspace:
                # Keep the original dependency as-is
                enhanced_dependencies.append(dep)

        return DependenciesExtract(
            enhanced_dependencies,
            result.dev_dependencies,
        )
