from __future__ import annotations

from dataclasses import dataclass, field

from . import ast as AST
from .data_loader import KEYWORDS, TYPE_NAMES, FunctionSpec, load_builtin_data, load_function_specs
from .diagnostics import Diagnostic, Severity

CONSISTENCY_SENSITIVE_BUILTINS = frozenset({"ta.cum"})


@dataclass(slots=True)
class Symbol:
    name: str
    line: int
    column: int
    kind: str
    used: bool = False


@dataclass(slots=True)
class Scope:
    parent: "Scope | None" = None
    symbols: dict[str, Symbol] = field(default_factory=dict)
    children: list["Scope"] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.parent is not None:
            self.parent.children.append(self)

    def define(self, symbol: Symbol) -> Symbol | None:
        existing = self.symbols.get(symbol.name)
        if existing is not None:
            return existing
        self.symbols[symbol.name] = symbol
        return None

    def lookup(self, name: str) -> Symbol | None:
        scope: Scope | None = self
        while scope is not None:
            symbol = scope.symbols.get(name)
            if symbol is not None:
                return symbol
            scope = scope.parent
        return None

    def all_symbols(self) -> list[Symbol]:
        output = list(self.symbols.values())
        for child in self.children:
            output.extend(child.all_symbols())
        return output


class AstValidator:
    def __init__(self) -> None:
        self.builtins = load_builtin_data()
        self.function_specs = load_function_specs()
        self.errors: list[Diagnostic] = []
        self.function_declarations: dict[str, AST.FunctionDeclaration] = {}
        self.consistency_sensitive_functions: set[str] = set(CONSISTENCY_SENSITIVE_BUILTINS)

    def validate(self, program: AST.Program) -> list[Diagnostic]:
        self.errors = []
        self.function_declarations = {}
        self.consistency_sensitive_functions = set(CONSISTENCY_SENSITIVE_BUILTINS)
        self.collect_function_declarations(program.body)
        self.mark_consistency_sensitive_functions()
        global_scope = Scope()
        self.collect_direct_declarations(program.body, global_scope)
        self.validate_block(program.body, global_scope)
        self.check_unused_variables(global_scope)
        return self.errors

    def collect_function_declarations(self, statements: list[AST.Statement]) -> None:
        for statement in statements:
            if isinstance(statement, AST.FunctionDeclaration):
                self.function_declarations[statement.name] = statement
                self.collect_function_declarations(statement.body)
                continue
            if isinstance(statement, AST.IfStatement):
                self.collect_function_declarations(statement.consequent)
                if statement.alternate:
                    self.collect_function_declarations(statement.alternate)
                continue
            if isinstance(statement, AST.ForStatement | AST.WhileStatement):
                self.collect_function_declarations(statement.body)
                continue
            if isinstance(statement, AST.SwitchStatement):
                for case in statement.cases:
                    self.collect_function_declarations(case.body)

    def mark_consistency_sensitive_functions(self) -> None:
        changed = True
        while changed:
            changed = False
            for name, declaration in self.function_declarations.items():
                if name in self.consistency_sensitive_functions:
                    continue
                if any(self.statement_uses_consistency_sensitive_state(statement) for statement in declaration.body):
                    self.consistency_sensitive_functions.add(name)
                    changed = True

    def collect_direct_declarations(self, statements: list[AST.Statement], scope: Scope) -> None:
        for statement in statements:
            if isinstance(statement, AST.FunctionDeclaration):
                self.define_symbol(scope, statement.name, statement.line, statement.column, "function")
            elif isinstance(statement, AST.TypeDeclaration):
                self.define_symbol(scope, statement.name, statement.line, statement.column, "type")
            elif isinstance(statement, AST.ImportStatement):
                if statement.alias:
                    self.define_symbol(scope, statement.alias, statement.line, statement.column, "namespace")
            elif isinstance(statement, AST.VariableDeclaration):
                self.define_symbol(scope, statement.name, statement.name_line, statement.name_column, "variable")
            elif isinstance(statement, AST.DestructuringAssignment):
                for variable in statement.variables:
                    self.define_symbol(scope, variable.name, variable.line, variable.column, "variable")

    def define_symbol(self, scope: Scope, name: str, line: int, column: int, kind: str) -> None:
        if name == "_":
            return
        existing = scope.symbols.get(name)
        if existing is None:
            scope.symbols[name] = Symbol(name=name, line=line, column=column, kind=kind)
            return

        if existing.kind == kind:
            self.errors.append(
                Diagnostic(
                    line=line,
                    column=column,
                    length=len(name),
                    message=f"{kind.capitalize()} '{name}' is already defined at line {existing.line}",
                    severity=Severity.ERROR,
                    source="ast",
                )
            )
            return

        # Pine scripts frequently reuse names across type/function/variable domains.
        # Keep the first declaration and avoid false duplicate diagnostics in those cases.
        if {existing.kind, kind}.issubset({"type", "function", "variable"}):
            return

        self.errors.append(
            Diagnostic(
                line=line,
                column=column,
                length=len(name),
                message=f"{kind.capitalize()} '{name}' conflicts with existing {existing.kind} declared at line {existing.line}",
                severity=Severity.ERROR,
                source="ast",
            )
        )

    def validate_block(self, statements: list[AST.Statement], scope: Scope, conditional_context: str | None = None) -> None:
        for statement in statements:
            self.validate_statement(statement, scope, conditional_context)

    def validate_statement(self, statement: AST.Statement, scope: Scope, conditional_context: str | None = None) -> None:
        if isinstance(statement, AST.VariableDeclaration):
            if statement.init is not None:
                self.validate_expression(statement.init, scope, conditional_context)
            return

        if isinstance(statement, AST.DestructuringAssignment):
            self.validate_expression(statement.init, scope, conditional_context)
            return

        if isinstance(statement, AST.AssignmentStatement):
            if statement.name == "_":
                self.validate_expression(statement.value, scope, conditional_context)
                return
            symbol = scope.lookup(statement.name)
            if symbol is None:
                self.undefined_name(statement.name, statement.name_line, statement.name_column)
            self.validate_expression(statement.value, scope, conditional_context)
            return

        if isinstance(statement, AST.CompoundAssignmentStatement):
            if statement.name == "_":
                self.validate_expression(statement.value, scope, conditional_context)
                return
            symbol = scope.lookup(statement.name)
            if symbol is None:
                self.undefined_name(statement.name, statement.name_line, statement.name_column)
            else:
                symbol.used = True
            self.validate_expression(statement.value, scope, conditional_context)
            return

        if isinstance(statement, AST.TargetAssignmentStatement):
            if isinstance(statement.target, AST.Identifier):
                if statement.target.name == "_":
                    self.validate_expression(statement.value, scope, conditional_context)
                    return
                symbol = scope.lookup(statement.target.name)
                if symbol is None:
                    self.undefined_name(statement.target.name, statement.target.line, statement.target.column)
                else:
                    symbol.used = True
            else:
                self.validate_expression(statement.target, scope, conditional_context)
            self.validate_expression(statement.value, scope, conditional_context)
            return

        if isinstance(statement, AST.ExpressionStatement):
            self.validate_expression(statement.expression, scope, conditional_context)
            return

        if isinstance(statement, AST.ReturnStatement):
            self.validate_expression(statement.value, scope, conditional_context)
            return

        if isinstance(statement, AST.TypeDeclaration):
            for field in statement.fields:
                if field.default_value is not None:
                    self.validate_expression(field.default_value, scope, conditional_context)
            return

        if isinstance(statement, AST.ImportStatement):
            return

        if isinstance(statement, AST.FunctionDeclaration):
            function_scope = Scope(parent=scope)
            for param in statement.params:
                self.define_symbol(function_scope, param.name, param.line, param.column, "parameter")
                if param.default_value is not None:
                    self.validate_expression(param.default_value, function_scope)
            self.collect_direct_declarations(statement.body, function_scope)
            self.validate_block(statement.body, function_scope)
            return

        if isinstance(statement, AST.IfStatement):
            self.validate_expression(statement.condition, scope, conditional_context)
            consequent_scope = Scope(parent=scope)
            self.collect_direct_declarations(statement.consequent, consequent_scope)
            self.validate_block(statement.consequent, consequent_scope, conditional_context or "scope")
            if statement.alternate:
                alternate_scope = Scope(parent=scope)
                self.collect_direct_declarations(statement.alternate, alternate_scope)
                self.validate_block(statement.alternate, alternate_scope, conditional_context or "scope")
            return

        if isinstance(statement, AST.ForStatement):
            loop_scope = Scope(parent=scope)
            if statement.iterators:
                for iterator in statement.iterators:
                    self.define_symbol(loop_scope, iterator.name, iterator.line, iterator.column, "iterator")
            elif statement.iterator is not None:
                self.define_symbol(loop_scope, statement.iterator, statement.line, statement.column, "iterator")
            if statement.from_expr is not None:
                self.validate_expression(statement.from_expr, scope, conditional_context)
            if statement.to_expr is not None:
                self.validate_expression(statement.to_expr, scope, conditional_context)
            if statement.step_expr is not None:
                self.validate_expression(statement.step_expr, scope, conditional_context)
            if statement.iterable is not None:
                self.validate_expression(statement.iterable, scope, conditional_context)
            self.collect_direct_declarations(statement.body, loop_scope)
            self.validate_block(statement.body, loop_scope, conditional_context)
            return

        if isinstance(statement, AST.WhileStatement):
            self.validate_expression(statement.condition, scope, conditional_context)
            loop_scope = Scope(parent=scope)
            self.collect_direct_declarations(statement.body, loop_scope)
            self.validate_block(statement.body, loop_scope, conditional_context)
            return

        if isinstance(statement, AST.SwitchStatement):
            if statement.expression is not None:
                self.validate_expression(statement.expression, scope, conditional_context)
            for case in statement.cases:
                case_scope = Scope(parent=scope)
                if case.condition is not None:
                    self.validate_expression(case.condition, scope, conditional_context)
                self.collect_direct_declarations(case.body, case_scope)
                self.validate_block(case.body, case_scope, conditional_context or "scope")

    def validate_expression(self, expression: AST.Expression, scope: Scope, conditional_context: str | None = None) -> None:
        if isinstance(expression, AST.Literal):
            return

        if isinstance(expression, AST.Identifier):
            symbol = scope.lookup(expression.name)
            if symbol is not None:
                symbol.used = True
                return
            if expression.name in KEYWORDS or expression.name in TYPE_NAMES:
                return
            if expression.name in self.builtins.standalone_variables:
                return
            if expression.name in self.builtins.known_namespaces:
                return
            self.undefined_name(expression.name, expression.line, expression.column)
            return

        if isinstance(expression, AST.MemberExpression):
            if isinstance(expression.object, AST.Identifier):
                symbol = scope.lookup(expression.object.name)
                if symbol is not None and symbol.kind in {"type", "namespace"}:
                    return
                if expression.object.name in self.builtins.known_namespaces:
                    namespace_members = self.builtins.namespace_members.get(expression.object.name, frozenset())
                    if namespace_members and expression.property.name not in namespace_members:
                        self.errors.append(
                            Diagnostic(
                                line=expression.property.line,
                                column=expression.property.column,
                                length=len(expression.property.name),
                                message=f"Unknown property '{expression.property.name}' on namespace '{expression.object.name}'",
                                severity=Severity.ERROR,
                                source="ast",
                            )
                        )
                    return
            self.validate_expression(expression.object, scope, conditional_context)
            return

        if isinstance(expression, AST.CallExpression):
            function_name = self.extract_function_name(expression.callee)
            for argument in expression.arguments:
                self.validate_expression(argument.value, scope, conditional_context)
            if self.is_instance_method_call(expression, scope):
                self.validate_expression(expression.callee, scope, conditional_context)
                return
            if function_name is None:
                self.validate_expression(expression.callee, scope, conditional_context)
                return
            symbol = scope.lookup(function_name)
            if symbol is not None and symbol.kind == "function":
                symbol.used = True
            resolved_function_name = self.resolve_generic_function_name(function_name)
            if (
                symbol is None
                and resolved_function_name not in self.function_specs
                and resolved_function_name not in self.builtins.function_paths
                and function_name not in self.builtins.standalone_functions
            ):
                self.errors.append(
                    Diagnostic(
                        line=expression.line,
                        column=expression.column,
                        length=len(function_name),
                        message=f"Undefined function '{function_name}'",
                        severity=Severity.ERROR,
                        source="ast",
                    )
                )
                return
            self.warn_on_inconsistent_call(expression, function_name, resolved_function_name, symbol, conditional_context)
            spec = self.function_specs.get(resolved_function_name)
            if spec is not None:
                self.validate_call_signature(expression, resolved_function_name, spec)
            self.validate_special_cases(expression, resolved_function_name)
            return

        if isinstance(expression, AST.BinaryExpression):
            self.validate_expression(expression.left, scope, conditional_context)
            self.validate_expression(expression.right, scope, conditional_context)
            return

        if isinstance(expression, AST.UnaryExpression):
            self.validate_expression(expression.argument, scope, conditional_context)
            return

        if isinstance(expression, AST.TernaryExpression):
            self.validate_expression(expression.condition, scope, conditional_context)
            ternary_context = conditional_context or "ternary"
            self.validate_expression(expression.consequent, scope, ternary_context)
            self.validate_expression(expression.alternate, scope, ternary_context)
            return

        if isinstance(expression, AST.IfExpression):
            self.validate_expression(expression.condition, scope, conditional_context)
            ternary_context = conditional_context or "ternary"
            self.validate_expression(expression.consequent, scope, ternary_context)
            self.validate_expression(expression.alternate, scope, ternary_context)
            return

        if isinstance(expression, AST.SwitchExpression):
            if expression.expression is not None:
                self.validate_expression(expression.expression, scope, conditional_context)
            for case in expression.cases:
                case_scope = Scope(parent=scope)
                if case.condition is not None:
                    self.validate_expression(case.condition, scope, conditional_context)
                self.collect_direct_declarations(case.body, case_scope)
                case_context = conditional_context or "scope"
                self.validate_block(case.body, case_scope, case_context)
                self.validate_expression(case.value, case_scope, case_context)
            return

        if isinstance(expression, AST.ArrayExpression):
            for element in expression.elements:
                self.validate_expression(element, scope, conditional_context)
            return

        if isinstance(expression, AST.IndexExpression):
            self.validate_expression(expression.object, scope, conditional_context)
            self.validate_expression(expression.index, scope, conditional_context)

    def warn_on_inconsistent_call(
        self,
        call: AST.CallExpression,
        function_name: str,
        resolved_function_name: str,
        symbol: Symbol | None,
        conditional_context: str | None,
    ) -> None:
        if conditional_context is None:
            return
        if not self.is_consistency_sensitive_function(function_name, resolved_function_name, symbol):
            return

        if conditional_context == "ternary":
            message = (
                f'The function "{function_name}" should be called on each calculation for consistency. '
                "It is recommended to extract the call from the ternary operator or from the scope"
            )
        else:
            message = (
                f'The function "{function_name}" should be called on each calculation for consistency. '
                "It is recommended to extract the call from this scope"
            )

        self.errors.append(
            Diagnostic(
                line=call.line,
                column=call.column,
                length=len(function_name),
                message=message,
                severity=Severity.WARNING,
                source="ast",
            )
        )

    def is_consistency_sensitive_function(
        self,
        function_name: str,
        resolved_function_name: str,
        symbol: Symbol | None,
    ) -> bool:
        if function_name in self.consistency_sensitive_functions:
            return True
        if resolved_function_name in self.consistency_sensitive_functions:
            return True
        if symbol is not None and symbol.kind == "function" and symbol.name in self.consistency_sensitive_functions:
            return True
        return False

    def statement_uses_consistency_sensitive_state(self, statement: AST.Statement) -> bool:
        if isinstance(statement, AST.VariableDeclaration):
            return statement.init is not None and self.expression_uses_consistency_sensitive_state(statement.init)
        if isinstance(statement, AST.DestructuringAssignment):
            return self.expression_uses_consistency_sensitive_state(statement.init)
        if isinstance(statement, AST.AssignmentStatement | AST.CompoundAssignmentStatement):
            return self.expression_uses_consistency_sensitive_state(statement.value)
        if isinstance(statement, AST.TargetAssignmentStatement):
            return self.expression_uses_consistency_sensitive_state(statement.target) or self.expression_uses_consistency_sensitive_state(statement.value)
        if isinstance(statement, AST.ExpressionStatement):
            return self.expression_uses_consistency_sensitive_state(statement.expression)
        if isinstance(statement, AST.ReturnStatement):
            return self.expression_uses_consistency_sensitive_state(statement.value)
        if isinstance(statement, AST.TypeDeclaration):
            return any(
                field.default_value is not None and self.expression_uses_consistency_sensitive_state(field.default_value)
                for field in statement.fields
            )
        if isinstance(statement, AST.IfStatement):
            if self.expression_uses_consistency_sensitive_state(statement.condition):
                return True
            if any(self.statement_uses_consistency_sensitive_state(item) for item in statement.consequent):
                return True
            if statement.alternate and any(self.statement_uses_consistency_sensitive_state(item) for item in statement.alternate):
                return True
            return False
        if isinstance(statement, AST.ForStatement):
            if statement.from_expr is not None and self.expression_uses_consistency_sensitive_state(statement.from_expr):
                return True
            if statement.to_expr is not None and self.expression_uses_consistency_sensitive_state(statement.to_expr):
                return True
            if statement.step_expr is not None and self.expression_uses_consistency_sensitive_state(statement.step_expr):
                return True
            if statement.iterable is not None and self.expression_uses_consistency_sensitive_state(statement.iterable):
                return True
            return any(self.statement_uses_consistency_sensitive_state(item) for item in statement.body)
        if isinstance(statement, AST.WhileStatement):
            return self.expression_uses_consistency_sensitive_state(statement.condition) or any(
                self.statement_uses_consistency_sensitive_state(item) for item in statement.body
            )
        if isinstance(statement, AST.SwitchStatement):
            if statement.expression is not None and self.expression_uses_consistency_sensitive_state(statement.expression):
                return True
            for case in statement.cases:
                if case.condition is not None and self.expression_uses_consistency_sensitive_state(case.condition):
                    return True
                if any(self.statement_uses_consistency_sensitive_state(item) for item in case.body):
                    return True
            return False
        return False

    def expression_uses_consistency_sensitive_state(self, expression: AST.Expression) -> bool:
        if isinstance(expression, AST.Literal | AST.Identifier):
            return False
        if isinstance(expression, AST.IndexExpression):
            return True
        if isinstance(expression, AST.MemberExpression):
            return self.expression_uses_consistency_sensitive_state(expression.object)
        if isinstance(expression, AST.CallExpression):
            function_name = self.extract_function_name(expression.callee)
            resolved_function_name = self.resolve_generic_function_name(function_name) if function_name is not None else None
            if function_name in self.consistency_sensitive_functions:
                return True
            if resolved_function_name is not None and resolved_function_name in self.consistency_sensitive_functions:
                return True
            if self.expression_uses_consistency_sensitive_state(expression.callee):
                return True
            return any(self.expression_uses_consistency_sensitive_state(argument.value) for argument in expression.arguments)
        if isinstance(expression, AST.BinaryExpression):
            return self.expression_uses_consistency_sensitive_state(expression.left) or self.expression_uses_consistency_sensitive_state(expression.right)
        if isinstance(expression, AST.UnaryExpression):
            return self.expression_uses_consistency_sensitive_state(expression.argument)
        if isinstance(expression, AST.TernaryExpression):
            return (
                self.expression_uses_consistency_sensitive_state(expression.condition)
                or self.expression_uses_consistency_sensitive_state(expression.consequent)
                or self.expression_uses_consistency_sensitive_state(expression.alternate)
            )
        if isinstance(expression, AST.IfExpression):
            return (
                self.expression_uses_consistency_sensitive_state(expression.condition)
                or self.expression_uses_consistency_sensitive_state(expression.consequent)
                or self.expression_uses_consistency_sensitive_state(expression.alternate)
            )
        if isinstance(expression, AST.SwitchExpression):
            if expression.expression is not None and self.expression_uses_consistency_sensitive_state(expression.expression):
                return True
            for case in expression.cases:
                if case.condition is not None and self.expression_uses_consistency_sensitive_state(case.condition):
                    return True
                if any(self.statement_uses_consistency_sensitive_state(item) for item in case.body):
                    return True
                if self.expression_uses_consistency_sensitive_state(case.value):
                    return True
            return False
        if isinstance(expression, AST.ArrayExpression):
            return any(self.expression_uses_consistency_sensitive_state(element) for element in expression.elements)
        return False

    @staticmethod
    def extract_function_name(expression: AST.Expression) -> str | None:
        if isinstance(expression, AST.Identifier):
            return expression.name
        if isinstance(expression, AST.MemberExpression) and isinstance(expression.object, AST.Identifier):
            return f"{expression.object.name}.{expression.property.name}"
        return None

    def is_instance_method_call(self, call: AST.CallExpression, scope: Scope) -> bool:
        callee = call.callee
        if not isinstance(callee, AST.MemberExpression):
            return False
        if isinstance(callee.object, AST.Identifier):
            symbol = scope.lookup(callee.object.name)
            if symbol is not None and symbol.kind in {"type", "namespace"}:
                return True
            if callee.object.name in self.builtins.known_namespaces:
                return False
        return True

    def resolve_generic_function_name(self, function_name: str) -> str:
        if function_name in self.function_specs or function_name in self.builtins.function_paths:
            return function_name
        generic_prefix = f"{function_name}<"
        for name in self.function_specs:
            if name.startswith(generic_prefix):
                return name
        for name in self.builtins.function_paths:
            if name.startswith(generic_prefix):
                return name
        return function_name

    def validate_call_signature(self, call: AST.CallExpression, function_name: str, spec: FunctionSpec) -> None:
        positional_args = [arg for arg in call.arguments if arg.name is None]
        provided_named = {arg.name for arg in call.arguments if arg.name is not None}
        if function_name.startswith("input."):
            provided_named = {
                name
                for name in provided_named
                if name not in {"display", "active"}
            }

        best_score: int | None = None
        best_errors: list[Diagnostic] = []

        for overload in spec.overloads:
            overload_errors: list[Diagnostic] = []
            score = 0
            all_params = list(overload.required_params) + list(overload.optional_params)

            if not overload.variadic and len(positional_args) > len(all_params):
                overload_errors.append(
                    Diagnostic(
                        line=call.line,
                        column=call.column,
                        length=len(function_name),
                        message=f"Too many arguments for '{function_name}'. Expected at most {len(all_params)}, got {len(positional_args)}",
                        severity=Severity.ERROR,
                        source="ast",
                    )
                )
                score += 100

            for name in provided_named:
                if name not in all_params:
                    overload_errors.append(
                        Diagnostic(
                            line=call.line,
                            column=call.column,
                            length=len(name),
                            message=f"Invalid parameter '{name}' for '{function_name}'",
                            severity=Severity.ERROR,
                            source="ast",
                        )
                    )
                    score += 10

            positional_count = len(positional_args)
            for index, param_name in enumerate(overload.required_params):
                provided_positionally = index < positional_count
                provided_by_name = param_name in provided_named
                if not provided_positionally and not provided_by_name:
                    overload_errors.append(
                        Diagnostic(
                            line=call.line,
                            column=call.column,
                            length=len(function_name),
                            message=f"Missing required parameter '{param_name}' for '{function_name}'",
                            severity=Severity.ERROR,
                            source="ast",
                        )
                    )
                    score += 5

            if not overload_errors:
                return
            if best_score is None or score < best_score:
                best_score = score
                best_errors = overload_errors

        self.errors.extend(best_errors)

    def validate_special_cases(self, call: AST.CallExpression, function_name: str) -> None:
        if function_name == "plotshape":
            for argument in call.arguments:
                if argument.name == "shape":
                    self.errors.append(
                        Diagnostic(
                            line=call.line,
                            column=call.column,
                            length=5,
                            message='Invalid parameter "shape". Did you mean "style"?',
                            severity=Severity.ERROR,
                            source="ast",
                        )
                    )
                    break

        if function_name == "plotchar":
            for argument in call.arguments:
                if argument.name == "shape":
                    self.errors.append(
                        Diagnostic(
                            line=call.line,
                            column=call.column,
                            length=5,
                            message='Invalid parameter "shape". Did you mean "char"?',
                            severity=Severity.ERROR,
                            source="ast",
                        )
                    )
                    break

        if function_name in {"indicator", "strategy"}:
            has_timeframe = any(argument.name == "timeframe" for argument in call.arguments)
            has_timeframe_gaps = any(argument.name == "timeframe_gaps" for argument in call.arguments)
            if has_timeframe_gaps and not has_timeframe:
                self.errors.append(
                    Diagnostic(
                        line=call.line,
                        column=call.column,
                        length=len(function_name),
                        message='"timeframe_gaps" has no effect without a "timeframe" argument',
                        severity=Severity.WARNING,
                        source="ast",
                    )
                )

    def check_unused_variables(self, scope: Scope) -> None:
        for symbol in scope.all_symbols():
            # Match the extension more closely: loop iterators are scope helpers,
            # not regular variable declarations that should receive unused hints.
            if symbol.kind != "variable":
                continue
            if symbol.used or symbol.name.startswith("_"):
                continue
            self.errors.append(
                Diagnostic(
                    line=symbol.line,
                    column=symbol.column,
                    length=len(symbol.name),
                    message=f"Variable '{symbol.name}' is declared but never used.",
                    severity=Severity.HINT,
                    source="ast",
                )
            )

    def undefined_name(self, name: str, line: int, column: int) -> None:
        self.errors.append(
            Diagnostic(
                line=line,
                column=column,
                length=len(name),
                message=f"Undefined variable '{name}'",
                severity=Severity.ERROR,
                source="ast",
            )
        )
