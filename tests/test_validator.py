from __future__ import annotations

import unittest
from pathlib import Path

from pinescript_validator.diagnostics import Severity
from pinescript_validator.validator import PineScriptValidator


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = PineScriptValidator()

    def test_duplicate_variable_definition(self) -> None:
        diagnostics = self.validator.validate_text("a = 1\na = 2")
        self.assertTrue(any("already defined" in diagnostic.message for diagnostic in diagnostics))

    def test_unused_variable(self) -> None:
        diagnostics = self.validator.validate_text('indicator("Test")\nvalue = close')
        self.assertTrue(any("never used" in diagnostic.message for diagnostic in diagnostics))

    def test_invalid_named_argument(self) -> None:
        diagnostics = self.validator.validate_text('plot(close, invalid_param=true)')
        self.assertTrue(any("Invalid parameter 'invalid_param'" in diagnostic.message for diagnostic in diagnostics))

    def test_destructuring_reassignment_is_supported(self) -> None:
        diagnostics = self.validator.validate_text("[a, b] := foo()")
        self.assertFalse(any("Mismatched input" in diagnostic.message for diagnostic in diagnostics))

    def test_typed_array_declaration(self) -> None:
        diagnostics = self.validator.validate_text("var box[] mc_boxes = array.new_box()")
        self.assertFalse(any("Expected variable name" in diagnostic.message for diagnostic in diagnostics))

    def test_multiline_ternary_assignment(self) -> None:
        code = """
style =
     condition ? size.small :
                 size.normal
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unexpected token" in diagnostic.message for diagnostic in diagnostics))

    def test_function_with_block_then_tuple_return(self) -> None:
        code = """
foo(x) =>
    if x
        y := 1

    [a, b]
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Expected \"]\" after index expression" in diagnostic.message for diagnostic in diagnostics))

    def test_comment_does_not_trigger_function_error(self) -> None:
        diagnostics = self.validator.validate_text("x = 1 // no reclaim (close sweep)")
        self.assertFalse(any("Undefined function 'reclaim'" in diagnostic.message for diagnostic in diagnostics))

    def test_real_mother_candle_script_has_no_errors(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        script_path = project_root / "Backtests" / "MotherCandle.pine"
        diagnostics = self.validator.validate_file(script_path)
        error_messages = [diagnostic.message for diagnostic in diagnostics if diagnostic.severity == Severity.ERROR]
        self.assertEqual(error_messages, [])

    def test_generic_function_call_and_dotted_array_type(self) -> None:
        code = "var chart.point[] _points = array.new<chart.point>()"
        diagnostics = self.validator.validate_text(code)
        self.assertEqual([d for d in diagnostics if d.severity == Severity.ERROR], [])

    def test_switch_statement_parses(self) -> None:
        code = """
switch mode
    "A" =>
        x := 1
    =>
        x := 2
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unexpected token: =>" in d.message for d in diagnostics))

    def test_switch_expression_without_selector_parses(self) -> None:
        code = """
value = switch
    cond1 => 1
    cond2 => 2
    => 3
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unexpected token: =>" in d.message for d in diagnostics))

    def test_switch_expression_with_selector_parses(self) -> None:
        code = """
value := switch mode
    "A" => 1
    "B" => 2
    => 3
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unexpected token: =>" in d.message for d in diagnostics))

    def test_if_expression_multiline_parses(self) -> None:
        code = """
foo() =>
    x = if true
        1
    else
        2
    x
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any('Expected "else" in if expression' in d.message for d in diagnostics))
        self.assertFalse(any("Unexpected token" in d.message for d in diagnostics))

    def test_input_timeframe_active_parameter(self) -> None:
        diagnostics = self.validator.validate_text('tf = input.timeframe("5S", "Lower timeframe", active=true)')
        self.assertFalse(any("Invalid parameter 'active'" in d.message for d in diagnostics))

    def test_bare_builtin_namespaces_are_valid_identifiers(self) -> None:
        diagnostics = self.validator.validate_text("x = barstate\ny = timeframe\nz = syminfo")
        self.assertFalse(any("Undefined variable 'barstate'" in d.message for d in diagnostics))
        self.assertFalse(any("Undefined variable 'timeframe'" in d.message for d in diagnostics))
        self.assertFalse(any("Undefined variable 'syminfo'" in d.message for d in diagnostics))

    def test_documented_namespace_constants_are_accepted(self) -> None:
        code = """
x = size.small
y = text.align_left
z = xloc.bar_time
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unknown property" in d.message for d in diagnostics))
        self.assertFalse(any("Undefined variable" in d.message for d in diagnostics))

    def test_unknown_property_on_known_namespace_is_reported(self) -> None:
        diagnostics = self.validator.validate_text("x = barstate.not_a_real_member")
        self.assertTrue(any("Unknown property 'not_a_real_member' on namespace 'barstate'" in d.message for d in diagnostics))

    def test_consistency_warning_for_conditional_stateful_user_function(self) -> None:
        code = """
f_hist() =>
    close[1]

if cond
    x = f_hist()
"""
        diagnostics = self.validator.validate_text(code)
        self.assertTrue(any('The function "f_hist" should be called on each calculation for consistency.' in d.message for d in diagnostics))
        self.assertTrue(any("extract the call from this scope" in d.message for d in diagnostics))

    def test_consistency_warning_for_ternary_ta_cum(self) -> None:
        code = """
f(flag) =>
    threshold = flag ? ta.cum(close) / bar_index : 0.0
    threshold
"""
        diagnostics = self.validator.validate_text(code)
        self.assertTrue(any('The function "ta.cum" should be called on each calculation for consistency.' in d.message for d in diagnostics))
        self.assertTrue(any("extract the call from the ternary operator or from the scope" in d.message for d in diagnostics))

    def test_pure_user_function_in_conditional_scope_does_not_warn(self) -> None:
        code = """
f_pure(x) =>
    x + 1

if cond
    y = f_pure(close)
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any('The function "f_pure" should be called on each calculation for consistency.' in d.message for d in diagnostics))

    def test_instance_method_call_on_variable(self) -> None:
        code = """
arr = array.new_float()
value = arr.size()
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Undefined function 'arr.size'" in d.message for d in diagnostics))

    def test_destructuring_declares_all_names_for_namespace_checks(self) -> None:
        code = """
[uV15, dV15] = sourceSeries
x = uV15.size()
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Undefined namespace or variable 'uV15'" in d.message for d in diagnostics))

    def test_generic_map_type_annotation_parses(self) -> None:
        diagnostics = self.validator.validate_text("var map<string, bool> alerts = map.new<string, bool>()")
        self.assertFalse(any("Expected variable name" in d.message for d in diagnostics))

    def test_type_declaration_and_member_assignment_parse(self) -> None:
        code = """
type srInfo
    int startTime
    bool active = true

render(srInfo sr) =>
    sr.active := false
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unexpected token: :=" in d.message for d in diagnostics))
        self.assertFalse(any("Undefined variable 'srInfo'" in d.message for d in diagnostics))

    def test_for_destructuring_iterators(self) -> None:
        code = """
for [i, ln] in lines
    lines.remove(i)
    ln.set_x2(bar_index)
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Undefined variable 'i'" in d.message for d in diagnostics))
        self.assertFalse(any("Undefined variable 'ln'" in d.message for d in diagnostics))

    def test_multiline_function_params_parse(self) -> None:
        code = """
foo(
    int a,
    int b,
    string c
) =>
    a + b
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unexpected token: ," in d.message for d in diagnostics))
        self.assertFalse(any("Undefined function 'foo'" in d.message for d in diagnostics))

    def test_comma_separated_statements_parse(self) -> None:
        diagnostics = self.validator.validate_text("a := 1, b := 2, c := a + b")
        self.assertFalse(any("Unexpected token: ," in d.message for d in diagnostics))

    def test_for_loop_with_by_clause(self) -> None:
        code = """
for i = 0 to 10 by 1
    x := i
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Undefined variable 'by'" in d.message for d in diagnostics))

    def test_unused_loop_iterator_does_not_emit_hint(self) -> None:
        code = """
for index = 0 to 10
    value := close
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Variable 'index' is declared but never used." in d.message for d in diagnostics))

    def test_unused_destructured_loop_iterators_do_not_emit_hint(self) -> None:
        code = """
for [iter, value] in items
    close
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Variable 'iter' is declared but never used." in d.message for d in diagnostics))
        self.assertFalse(any("Variable 'value' is declared but never used." in d.message for d in diagnostics))

    def test_leading_dot_float_literal(self) -> None:
        diagnostics = self.validator.validate_text("x = .1\ny = .0")
        self.assertFalse(any("Unexpected token: ." in d.message for d in diagnostics))

    def test_trailing_dot_float_literal(self) -> None:
        diagnostics = self.validator.validate_text("x = 0.\ny = 10.")
        self.assertFalse(any("Expected property name" in d.message for d in diagnostics))

    def test_switch_expression_case_block(self) -> None:
        code = """
[a, b] = switch mode
    "A" =>
        [x, y] = foo()
        [x, y]
    =>
        [0, 0]
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unexpected token: =" in d.message for d in diagnostics))

    def test_timestamp_overloads(self) -> None:
        diagnostics = self.validator.validate_text("x = timestamp(2020, 5, 11)")
        self.assertFalse(any("Too many arguments for 'timestamp'" in d.message for d in diagnostics))

    def test_multiline_destructuring_assignment(self) -> None:
        code = """
[a, b,
 c, d] = foo()
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Expected identifier in destructuring pattern" in d.message for d in diagnostics))

    def test_enum_declaration_namespace_usage(self) -> None:
        code = """
enum MA_Type
    SMA = "SMA"
    EMA = "EMA"

x = MA_Type.SMA
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Undefined variable 'MA_Type'" in d.message for d in diagnostics))

    def test_import_with_alias_is_supported(self) -> None:
        code = """
import TradingView/ta/9 as ta
x = ta.ema(close, 20)
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Undefined variable 'ta'" in d.message for d in diagnostics))

    def test_import_alias_namespace_members_are_not_validated_as_builtin_members(self) -> None:
        code = """
import TradingView/ta/7 as ta
x = ta.dema(close, 20)
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unknown property 'dema' on namespace 'ta'" in d.message for d in diagnostics))
        self.assertFalse(any("Undefined function 'ta.dema'" in d.message for d in diagnostics))

    def test_method_keyword_can_be_variable_name(self) -> None:
        diagnostics = self.validator.validate_text('method = input.string("ADX")')
        self.assertFalse(any("Expected method name" in d.message for d in diagnostics))

    def test_user_type_constructor_namespace_over_builtin_namespace(self) -> None:
        code = """
type session
    int t
x = session.new(1)
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Undefined function 'session.new'" in d.message for d in diagnostics))

    def test_var_series_type_qualifier_declaration_parses(self) -> None:
        code = """
var series float cluster_1 = na
var series float cluster_2 = na
var series int trend_regime = 0
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Variable 'float' is already defined" in d.message for d in diagnostics))
        self.assertFalse(any("Variable 'int' is already defined" in d.message for d in diagnostics))

    def test_inline_switch_case_with_compound_assignment_parses(self) -> None:
        code = """
upAndDownVolume(is_green, is_red, is_neut) =>
    bullVol = 0.0
    bearVol = 0.0
    switch
        is_green => bullVol += volume
        is_red => bearVol -= volume
    [bullVol, bearVol, volume]
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unexpected token: +=" in d.message for d in diagnostics))
        self.assertFalse(any("Unexpected token: =>" in d.message for d in diagnostics))

    def test_if_expression_with_negative_else_if_branch_parses(self) -> None:
        code = """
Pivots(int length) =>
    float ph = ta.highestbars(high, length) == 0 ? high : na
    float pl = ta.lowestbars(low, length) == 0 ? low  : na
    int dir = na
    dir := if not na(ph) and na(pl)
        1
    else if not na(pl) and na(ph)
        -1
    else
        dir[1]
    [dir, ph, pl]
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any('Expected "else" in if expression' in d.message for d in diagnostics))
        self.assertFalse(any("Undefined variable 'dir'" in d.message for d in diagnostics))

    def test_multiline_call_then_index_suffix_parses(self) -> None:
        code = """
foo() =>
    label.delete(label.new(bar_index,
                 "x",
                 textcolor = chart.bg_color)[1])
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any('Expected ")" after arguments' in d.message for d in diagnostics))

    def test_comparison_expression_is_not_treated_as_generic_type(self) -> None:
        code = """
histShouldUseLines(idx, visibleCount, neededSegments) =>
    idx < math.min(2, visibleCount)
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Unterminated generic type annotation" in d.message for d in diagnostics))
        self.assertFalse(any("Undefined function 'histShouldUseLines'" in d.message for d in diagnostics))

    def test_time_bars_back_named_parameter(self) -> None:
        diagnostics = self.validator.validate_text("t = time(timeframe.period, bars_back = -1)")
        self.assertFalse(any("Invalid parameter 'bars_back'" in d.message for d in diagnostics))

    def test_function_and_variable_name_overload_is_allowed(self) -> None:
        code = """
smema(src, length) =>
    ta.sma(src, length)
float smema = smema(close, 10)
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("already defined at line" in d.message for d in diagnostics))

    def test_type_and_function_name_overload_is_allowed(self) -> None:
        code = """
type level
    float value
level(float x) =>
    x
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("already defined at line" in d.message for d in diagnostics))

    def test_variable_named_color_is_tracked_as_variable_not_type(self) -> None:
        code = """
color = close > open ? color.green : color.red
plot(close, color = color)
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Variable 'color' is declared but never used." in d.message for d in diagnostics))
        self.assertFalse(any("Undefined variable 'color'" in d.message for d in diagnostics))

    def test_typed_variable_named_color_is_tracked_as_variable_not_type(self) -> None:
        code = """
color color = close > open ? color.green : color.red
plot(close, color = color)
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Variable 'color' is declared but never used." in d.message for d in diagnostics))
        self.assertFalse(any("Undefined variable 'color'" in d.message for d in diagnostics))

    def test_variable_named_timeframe_is_tracked_as_variable_not_builtin_namespace(self) -> None:
        code = """
timeframe = "D"
value = timeframe
"""
        diagnostics = self.validator.validate_text(code)
        self.assertFalse(any("Variable 'timeframe' is declared but never used." in d.message for d in diagnostics))


if __name__ == "__main__":
    unittest.main()
