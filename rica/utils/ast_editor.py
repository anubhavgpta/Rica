"""AST-based code editing utilities for safe Python code modification."""

import ast
from typing import Optional, List, Union
from loguru import logger


def find_function(tree: ast.AST, name: str) -> Optional[ast.FunctionDef]:
    """
    Find a function definition by name in the AST.
    
    Args:
        tree: The AST tree to search
        name: Name of the function to find
        
    Returns:
        FunctionDef node if found, None otherwise
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def replace_function(source_code: str, func_name: str, new_code: str) -> Optional[str]:
    """
    Replace a function body with new code while preserving the function signature.
    
    Args:
        source_code: Original source code
        func_name: Name of the function to replace
        new_code: New function code (can be just the body or full function)
        
    Returns:
        Modified source code if successful, None otherwise
    """
    try:
        tree = ast.parse(source_code)
        
        # Find the function to replace
        func_node = find_function(tree, func_name)
        if not func_node:
            logger.warning(f"[ast_editor] Function '{func_name}' not found")
            return None
            
        logger.info(f"[ast_editor] editing function: {func_name}")
        
        # Try to parse as full function first
        try:
            new_tree = ast.parse(new_code)
            if new_tree.body and isinstance(new_tree.body[0], ast.FunctionDef):
                # Full function provided, extract body
                new_body = new_tree.body[0].body
            else:
                # Body-only code provided
                new_body = new_tree.body
        except SyntaxError:
            # If parsing fails, try to wrap in a function to get proper AST
            wrapped_code = f"def temp_func():\n{new_code}"
            try:
                wrapped_tree = ast.parse(wrapped_code)
                new_body = wrapped_tree.body[0].body
            except SyntaxError:
                logger.error(f"[ast_editor] Cannot parse new_code as valid Python")
                return None
            
        # Replace the function body
        func_node.body = new_body
        
        return ast.unparse(tree)
        
    except SyntaxError as e:
        logger.error(f"[ast_editor] Syntax error parsing code: {e}")
        return None
    except Exception as e:
        logger.error(f"[ast_editor] Error replacing function: {e}")
        return None


def insert_import(tree: ast.AST, module: str, name: Optional[str] = None, alias: Optional[str] = None) -> ast.AST:
    """
    Insert an import statement at the top of the module.
    
    Args:
        tree: The AST tree to modify
        module: Module to import (e.g., 'os.path')
        name: Name to import from module (for 'from' imports)
        alias: Alias for the imported name
        
    Returns:
        Modified AST tree
    """
    logger.info(f"[ast_editor] inserting import: {module}")
    
    if name:
        # Create 'from module import name [as alias]' statement
        import_node = ast.ImportFrom(
            module=module,
            names=[ast.alias(name=name, asname=alias)],
            level=0
        )
    else:
        # Create 'import module [as alias]' statement
        import_node = ast.Import(
            names=[ast.alias(name=module, asname=alias)]
        )
    
    # Insert at the beginning of the module body
    if isinstance(tree, ast.Module):
        tree.body.insert(0, import_node)
    
    return tree


def add_function(tree: ast.AST, code: str) -> Optional[ast.AST]:
    """
    Add a new function to the module.
    
    Args:
        tree: The AST tree to modify
        code: Function code to add
        
    Returns:
        Modified AST tree if successful, None otherwise
    """
    try:
        new_tree = ast.parse(code)
        
        if not new_tree.body or not isinstance(new_tree.body[0], ast.FunctionDef):
            logger.error("[ast_editor] Provided code is not a function definition")
            return None
            
        func_node = new_tree.body[0]
        logger.info(f"[ast_editor] adding function: {func_node.name}")
        
        if isinstance(tree, ast.Module):
            tree.body.append(func_node)
        
        return tree
        
    except SyntaxError as e:
        logger.error(f"[ast_editor] Syntax error parsing function code: {e}")
        return None
    except Exception as e:
        logger.error(f"[ast_editor] Error adding function: {e}")
        return None


def edit_source_with_ast(source_code: str, operations: List[callable]) -> Optional[str]:
    """
    Apply multiple AST operations to source code.
    
    Args:
        source_code: Original source code
        operations: List of functions that take and return an AST tree
        
    Returns:
        Modified source code if successful, None otherwise
    """
    try:
        tree = ast.parse(source_code)
        
        for operation in operations:
            tree = operation(tree)
            if tree is None:
                return None
                
        return ast.unparse(tree)
        
    except SyntaxError as e:
        logger.error(f"[ast_editor] Syntax error parsing source: {e}")
        return None
    except Exception as e:
        logger.error(f"[ast_editor] Error applying AST operations: {e}")
        return None


def insert_import_source(source_code: str, module: str, name: Optional[str] = None, alias: Optional[str] = None) -> Optional[str]:
    """
    Insert an import statement into source code.
    
    Args:
        source_code: Original source code
        module: Module to import
        name: Name to import from module
        alias: Alias for the imported name
        
    Returns:
        Modified source code if successful, None otherwise
    """
    try:
        tree = ast.parse(source_code)
        modified_tree = insert_import(tree, module, name, alias)
        return ast.unparse(modified_tree) if modified_tree else None
    except Exception as e:
        logger.error(f"[ast_editor] Error inserting import: {e}")
        return None


def add_function_source(source_code: str, code: str) -> Optional[str]:
    """
    Add a function to source code.
    
    Args:
        source_code: Original source code
        code: Function code to add
        
    Returns:
        Modified source code if successful, None otherwise
    """
    try:
        tree = ast.parse(source_code)
        modified_tree = add_function(tree, code)
        return ast.unparse(modified_tree) if modified_tree else None
    except Exception as e:
        logger.error(f"[ast_editor] Error adding function to source: {e}")
        return None
