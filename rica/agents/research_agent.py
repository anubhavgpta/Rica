"""Research Agent for gathering context and information."""

import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger

from rica.logging_utils import get_component_logger
from rica.reader import CodebaseReader


class ResearchAgent:
    """Agent responsible for gathering context and research information for tasks."""
    
    def __init__(self, config: dict):
        self.config = config
        self.reader = CodebaseReader()
        self.logger = get_component_logger("research_agent")
        
        # Research capabilities
        self.research_patterns = {
            "api_documentation": {
                "keywords": ["api", "endpoint", "documentation", "reference"],
                "sources": ["docstrings", "comments", "README files"]
            },
            "dependencies": {
                "keywords": ["import", "require", "dependency", "package"],
                "sources": ["requirements.txt", "setup.py", "pyproject.toml", "import statements"]
            },
            "configuration": {
                "keywords": ["config", "setting", "env", "environment"],
                "sources": [".env", "config files", "settings.py"]
            },
            "tests": {
                "keywords": ["test", "spec", "unit", "integration"],
                "sources": ["test_*.py", "*_test.py", "tests/ directory"]
            }
        }
    
    def gather(self, task: Dict[str, Any], workspace_dir: str = None, project_dir: str = None) -> Dict[str, Any]:
        """
        Gather context and research information for a given task.
        
        Args:
            task: The task requiring research
            workspace_dir: Workspace directory path
            project_dir: Project directory path
            
        Returns:
            Dictionary containing gathered context and research results
        """
        self.logger.info(f"[researcher] gathering context for task: {task.get('description', '')[:50]}...")
        
        context = {
            "task_id": task.get("id", "unknown"),
            "task_description": task.get("description", ""),
            "task_type": task.get("type", "unknown"),
            "research_results": {},
            "dependencies_found": [],
            "related_files": [],
            "documentation_snippets": [],
            "configuration_info": {},
            "test_coverage": {},
            "similar_patterns": []
        }
        
        # Analyze task requirements
        task_desc = task.get("description", "").lower()
        
        # Determine research needs based on task type and description
        research_needs = self._analyze_research_needs(task_desc, task.get("type", ""))
        
        # Gather information from project files
        if project_dir:
            project_context = self._research_project_structure(project_dir, research_needs)
            context["research_results"].update(project_context)
        
        # Gather information from workspace
        if workspace_dir and workspace_dir != project_dir:
            workspace_context = self._research_workspace(workspace_dir, research_needs)
            context["research_results"].update(workspace_context)
        
        # Analyze dependencies
        dependencies = self._analyze_dependencies(project_dir or workspace_dir)
        context["dependencies_found"] = dependencies
        
        # Find related files
        related_files = self._find_related_files(task_desc, project_dir or workspace_dir)
        context["related_files"] = related_files
        
        # Extract documentation snippets
        docs = self._extract_documentation(task_desc, project_dir or workspace_dir)
        context["documentation_snippets"] = docs
        
        # Analyze configuration
        config_info = self._analyze_configuration(project_dir or workspace_dir)
        context["configuration_info"] = config_info
        
        # Check test coverage
        test_info = self._analyze_test_coverage(task_desc, project_dir or workspace_dir)
        context["test_coverage"] = test_info
        
        # Find similar patterns from memory
        similar_patterns = self._find_similar_patterns(task_desc, project_dir or workspace_dir)
        context["similar_patterns"] = similar_patterns
        
        self.logger.info(f"[researcher] gathered context: {len(context['related_files'])} files, "
                        f"{len(context['dependencies_found'])} dependencies, "
                        f"{len(context['documentation_snippets'])} docs")
        
        return context
    
    def _analyze_research_needs(self, task_desc: str, task_type: str) -> List[str]:
        """Analyze task description to determine what research is needed."""
        needs = []
        
        # Check for API-related needs
        if any(keyword in task_desc for keyword in ["api", "endpoint", "server", "route"]):
            needs.append("api_documentation")
        
        # Check for dependency needs
        if any(keyword in task_desc for keyword in ["install", "import", "package", "library"]):
            needs.append("dependencies")
        
        # Check for configuration needs
        if any(keyword in task_desc for keyword in ["config", "setting", "env"]):
            needs.append("configuration")
        
        # Check for testing needs
        if any(keyword in task_desc for keyword in ["test", "spec", "validate"]):
            needs.append("tests")
        
        # Task-specific needs
        if task_type == "codegen":
            needs.extend(["dependencies", "related_files"])
        elif task_type == "debug":
            needs.extend(["dependencies", "configuration", "similar_patterns"])
        
        return list(set(needs))  # Remove duplicates
    
    def _research_project_structure(self, project_dir: str, research_needs: List[str]) -> Dict[str, Any]:
        """Research project structure and gather relevant information."""
        if not project_dir or not Path(project_dir).exists():
            return {}
        
        project_path = Path(project_dir)
        results = {}
        
        try:
            # Scan project structure
            python_files = list(project_path.rglob("*.py"))
            config_files = []
            doc_files = []
            
            for pattern in ["*.md", "*.rst", "*.txt"]:
                config_files.extend(project_path.rglob(pattern))
            
            # Categorize files
            for file_path in python_files:
                if "test" in file_path.name.lower():
                    if "tests" not in results:
                        results["tests"] = []
                    results["tests"].append(str(file_path))
                elif file_path.name in ["__init__.py", "setup.py", "requirements.txt", "pyproject.toml"]:
                    if "project_files" not in results:
                        results["project_files"] = []
                    results["project_files"].append(str(file_path))
            
            results["python_files_count"] = len(python_files)
            results["project_structure"] = self._analyze_directory_structure(project_path)
            
        except Exception as e:
            self.logger.warning(f"[researcher] Error researching project structure: {e}")
        
        return results
    
    def _research_workspace(self, workspace_dir: str, research_needs: List[str]) -> Dict[str, Any]:
        """Research workspace for additional context."""
        workspace_path = Path(workspace_dir)
        if not workspace_path.exists():
            return {}
        
        results = {}
        
        try:
            # Look for workspace-specific files
            workspace_files = list(workspace_path.glob("*"))
            results["workspace_files"] = [str(f) for f in workspace_files if f.is_file()]
            
            # Look for generated files
            generated_patterns = ["*.py", "*.js", "*.html", "*.css", "*.json"]
            generated_files = []
            for pattern in generated_patterns:
                generated_files.extend(workspace_path.glob(pattern))
            
            results["generated_files"] = [str(f) for f in generated_files]
            
        except Exception as e:
            self.logger.warning(f"[researcher] Error researching workspace: {e}")
        
        return results
    
    def _analyze_dependencies(self, directory: str) -> List[Dict[str, str]]:
        """Analyze project dependencies."""
        if not directory:
            return []
        
        dir_path = Path(directory)
        dependencies = []
        
        try:
            # Check requirements.txt
            requirements_file = dir_path / "requirements.txt"
            if requirements_file.exists():
                with open(requirements_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            dependencies.append({
                                "source": "requirements.txt",
                                "dependency": line
                            })
            
            # Check setup.py
            setup_file = dir_path / "setup.py"
            if setup_file.exists():
                content = setup_file.read_text(encoding='utf-8')
                # Simple regex to find install_requires
                matches = re.findall(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
                for match in matches:
                    deps = [dep.strip().strip('"\'') for dep in match.split(',')]
                    for dep in deps:
                        if dep:
                            dependencies.append({
                                "source": "setup.py",
                                "dependency": dep
                            })
            
            # Check pyproject.toml
            pyproject_file = dir_path / "pyproject.toml"
            if pyproject_file.exists():
                content = pyproject_file.read_text(encoding='utf-8')
                # Simple regex for dependencies
                if '[tool.poetry.dependencies]' in content:
                    section = content.split('[tool.poetry.dependencies]')[1].split('\n[')[0]
                    for line in section.split('\n'):
                        line = line.strip()
                        if '=' in line and not line.startswith('#'):
                            dep = line.split('=')[0].strip()
                            dependencies.append({
                                "source": "pyproject.toml",
                                "dependency": dep
                            })
            
            # Scan Python files for imports
            for py_file in dir_path.rglob("*.py"):
                if "test" not in py_file.name.lower() and py_file.name != "__init__.py":
                    try:
                        content = py_file.read_text(encoding='utf-8')
                        # Find import statements
                        imports = re.findall(r'^(?:from|import)\s+(.+)$', content, re.MULTILINE)
                        for imp in imports:
                            # Clean up import statement
                            clean_imp = imp.split(' as ')[0].strip()
                            if not clean_imp.startswith('.'):
                                dependencies.append({
                                    "source": f"import:{py_file.name}",
                                    "dependency": clean_imp
                                })
                    except Exception:
                        continue  # Skip files that can't be read
        
        except Exception as e:
            self.logger.warning(f"[researcher] Error analyzing dependencies: {e}")
        
        return dependencies
    
    def _find_related_files(self, task_desc: str, directory: str) -> List[Dict[str, str]]:
        """Find files related to the task description."""
        if not directory:
            return []
        
        dir_path = Path(directory)
        related_files = []
        
        try:
            # Extract keywords from task description
            keywords = re.findall(r'\b\w+\b', task_desc.lower())
            keywords = [kw for kw in keywords if len(kw) > 3]  # Filter short words
            
            # Search Python files
            for py_file in dir_path.rglob("*.py"):
                try:
                    content = py_file.read_text(encoding='utf-8').lower()
                    
                    # Check if file contains relevant keywords
                    relevance_score = 0
                    for keyword in keywords:
                        if keyword in content:
                            relevance_score += content.count(keyword)
                    
                    if relevance_score > 0:
                        related_files.append({
                            "path": str(py_file),
                            "relevance_score": relevance_score,
                            "type": "python"
                        })
                except Exception:
                    continue
            
            # Sort by relevance
            related_files.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # Limit to top 10 most relevant files
            related_files = related_files[:10]
            
        except Exception as e:
            self.logger.warning(f"[researcher] Error finding related files: {e}")
        
        return related_files
    
    def _extract_documentation(self, task_desc: str, directory: str) -> List[Dict[str, str]]:
        """Extract relevant documentation snippets."""
        if not directory:
            return []
        
        dir_path = Path(directory)
        docs = []
        
        try:
            # Look for docstrings in related files
            keywords = re.findall(r'\b\w+\b', task_desc.lower())
            
            for py_file in dir_path.rglob("*.py"):
                try:
                    content = py_file.read_text(encoding='utf-8')
                    
                    # Extract docstrings
                    docstring_pattern = r'"""([^"]+)"""'
                    matches = re.findall(docstring_pattern, content, re.DOTALL)
                    
                    for docstring in matches:
                        # Check if docstring contains relevant keywords
                        docstring_lower = docstring.lower()
                        relevance = any(keyword in docstring_lower for keyword in keywords)
                        
                        if relevance or len(docs) < 5:  # Include some docs even if not directly relevant
                            docs.append({
                                "file": str(py_file),
                                "content": docstring.strip()[:200] + "..." if len(docstring) > 200 else docstring.strip(),
                                "relevance": relevance
                            })
                except Exception:
                    continue
            
            # Look for README files
            for readme in dir_path.glob("README*"):
                try:
                    content = readme.read_text(encoding='utf-8')
                    docs.append({
                        "file": str(readme),
                        "content": content[:300] + "..." if len(content) > 300 else content,
                        "relevance": True
                    })
                except Exception:
                    continue
            
        except Exception as e:
            self.logger.warning(f"[researcher] Error extracting documentation: {e}")
        
        return docs[:10]  # Limit to 10 docs
    
    def _analyze_configuration(self, directory: str) -> Dict[str, Any]:
        """Analyze project configuration."""
        if not directory:
            return {}
        
        dir_path = Path(directory)
        config_info = {}
        
        try:
            # Look for config files
            config_files = [
                ".env", ".env.example", "config.py", "settings.py",
                "config.json", "settings.json", ".config"
            ]
            
            found_configs = []
            for config_file in config_files:
                config_path = dir_path / config_file
                if config_path.exists():
                    found_configs.append(str(config_path))
            
            config_info["config_files"] = found_configs
            
            # Analyze .env file if exists
            env_file = dir_path / ".env"
            if env_file.exists():
                try:
                    content = env_file.read_text(encoding='utf-8')
                    env_vars = {}
                    for line in content.split('\n'):
                        line = line.strip()
                        if '=' in line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            env_vars[key] = value
                    config_info["environment_variables"] = env_vars
                except Exception:
                    pass
            
        except Exception as e:
            self.logger.warning(f"[researcher] Error analyzing configuration: {e}")
        
        return config_info
    
    def _analyze_test_coverage(self, task_desc: str, directory: str) -> Dict[str, Any]:
        """Analyze test coverage and related test files."""
        if not directory:
            return {}
        
        dir_path = Path(directory)
        test_info = {}
        
        try:
            # Find test files
            test_files = []
            for pattern in ["test_*.py", "*_test.py"]:
                test_files.extend(dir_path.rglob(pattern))
            
            test_info["test_files"] = [str(f) for f in test_files]
            test_info["test_count"] = len(test_files)
            
            # Look for test directories
            test_dirs = [d for d in dir_path.iterdir() if d.is_dir() and "test" in d.name.lower()]
            test_info["test_directories"] = [str(d) for d in test_dirs]
            
            # Analyze test content for relevance
            keywords = re.findall(r'\b\w+\b', task_desc.lower())
            relevant_tests = []
            
            for test_file in test_files:
                try:
                    content = test_file.read_text(encoding='utf-8').lower()
                    relevance = any(keyword in content for keyword in keywords)
                    
                    if relevance:
                        relevant_tests.append(str(test_file))
                except Exception:
                    continue
            
            test_info["relevant_tests"] = relevant_tests
            
        except Exception as e:
            self.logger.warning(f"[researcher] Error analyzing test coverage: {e}")
        
        return test_info
    
    def _analyze_directory_structure(self, project_path: Path) -> Dict[str, Any]:
        """Analyze and summarize directory structure."""
        structure = {
            "directories": [],
            "file_types": {},
            "depth": 0
        }
        
        try:
            # Get directory structure (up to 3 levels deep)
            for root, dirs, files in project_path.walk():
                root_path = Path(root)
                depth = len(root_path.relative_to(project_path).parts)
                
                if depth <= 3:
                    structure["directories"].append({
                        "path": str(root_path.relative_to(project_path)),
                        "depth": depth,
                        "file_count": len(files)
                    })
                
                # Track file types
                for file in files:
                    ext = Path(file).suffix.lower()
                    structure["file_types"][ext] = structure["file_types"].get(ext, 0) + 1
                
                structure["depth"] = max(structure["depth"], depth)
        
        except Exception as e:
            self.logger.warning(f"[researcher] Error analyzing directory structure: {e}")
        
        return structure
    
    def _find_similar_patterns(self, task_desc: str, directory: str) -> List[Dict[str, Any]]:
        """Find similar patterns from memory or existing code."""
        patterns = []
        
        try:
            # This could be enhanced to search the memory store for similar tasks
            # For now, return basic pattern analysis
            
            # Look for common patterns in the codebase
            if directory:
                dir_path = Path(directory)
                
                # Find function definitions that might be relevant
                keywords = re.findall(r'\b\w+\b', task_desc.lower())
                
                for py_file in dir_path.rglob("*.py"):
                    try:
                        content = py_file.read_text(encoding='utf-8')
                        
                        # Find function definitions
                        func_pattern = r'def\s+(\w+)\s*\([^)]*\):'
                        matches = re.findall(func_pattern, content)
                        
                        for func_name in matches:
                            if any(keyword in func_name.lower() for keyword in keywords):
                                patterns.append({
                                    "type": "function",
                                    "name": func_name,
                                    "file": str(py_file),
                                    "relevance": "high"
                                })
                    except Exception:
                        continue
        
        except Exception as e:
            self.logger.warning(f"[researcher] Error finding similar patterns: {e}")
        
        return patterns[:5]  # Limit to 5 patterns
