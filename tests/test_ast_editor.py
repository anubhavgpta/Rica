"""Unit tests for AST editor utilities."""

import pytest
import ast
from rica.utils.ast_editor import (
    find_function,
    replace_function,
    insert_import_source,
    add_function_source,
    edit_source_with_ast
)


class TestASTEditor:
    """Test cases for AST editor functionality."""

    def test_find_function_success(self):
        """Test finding an existing function."""
        source = """
def hello_world():
    print("Hello, World!")

def another_function():
    pass
"""
        tree = ast.parse(source)
        func = find_function(tree, "hello_world")
        
        assert func is not None
        assert func.name == "hello_world"

    def test_find_function_not_found(self):
        """Test finding a non-existent function."""
        source = """
def existing_function():
    pass
"""
        tree = ast.parse(source)
        func = find_function(tree, "non_existent")
        
        assert func is None

    def test_replace_function_success(self):
        """Test successful function replacement."""
        source = """
def original_function():
    print("Original")

def other_function():
    pass
"""
        new_code = """
def original_function():
    print("Modified")
    return True
"""
        result = replace_function(source, "original_function", new_code)
        
        assert result is not None
        assert "Modified" in result
        assert "Original" not in result
        assert "return True" in result

    def test_replace_function_not_found(self):
        """Test replacing a non-existent function."""
        source = """
def existing_function():
    pass
"""
        new_code = "def new_function(): pass"
        result = replace_function(source, "non_existent", new_code)
        
        assert result is None

    def test_replace_function_with_body_only(self):
        """Test replacing function with just body code."""
        source = """
def target_function():
    old_code()
"""
        new_body = """new_code()
return result"""
        
        result = replace_function(source, "target_function", new_body)
        
        assert result is not None
        assert "new_code()" in result
        assert "old_code()" not in result

    def test_insert_import_source_simple(self):
        """Test inserting a simple import."""
        source = """
def some_function():
    pass
"""
        result = insert_import_source(source, "os")
        
        assert result is not None
        assert result.strip().startswith("import os")
        assert "def some_function()" in result

    def test_insert_import_source_from_import(self):
        """Test inserting a 'from' import."""
        source = """
def some_function():
    pass
"""
        result = insert_import_source(source, "os.path", "join")
        
        assert result is not None
        assert "from os.path import join" in result
        assert "def some_function()" in result

    def test_insert_import_source_with_alias(self):
        """Test inserting import with alias."""
        source = """
def some_function():
    pass
"""
        result = insert_import_source(source, "numpy", name="array", alias="np")
        
        assert result is not None
        assert "from numpy import array as np" in result

    def test_add_function_source(self):
        """Test adding a new function."""
        source = """
def existing_function():
    pass
"""
        new_func = """
def new_function():
    return 'Hello'
"""
        result = add_function_source(source, new_func)
        
        assert result is not None
        assert "def existing_function()" in result
        assert "def new_function()" in result
        assert "return 'Hello'" in result

    def test_add_function_source_invalid_code(self):
        """Test adding invalid function code."""
        source = "def existing(): pass"
        invalid_code = "not a function"
        
        result = add_function_source(source, invalid_code)
        assert result is None

    def test_edit_source_with_ast_multiple_operations(self):
        """Test applying multiple AST operations."""
        source = """
def original_func():
    pass
"""
        
        def operation1(tree):
            return insert_import(tree, "datetime")
        
        def operation2(tree):
            return add_function(tree, "def new_func(): return True")
        
        result = edit_source_with_ast(source, [operation1, operation2])
        
        assert result is not None
        assert "import datetime" in result
        assert "def original_func()" in result
        assert "def new_func()" in result

    def test_replace_function_preserves_signature(self):
        """Test that function replacement preserves the original signature."""
        source = """
def complex_function(a, b=10, *args, **kwargs):
    old_body()
"""
        new_body = """new_body()
return a + b"""
        
        result = replace_function(source, "complex_function", new_body)
        
        assert result is not None
        assert "def complex_function(a, b=10, *args, **kwargs):" in result
        assert "new_body()" in result
        assert "old_body()" not in result

    def test_insert_import_source_preserves_order(self):
        """Test that imports are inserted at the top."""
        source = """# Comment at top

def function():
    pass
"""
        result = insert_import_source(source, "sys")
        
        lines = result.strip().split('\n')
        # Import should come after comment but before function
        import_line_index = next(i for i, line in enumerate(lines) if "import sys" in line)
        function_line_index = next(i for i, line in enumerate(lines) if "def function()" in line)
        
        assert import_line_index < function_line_index

    def test_syntax_error_handling(self):
        """Test handling of syntax errors in source code."""
        invalid_source = "def invalid_function(\n    # incomplete syntax"
        
        result = replace_function(invalid_source, "any", "pass")
        assert result is None
        
        result = insert_import_source(invalid_source, "os")
        assert result is None
        
        result = add_function_source(invalid_source, "def func(): pass")
        assert result is None


# Helper function for testing
def insert_import(tree, module):
    """Helper function to insert import for testing."""
    from rica.utils.ast_editor import insert_import
    return insert_import(tree, module)


def add_function(tree, code):
    """Helper function to add function for testing."""
    from rica.utils.ast_editor import add_function
    return add_function(tree, code)


if __name__ == "__main__":
    pytest.main([__file__])
