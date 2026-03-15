"""Repository summarization for RICA project understanding."""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from rica.logging_utils import get_component_logger
from rica.reader import scan_project_structure

logger = get_component_logger("repo_summary")


@dataclass
class RepoSummary:
    """Structured repository summary."""
    language: str
    frameworks: List[str]
    entry_points: List[str]
    key_modules: List[str]
    dependencies: List[str]
    test_files: List[str]
    config_files: List[str]
    project_type: str
    description: str


class RepoSummarizer:
    """Analyzes and summarizes project repositories."""
    
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        
    def analyze_repository(self) -> RepoSummary:
        """Analyze the repository and generate a comprehensive summary."""
        try:
            # Scan project structure
            structure = scan_project_structure(self.project_dir)
            
            # Detect language
            language = self._detect_language(structure)
            
            # Detect frameworks
            frameworks = self._detect_frameworks(structure)
            
            # Identify entry points
            entry_points = self._identify_entry_points(structure)
            
            # Find key modules
            key_modules = self._identify_key_modules(structure)
            
            # Get dependencies
            dependencies = structure.get("dependencies", [])
            
            # Get test files
            test_files = structure.get("tests", [])
            
            # Get config files
            config_files = structure.get("config_files", [])
            
            # Determine project type
            project_type = self._determine_project_type(frameworks, structure)
            
            # Generate description
            description = self._generate_description(
                language, frameworks, project_type, structure
            )
            
            summary = RepoSummary(
                language=language,
                frameworks=frameworks,
                entry_points=entry_points,
                key_modules=key_modules,
                dependencies=dependencies,
                test_files=test_files,
                config_files=config_files,
                project_type=project_type,
                description=description
            )
            
            logger.info(f"[repo_summary] Analyzed {language} {project_type} project")
            return summary
            
        except Exception as e:
            logger.error(f"[repo_summary] Failed to analyze repository: {e}")
            # Return default summary
            return RepoSummary(
                language="Python",
                frameworks=[],
                entry_points=[],
                key_modules=[],
                dependencies=[],
                test_files=[],
                config_files=[],
                project_type="Unknown",
                description="Failed to analyze project"
            )
    
    def _detect_language(self, structure: Dict[str, List[str]]) -> str:
        """Detect the primary programming language."""
        python_files = len(structure.get("python_files", []))
        
        if python_files > 0:
            return "Python"
        
        # Add more language detection as needed
        return "Unknown"
    
    def _detect_frameworks(self, structure: Dict[str, List[str]]) -> List[str]:
        """Detect web frameworks and other frameworks from dependencies and files."""
        frameworks = []
        dependencies = [dep.lower() for dep in structure.get("dependencies", [])]
        config_files = structure.get("config_files", [])
        
        # Web frameworks
        if any(framework in dependencies for framework in ["flask", "flask-sqlalchemy", "flask-login"]):
            frameworks.append("Flask")
        
        if any(framework in dependencies for framework in ["django", "djangorestframework"]):
            frameworks.append("Django")
        
        if any(framework in dependencies for framework in ["fastapi", "uvicorn"]):
            frameworks.append("FastAPI")
        
        if any(framework in dependencies for framework in ["starlette"]):
            frameworks.append("Starlette")
        
        # Data science frameworks
        if any(framework in dependencies for framework in ["pandas", "numpy", "scipy", "matplotlib"]):
            frameworks.append("Data Science")
        
        if any(framework in dependencies for framework in ["tensorflow", "pytorch", "keras"]):
            frameworks.append("Machine Learning")
        
        # Testing frameworks
        if any(framework in dependencies for framework in ["pytest", "unittest"]):
            frameworks.append("Testing")
        
        # Async frameworks
        if any(framework in dependencies for framework in ["asyncio", "aiohttp"]):
            frameworks.append("Async")
        
        return list(set(frameworks))
    
    def _identify_entry_points(self, structure: Dict[str, List[str]]) -> List[str]:
        """Identify potential entry points."""
        entry_points = []
        
        # Check for common entry point patterns
        python_files = structure.get("python_files", [])
        
        for file_path in python_files:
            file_name = Path(file_path).name
            
            # Common entry point files
            if file_name in ["main.py", "app.py", "run.py", "server.py", "manage.py"]:
                entry_points.append(file_path)
            
            # Files with if __name__ == '__main__'
            full_path = self.project_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    if "if __name__ == '__main__':" in content:
                        if file_path not in entry_points:
                            entry_points.append(file_path)
                except Exception:
                    pass
        
        return entry_points
    
    def _identify_key_modules(self, structure: Dict[str, List[str]]) -> List[str]:
        """Identify key modules in the project."""
        key_modules = []
        python_files = structure.get("python_files", [])
        
        # Look for common module patterns
        for file_path in python_files:
            file_name = Path(file_path).name
            module_name = Path(file_path).stem
            
            # Common important modules
            if any(pattern in module_name.lower() for pattern in [
                "auth", "user", "login", "security", "database", "db", "model",
                "api", "view", "controller", "service", "util", "helper", "config",
                "settings", "routes", "middleware", "schema", "serializer"
            ]):
                key_modules.append(file_path)
        
        return key_modules[:10]  # Limit to top 10
    
    def _determine_project_type(self, frameworks: List[str], structure: Dict[str, List[str]]) -> str:
        """Determine the type of project."""
        # Web application
        if any(framework in frameworks for framework in ["Flask", "Django", "FastAPI", "Starlette"]):
            return "Web Application"
        
        # Data science project
        if any(framework in frameworks for framework in ["Data Science", "Machine Learning"]):
            return "Data Science Project"
        
        # API project
        if any(framework in frameworks for framework in ["FastAPI"]):
            return "API Service"
        
        # Library/package
        config_files = structure.get("config_files", [])
        if any(file in config_files for file in ["setup.py", "pyproject.toml"]):
            return "Python Package"
        
        # Testing project
        if len(structure.get("tests", [])) > len(structure.get("python_files", [])) / 2:
            return "Testing Project"
        
        # CLI tool
        if any("argparse" in dep.lower() or "click" in dep.lower() 
               for dep in structure.get("dependencies", [])):
            return "CLI Tool"
        
        return "General Python Project"
    
    def _generate_description(self, language: str, frameworks: List[str], 
                            project_type: str, structure: Dict[str, List[str]]) -> str:
        """Generate a human-readable description of the project."""
        parts = []
        
        # Basic info
        parts.append(f"A {language} {project_type.lower()}")
        
        # Frameworks
        if frameworks:
            if len(frameworks) == 1:
                parts.append(f"using {frameworks[0]}")
            else:
                parts.append(f"using {', '.join(frameworks[:-1])} and {frameworks[-1]}")
        
        # Scale indicators
        python_files = len(structure.get("python_files", []))
        test_files = len(structure.get("tests", []))
        dependencies = len(structure.get("dependencies", []))
        
        if python_files > 20:
            parts.append("with a large codebase")
        elif python_files > 10:
            parts.append("with a moderate codebase")
        elif python_files > 0:
            parts.append("with a small codebase")
        
        if test_files > 5:
            parts.append(f"and {test_files} test files")
        
        if dependencies > 10:
            parts.append(f"and {dependencies} dependencies")
        
        return " ".join(parts) + "."
    
    def format_summary_for_prompt(self) -> str:
        """Format the summary for use in LLM prompts."""
        summary = self.analyze_repository()
        
        sections = [
            "=== PROJECT SUMMARY ===",
            f"Language: {summary.language}",
            f"Type: {summary.project_type}",
            f"Description: {summary.description}",
            ""
        ]
        
        if summary.frameworks:
            sections.append(f"Frameworks: {', '.join(summary.frameworks)}")
            sections.append("")
        
        if summary.entry_points:
            sections.append("Entry Points:")
            for entry_point in summary.entry_points:
                sections.append(f"  - {entry_point}")
            sections.append("")
        
        if summary.key_modules:
            sections.append("Key Modules:")
            for module in summary.key_modules[:5]:  # Limit to top 5
                sections.append(f"  - {module}")
            sections.append("")
        
        if summary.dependencies:
            sections.append("Dependencies (sample):")
            for dep in summary.dependencies[:10]:  # Limit to top 10
                sections.append(f"  - {dep}")
            sections.append("")
        
        return "\n".join(sections)
    
    def save_summary(self, output_path: Optional[str] = None) -> str:
        """Save the summary to a file."""
        if output_path is None:
            output_path = str(self.project_dir / ".rica_summary.json")
        
        summary = self.analyze_repository()
        
        # Convert to dict for JSON serialization
        summary_dict = {
            "language": summary.language,
            "frameworks": summary.frameworks,
            "entry_points": summary.entry_points,
            "key_modules": summary.key_modules,
            "dependencies": summary.dependencies,
            "test_files": summary.test_files,
            "config_files": summary.config_files,
            "project_type": summary.project_type,
            "description": summary.description,
            "generated_at": str(Path().cwd())  # Simple timestamp
        }
        
        try:
            output_file = Path(output_path)
            output_file.write_text(json.dumps(summary_dict, indent=2), encoding="utf-8")
            logger.info(f"[repo_summary] Saved summary to {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"[repo_summary] Failed to save summary: {e}")
            return ""
    
    def load_summary(self, summary_path: Optional[str] = None) -> Optional[RepoSummary]:
        """Load a previously saved summary."""
        if summary_path is None:
            summary_path = str(self.project_dir / ".rica_summary.json")
        
        try:
            summary_file = Path(summary_path)
            if not summary_file.exists():
                return None
            
            data = json.loads(summary_file.read_text(encoding="utf-8"))
            
            return RepoSummary(
                language=data.get("language", "Python"),
                frameworks=data.get("frameworks", []),
                entry_points=data.get("entry_points", []),
                key_modules=data.get("key_modules", []),
                dependencies=data.get("dependencies", []),
                test_files=data.get("test_files", []),
                config_files=data.get("config_files", []),
                project_type=data.get("project_type", "Unknown"),
                description=data.get("description", "")
            )
            
        except Exception as e:
            logger.error(f"[repo_summary] Failed to load summary: {e}")
            return None
