"""
AST-based code editing for safe and precise modifications.
"""

import ast
from pathlib import Path
from typing import Optional, Union, List


class ASTEditor:
    """Safe code editing using Python AST."""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.original_content = ""
        self.tree = None
        self._load_file()
    
    def _load_file(self):
        """Load and parse the Python file."""
        try:
            self.original_content = self.file_path.read_text(encoding='utf-8')
            self.tree = ast.parse(self.original_content)
        except (SyntaxError, UnicodeDecodeError) as e:
            raise ValueError(f"Cannot parse file {self.file_path}: {e}")
    
    def replace_function(self, function_name: str, new_code: str) -> bool:
        """Replace a function with new code."""
        try:
            # Parse the new code
            new_tree = ast.parse(new_code)
            
            # Find the function to replace
            for i, node in enumerate(self.tree.body):
                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                    # Replace the function node
                    if new_tree.body:
                        self.tree.body[i] = new_tree.body[0]
                        return True
            return False
            
        except SyntaxError:
            return False
    
    def add_import(self, module_name: str, alias: Optional[str] = None) -> bool:
        """Add an import statement at the top of the file."""
        try:
            if alias:
                import_node = ast.Import(names=[ast.alias(name=module_name, asname=alias)])
            else:
                import_node = ast.Import(names=[ast.alias(name=module_name)])
            
            # Insert at the beginning (after any existing imports)
            insert_pos = 0
            for i, node in enumerate(self.tree.body):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    insert_pos = i + 1
                else:
                    break
            
            self.tree.body.insert(insert_pos, import_node)
            return True
            
        except Exception:
            return False
    
    def add_from_import(self, module: str, names: List[str]) -> bool:
        """Add a from-import statement."""
        try:
            aliases = [ast.alias(name=name, asname=None) for name in names]
            import_node = ast.ImportFrom(module=module, names=aliases, level=0)
            
            # Insert at the beginning (after any existing imports)
            insert_pos = 0
            for i, node in enumerate(self.tree.body):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    insert_pos = i + 1
                else:
                    break
            
            self.tree.body.insert(insert_pos, import_node)
            return True
            
        except Exception:
            return False
    
    def remove_function(self, function_name: str) -> bool:
        """Remove a function from the file."""
        for i, node in enumerate(self.tree.body):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                del self.tree.body[i]
                return True
        return False
    
    def replace_class(self, class_name: str, new_code: str) -> bool:
        """Replace a class with new code."""
        try:
            new_tree = ast.parse(new_code)
            
            for i, node in enumerate(self.tree.body):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    if new_tree.body:
                        self.tree.body[i] = new_tree.body[0]
                        return True
            return False
            
        except SyntaxError:
            return False
    
    def add_function_at_end(self, function_code: str) -> bool:
        """Add a function at the end of the file."""
        try:
            new_tree = ast.parse(function_code)
            if new_tree.body:
                self.tree.body.extend(new_tree.body)
                return True
            return False
            
        except SyntaxError:
            return False
    
    def find_function(self, function_name: str) -> Optional[ast.FunctionDef]:
        """Find a function node in the AST."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                return node
        return None
    
    def find_class(self, class_name: str) -> Optional[ast.ClassDef]:
        """Find a class node in the AST."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None
    
    def get_function_source(self, function_name: str) -> Optional[str]:
        """Get the source code of a function."""
        func_node = self.find_function(function_name)
        if func_node:
            start_line = func_node.lineno - 1
            end_line = func_node.end_lineno if func_node.end_lineno else start_line + 1
            lines = self.original_content.split('\n')
            return '\n'.join(lines[start_line:end_line])
        return None
    
    def save(self) -> bool:
        """Save the modified file."""
        try:
            # Convert AST back to code
            import astor
            
            formatted_code = astor.to_source(self.tree)
            
            # Add final newline if missing
            if not formatted_code.endswith('\n'):
                formatted_code += '\n'
            
            self.file_path.write_text(formatted_code, encoding='utf-8')
            return True
            
        except ImportError:
            # Fallback to basic formatting
            try:
                import black
                formatted_code = black.format_str(ast.unparse(self.tree))
                self.file_path.write_text(formatted_code, encoding='utf-8')
                return True
            except ImportError:
                # Last resort: use unparse
                formatted_code = ast.unparse(self.tree)
                self.file_path.write_text(formatted_code, encoding='utf-8')
                return True
        except Exception:
            return False
