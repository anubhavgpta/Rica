"""Project intelligence analyzer for deep project understanding."""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
from loguru import logger

from rica.logging_utils import get_component_logger
from rica.reader import scan_project_structure

analyzer_logger = get_component_logger("project_analyzer")


@dataclass
class ProjectIntelligence:
    """Comprehensive project intelligence data."""
    language: str
    frameworks: List[str]
    dependencies: List[str]
    entry_points: List[str]
    test_files: List[str]
    config_files: List[str]
    project_type: str
    architecture_patterns: List[str]
    coding_style: Dict[str, Any]
    complexity_metrics: Dict[str, Any]
    security_indicators: List[str]
    performance_indicators: List[str]


class ProjectAnalyzer:
    """Analyzes projects to extract deep intelligence."""
    
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        
    def analyze_project(self) -> ProjectIntelligence:
        """Perform comprehensive project analysis."""
        try:
            # Get basic structure
            structure = scan_project_structure(self.project_dir)
            
            # Detect language
            language = self._detect_primary_language(structure)
            
            # Detect frameworks
            frameworks = self._detect_frameworks(structure)
            
            # Get dependencies
            dependencies = structure.get("dependencies", [])
            
            # Identify entry points
            entry_points = self._identify_entry_points(structure)
            
            # Get test files
            test_files = structure.get("tests", [])
            
            # Get config files
            config_files = structure.get("config_files", [])
            
            # Determine project type
            project_type = self._determine_project_type(frameworks, structure)
            
            # Analyze architecture patterns
            architecture_patterns = self._analyze_architecture_patterns(structure)
            
            # Analyze coding style
            coding_style = self._analyze_coding_style(structure)
            
            # Calculate complexity metrics
            complexity_metrics = self._calculate_complexity_metrics(structure)
            
            # Detect security indicators
            security_indicators = self._detect_security_indicators(structure)
            
            # Detect performance indicators
            performance_indicators = self._detect_performance_indicators(structure)
            
            intelligence = ProjectIntelligence(
                language=language,
                frameworks=frameworks,
                dependencies=dependencies,
                entry_points=entry_points,
                test_files=test_files,
                config_files=config_files,
                project_type=project_type,
                architecture_patterns=architecture_patterns,
                coding_style=coding_style,
                complexity_metrics=complexity_metrics,
                security_indicators=security_indicators,
                performance_indicators=performance_indicators
            )
            
            analyzer_logger.info(f"[project_analyzer] Analyzed {language} {project_type} with {len(frameworks)} frameworks")
            return intelligence
            
        except Exception as e:
            analyzer_logger.error(f"[project_analyzer] Analysis failed: {e}")
            return self._get_default_intelligence()
    
    def _detect_primary_language(self, structure: Dict[str, List[str]]) -> str:
        """Detect the primary programming language."""
        python_files = len(structure.get("python_files", []))
        
        if python_files > 0:
            return "Python"
        
        # Add more language detection as needed
        return "Unknown"
    
    def _detect_frameworks(self, structure: Dict[str, List[str]]) -> List[str]:
        """Detect frameworks with enhanced pattern recognition."""
        frameworks = []
        dependencies = [dep.lower() for dep in structure.get("dependencies", [])]
        config_files = structure.get("config_files", [])
        python_files = structure.get("python_files", [])
        
        # Web frameworks
        if any(fw in dependencies for fw in ["flask", "flask-sqlalchemy", "flask-login", "flask-migrate"]):
            frameworks.append("Flask")
        
        if any(fw in dependencies for fw in ["django", "djangorestframework", "django-cors-headers"]):
            frameworks.append("Django")
        
        if any(fw in dependencies for fw in ["fastapi", "uvicorn", "pydantic"]):
            frameworks.append("FastAPI")
        
        if any(fw in dependencies for fw in ["starlette", "jinja2"]):
            frameworks.append("Starlette")
        
        # Data science frameworks
        if any(fw in dependencies for fw in ["pandas", "numpy", "scipy", "matplotlib", "seaborn"]):
            frameworks.append("Data Science")
        
        if any(fw in dependencies for fw in ["tensorflow", "pytorch", "keras", "scikit-learn"]):
            frameworks.append("Machine Learning")
        
        # Database frameworks
        if any(fw in dependencies for fw in ["sqlalchemy", "alembic", "psycopg2", "pymongo"]):
            frameworks.append("Database")
        
        # Testing frameworks
        if any(fw in dependencies for fw in ["pytest", "unittest", "nose2", "coverage"]):
            frameworks.append("Testing")
        
        # Async frameworks
        if any(fw in dependencies for fw in ["asyncio", "aiohttp", "aiofiles"]):
            frameworks.append("Async")
        
        # CLI frameworks
        if any(fw in dependencies for fw in ["click", "argparse", "typer"]):
            frameworks.append("CLI")
        
        # API frameworks
        if any(fw in dependencies for fw in ["requests", "httpx", "urllib3"]):
            frameworks.append("HTTP Client")
        
        return list(set(frameworks))
    
    def _identify_entry_points(self, structure: Dict[str, List[str]]) -> List[str]:
        """Identify entry points with enhanced detection."""
        entry_points = []
        python_files = structure.get("python_files", [])
        
        for file_path in python_files:
            file_name = Path(file_path).name
            full_path = self.project_dir / file_path
            
            # Common entry point patterns
            if file_name in ["main.py", "app.py", "run.py", "server.py", "manage.py", "cli.py"]:
                entry_points.append(file_path)
            
            # Check for __main__ blocks
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    if "if __name__ == '__main__':" in content:
                        if file_path not in entry_points:
                            entry_points.append(file_path)
                    
                    # Check for Flask app patterns
                    if "app.run(" in content or "Flask(__name__)" in content:
                        if file_path not in entry_points:
                            entry_points.append(file_path)
                    
                    # Check for Django manage patterns
                    if "execute_from_command_line" in content:
                        if file_path not in entry_points:
                            entry_points.append(file_path)
                            
                except Exception:
                    pass
        
        return entry_points
    
    def _determine_project_type(self, frameworks: List[str], structure: Dict[str, List[str]]) -> str:
        """Determine project type with enhanced classification."""
        # Web application
        if any(fw in frameworks for fw in ["Flask", "Django", "FastAPI", "Starlette"]):
            return "Web Application"
        
        # API service
        if "FastAPI" in frameworks or ("API Client" in frameworks and "Data Science" not in frameworks):
            return "API Service"
        
        # Data science project
        if any(fw in frameworks for fw in ["Data Science", "Machine Learning"]):
            return "Data Science Project"
        
        # CLI tool
        if "CLI" in frameworks:
            return "CLI Tool"
        
        # Library/package
        config_files = structure.get("config_files", [])
        if any(file in config_files for file in ["setup.py", "pyproject.toml"]) and not frameworks:
            return "Python Package"
        
        # Testing project
        test_files = structure.get("tests", [])
        python_files = structure.get("python_files", [])
        if len(test_files) > len(python_files) / 2:
            return "Testing Project"
        
        # Database project
        if "Database" in frameworks:
            return "Database Application"
        
        return "General Python Project"
    
    def _analyze_architecture_patterns(self, structure: Dict[str, List[str]]) -> List[str]:
        """Analyze architectural patterns used in the project."""
        patterns = []
        python_files = structure.get("python_files", [])
        
        # Look for MVC/MVT patterns
        has_models = any("model" in Path(f).name.lower() for f in python_files)
        has_views = any("view" in Path(f).name.lower() for f in python_files)
        has_controllers = any("controller" in Path(f).name.lower() for f in python_files)
        
        if has_models and (has_views or has_controllers):
            patterns.append("MVC/MVT Pattern")
        
        # Look for service layer
        has_services = any("service" in Path(f).name.lower() for f in python_files)
        if has_services:
            patterns.append("Service Layer Pattern")
        
        # Look for repository pattern
        has_repositories = any("repository" in Path(f).name.lower() for f in python_files)
        if has_repositories:
            patterns.append("Repository Pattern")
        
        # Look for factory pattern
        for file_path in python_files[:10]:  # Check first 10 files
            full_path = self.project_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    if "def create_" in content or "def make_" in content or "Factory" in content:
                        patterns.append("Factory Pattern")
                        break
                except Exception:
                    pass
        
        # Look for singleton pattern
        for file_path in python_files[:10]:
            full_path = self.project_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    if "_instance = None" in content and "def __new__" in content:
                        patterns.append("Singleton Pattern")
                        break
                except Exception:
                    pass
        
        return list(set(patterns))
    
    def _analyze_coding_style(self, structure: Dict[str, List[str]]) -> Dict[str, Any]:
        """Analyze coding style and conventions."""
        style_info = {
            "line_length_average": 0,
            "uses_type_hints": False,
            "uses_docstrings": False,
            "naming_convention": "snake_case",
            "imports_style": "top_level"
        }
        
        python_files = structure.get("python_files", [])
        if not python_files:
            return style_info
        
        total_lines = 0
        total_length = 0
        files_with_type_hints = 0
        files_with_docstrings = 0
        
        for file_path in python_files[:20]:  # Sample first 20 files
            full_path = self.project_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    lines = content.splitlines()
                    
                    # Calculate average line length
                    for line in lines:
                        if line.strip():
                            total_length += len(line)
                            total_lines += 1
                    
                    # Check for type hints
                    if any(":" in line and ("def " in line or "class " in line) for line in lines):
                        files_with_type_hints += 1
                    
                    # Check for docstrings
                    if any('"""' in line or "'''" in line for line in lines):
                        files_with_docstrings += 1
                        
                except Exception:
                    pass
        
        if total_lines > 0:
            style_info["line_length_average"] = total_length // total_lines
        
        if python_files:
            style_info["uses_type_hints"] = files_with_type_hints / len(python_files) > 0.5
            style_info["uses_docstrings"] = files_with_docstrings / len(python_files) > 0.5
        
        return style_info
    
    def _calculate_complexity_metrics(self, structure: Dict[str, List[str]]) -> Dict[str, Any]:
        """Calculate project complexity metrics."""
        metrics = {
            "file_count": len(structure.get("python_files", [])),
            "dependency_count": len(structure.get("dependencies", [])),
            "test_coverage_estimate": 0.0,
            "complexity_score": 0
        }
        
        python_files = structure.get("python_files", [])
        test_files = structure.get("tests", [])
        
        # Estimate test coverage
        if python_files:
            metrics["test_coverage_estimate"] = len(test_files) / len(python_files)
        
        # Calculate complexity score (simple heuristic)
        complexity_score = 0
        complexity_score += len(python_files) * 1  # Files contribute
        complexity_score += len(structure.get("dependencies", [])) * 2  # Dependencies contribute more
        complexity_score += len(structure.get("config_files", [])) * 3  # Config files indicate complexity
        
        metrics["complexity_score"] = complexity_score
        
        return metrics
    
    def _detect_security_indicators(self, structure: Dict[str, List[str]]) -> List[str]:
        """Detect security-related indicators."""
        indicators = []
        dependencies = [dep.lower() for dep in structure.get("dependencies", [])]
        python_files = structure.get("python_files", [])
        
        # Security-related dependencies
        security_deps = ["cryptography", "pyjwt", "bcrypt", "passlib", "oauthlib"]
        for dep in security_deps:
            if any(dep in d for d in dependencies):
                indicators.append(f"Security: {dep.title()}")
        
        # Check for security patterns in code
        for file_path in python_files[:10]:  # Sample first 10 files
            full_path = self.project_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    
                    if "password" in content.lower() or "secret" in content.lower():
                        indicators.append("Security: Credential handling detected")
                    
                    if "ssl" in content.lower() or "tls" in content.lower():
                        indicators.append("Security: SSL/TLS usage detected")
                        
                except Exception:
                    pass
        
        return indicators
    
    def _detect_performance_indicators(self, structure: Dict[str, List[str]]) -> List[str]:
        """Detect performance-related indicators."""
        indicators = []
        dependencies = [dep.lower() for dep in structure.get("dependencies", [])]
        python_files = structure.get("python_files", [])
        
        # Performance-related dependencies
        perf_deps = ["redis", "celery", "gunicorn", "uwsgi", "nginx", "cache"]
        for dep in perf_deps:
            if any(dep in d for d in dependencies):
                indicators.append(f"Performance: {dep.title()}")
        
        # Check for performance patterns in code
        for file_path in python_files[:10]:  # Sample first 10 files
            full_path = self.project_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    
                    if "cache" in content.lower():
                        indicators.append("Performance: Caching detected")
                    
                    if "async def" in content:
                        indicators.append("Performance: Async patterns detected")
                        
                except Exception:
                    pass
        
        return indicators
    
    def _get_default_intelligence(self) -> ProjectIntelligence:
        """Get default intelligence for failed analysis."""
        return ProjectIntelligence(
            language="Python",
            frameworks=[],
            dependencies=[],
            entry_points=[],
            test_files=[],
            config_files=[],
            project_type="Unknown",
            architecture_patterns=[],
            coding_style={},
            complexity_metrics={},
            security_indicators=[],
            performance_indicators=[]
        )
    
    def format_intelligence_for_prompt(self) -> str:
        """Format intelligence data for use in LLM prompts."""
        intelligence = self.analyze_project()
        
        sections = [
            "=== PROJECT INTELLIGENCE ===",
            f"Language: {intelligence.language}",
            f"Type: {intelligence.project_type}",
            f"Dependencies: {len(intelligence.dependencies)}",
            f"Complexity Score: {intelligence.complexity_metrics.get('complexity_score', 0)}",
            ""
        ]
        
        if intelligence.frameworks:
            sections.append(f"Frameworks: {', '.join(intelligence.frameworks)}")
            sections.append("")
        
        if intelligence.architecture_patterns:
            sections.append("Architecture Patterns:")
            for pattern in intelligence.architecture_patterns:
                sections.append(f"  - {pattern}")
            sections.append("")
        
        if intelligence.coding_style:
            style = intelligence.coding_style
            sections.append("Coding Style:")
            sections.append(f"  - Type hints: {'Yes' if style.get('uses_type_hints') else 'No'}")
            sections.append(f"  - Docstrings: {'Yes' if style.get('uses_docstrings') else 'No'}")
            sections.append(f"  - Avg line length: {style.get('line_length_average', 0)}")
            sections.append("")
        
        if intelligence.security_indicators:
            sections.append("Security Indicators:")
            for indicator in intelligence.security_indicators:
                sections.append(f"  - {indicator}")
            sections.append("")
        
        if intelligence.performance_indicators:
            sections.append("Performance Indicators:")
            for indicator in intelligence.performance_indicators:
                sections.append(f"  - {indicator}")
            sections.append("")
        
        return "\n".join(sections)
