"""Automatic dependency detection and management for RICA projects."""

import re
import sys
import importlib.util
from pathlib import Path
from typing import List, Set, Dict, Optional
from loguru import logger

from rica.logging_utils import get_component_logger

logger = get_component_logger("dependency_manager")


def is_stdlib(module_name: str) -> bool:
    """Check if a module is part of Python standard library."""
    if module_name in sys.builtin_module_names:
        return True
    
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return False
    
    return "site-packages" not in (spec.origin or "")


# Invalid packages that should never be installed
INVALID_PACKAGES = {
    "__future__",
    "builtins", 
    "site",
    "runpy",
    "encodings"
}


class DependencyManager:
    """Manages automatic detection and installation of project dependencies."""
    
    def __init__(self, project_dir: str, executor_agent=None):
        self.project_dir = Path(project_dir)
        self.executor_agent = executor_agent
        self.requirements_file = self.project_dir / "requirements.txt"
        self.pyproject_file = self.project_dir / "pyproject.toml"
        
    def extract_imports_from_file(self, file_path: Path) -> Set[str]:
        """Extract import statements from a Python file."""
        imports = set()
        
        try:
            content = file_path.read_text(encoding="utf-8")
            
            # Find import statements
            import_patterns = [
                r'^import\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)',
                r'^from\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s+import',
            ]
            
            for pattern in import_patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                for match in matches:
                    # Get the top-level package name
                    package_name = match.split('.')[0]
                    if package_name and not package_name.startswith('.'):
                        imports.add(package_name)
                        
        except Exception as e:
            logger.warning(f"[dependency_manager] Failed to extract imports from {file_path.name}: {e}")
            
        return imports
    
    def scan_project_imports(self) -> Set[str]:
        """Scan all Python files in the project for imports."""
        all_imports = set()
        
        # Only scan files within the project directory, not site-packages
        for py_file in self.project_dir.rglob("*.py"):
            # Skip files in site-packages or other library directories
            if "site-packages" in str(py_file):
                logger.debug(f"[dependency_manager] Skipping site-packages file: {py_file}")
                continue
            
            imports = self.extract_imports_from_file(py_file)
            all_imports.update(imports)
            logger.debug(f"[dependency_manager] Found {len(imports)} imports in {py_file.name}")
        
        logger.info(f"[dependency_manager] Total unique imports found: {len(all_imports)}")
        return all_imports
    
    def get_current_dependencies(self) -> Set[str]:
        """Get currently listed dependencies from requirements files."""
        dependencies = set()
        
        # Check requirements.txt
        if self.requirements_file.exists():
            try:
                content = self.requirements_file.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Extract package name (remove version specs)
                        package = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0]
                        dependencies.add(package.strip())
            except Exception as e:
                logger.warning(f"[dependency_manager] Failed to read requirements.txt: {e}")
        
        # Check pyproject.toml
        if self.pyproject_file.exists():
            try:
                content = self.pyproject_file.read_text(encoding="utf-8")
                # Simple extraction of dependencies from pyproject.toml
                deps_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if deps_match:
                    deps_section = deps_match.group(1)
                    for line in deps_section.splitlines():
                        line = line.strip().strip('"\'')
                        if line and not line.startswith('#'):
                            package = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0]
                            dependencies.add(package.strip())
            except Exception as e:
                logger.warning(f"[dependency_manager] Failed to parse pyproject.toml: {e}")
        
        return dependencies
    
    def detect_missing_dependencies(self) -> List[str]:
        """Detect dependencies that are imported but not listed in requirements."""
        all_imports = self.scan_project_imports()
        current_deps = self.get_current_dependencies()
        
        # Filter out standard library modules, invalid packages, and local modules
        local_modules = self._detect_local_modules()
        
        missing = []
        for import_name in all_imports:
            # Skip standard library modules
            if is_stdlib(import_name):
                continue
            
            # Skip invalid packages
            if import_name in INVALID_PACKAGES:
                continue
                
            # Skip local modules
            if import_name in local_modules:
                continue
                
            # Only add if not already in dependencies
            if import_name not in current_deps:
                missing.append(import_name)
        
        logger.info(f"[dependency_manager] Detected imports: {sorted(all_imports)}")
        logger.info(f"[dependency_manager] Missing dependencies: {missing}")
        return sorted(missing)
    
    def _get_stdlib_modules(self) -> Set[str]:
        """Get a set of standard library module names."""
        # Common standard library modules (abbreviated list)
        stdlib = {
            'os', 'sys', 'json', 're', 'datetime', 'pathlib', 'collections', 
            'itertools', 'functools', 'operator', 'math', 'random', 'string',
            'typing', 'dataclasses', 'enum', 'contextlib', 'unittest', 'logging',
            'argparse', 'configparser', 'subprocess', 'threading', 'multiprocessing',
            'socket', 'urllib', 'http', 'email', 'html', 'xml', 'csv', 'sqlite3',
            'pickle', 'base64', 'hashlib', 'hmac', 'secrets', 'time', 'zoneinfo',
            'importlib', 'inspect', 'pkgutil', 'warnings', 'traceback', 'types',
            'weakref', 'copy', 'gc', 'dis', 'ast', 'symbol', 'token', 'keyword',
            'tokenize', 'py_compile', 'compileall', 'tabnanny', 'pydoc', 'doctest',
            'unittest', 'pdb', 'profile', 'pstats', 'timeit', 'trace', 'tracemalloc',
            'faulthandler', 'resource', 'sysconfig', 'platform', 'errno', 'stat'
        }
        return stdlib
    
    def _detect_local_modules(self) -> Set[str]:
        """Detect local project modules."""
        local_modules = set()
        
        for py_file in self.project_dir.rglob("*.py"):
            if py_file.name != "__init__.py":
                # Use the directory name as potential module name
                if py_file.parent != self.project_dir:
                    module_name = py_file.parent.name
                    if module_name.isidentifier():
                        local_modules.add(module_name)
                
                # Use the file name (without .py) as potential module name
                file_module = py_file.stem
                if file_module.isidentifier():
                    local_modules.add(file_module)
        
        return local_modules
    
    def add_dependency(self, package_name: str, version_spec: str = "") -> bool:
        """Add a dependency to requirements.txt."""
        try:
            # Ensure requirements.txt exists
            if not self.requirements_file.exists():
                self.requirements_file.write_text("# RICA auto-generated requirements\n", encoding="utf-8")
            
            # Read existing content
            content = self.requirements_file.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            # Check if dependency already exists
            package_line = f"{package_name}{version_spec}"
            for i, line in enumerate(lines):
                if line.startswith(package_name):
                    # Update existing line
                    lines[i] = package_line
                    break
            else:
                # Add new line
                lines.append(package_line)
            
            # Write back
            new_content = "\n".join(lines) + "\n"
            self.requirements_file.write_text(new_content, encoding="utf-8")
            
            logger.info(f"[dependency_manager] Added dependency: {package_line}")
            return True
            
        except Exception as e:
            logger.error(f"[dependency_manager] Failed to add dependency {package_name}: {e}")
            return False
    
    def install_dependencies(self, packages: List[str]) -> bool:
        """Install packages using pip."""
        if not self.executor_agent:
            logger.warning("[dependency_manager] No executor agent available for installation")
            return False
        
        try:
            # Install packages one by one to avoid conflicts
            for package in packages:
                logger.info(f"[dependency_manager] Installing {package}...")
                
                result = self.executor_agent.run(f"pip install {package}")
                
                if result["success"]:
                    # Add to requirements.txt
                    self.add_dependency(package)
                    logger.info(f"[dependency_manager] Successfully installed {package}")
                else:
                    logger.error(f"[dependency_manager] Failed to install {package}: {result.get('stderr', '')}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"[dependency_manager] Installation failed: {e}")
            return False
    
    def install_from_requirements(self) -> bool:
        """Install all dependencies from requirements.txt."""
        if not self.requirements_file.exists():
            logger.info("[dependency_manager] No requirements.txt found")
            return True
        
        if not self.executor_agent:
            logger.warning("[dependency_manager] No executor agent available for installation")
            return False
        
        try:
            logger.info("[dependency_manager] Installing from requirements.txt...")
            result = self.executor_agent.run("pip install -r requirements.txt")
            
            if result["success"]:
                logger.info("[dependency_manager] Successfully installed requirements")
                return True
            else:
                logger.error(f"[dependency_manager] Failed to install requirements: {result.get('stderr', '')}")
                return False
                
        except Exception as e:
            logger.error(f"[dependency_manager] Requirements installation failed: {e}")
            return False
    
    def auto_detect_and_install(self) -> Dict[str, any]:
        """Automatically detect and install missing dependencies."""
        missing_deps = self.detect_missing_dependencies()
        
        if not missing_deps:
            return {
                "success": True,
                "installed": [],
                "message": "All dependencies satisfied"
            }
        
        logger.info(f"[dependency_manager] Auto-installing {len(missing_deps)} missing dependencies")
        
        success = self.install_dependencies(missing_deps)
        
        return {
            "success": success,
            "installed": missing_deps if success else [],
            "attempted": missing_deps,
            "message": f"Installed {len(missing_deps)} dependencies" if success else "Installation failed"
        }
