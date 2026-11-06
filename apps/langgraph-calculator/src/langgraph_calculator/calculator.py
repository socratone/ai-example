"""Python 코드를 실행하지 않고 허용된 사칙연산 수식만 계산합니다."""

import ast
from decimal import Decimal, DecimalException, localcontext


def evaluate(expression: str) -> str:
    """수식을 검사한 뒤 Decimal 결과를 문자열로 반환합니다."""
    # 모델이 만든 수식이 지나치게 길어지는 것을 막습니다.
    if not expression or len(expression) > 200:
        raise ValueError("수식은 1~200자로 입력해 주세요.")

    # ast.parse는 수식을 문법 트리로 바꿀 뿐, 입력 코드를 실행하지 않습니다.
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("올바른 사칙연산 수식을 입력해 주세요.") from exc

    try:
        # Decimal을 사용해 0.1 + 0.2 같은 소수 계산의 부동소수점 오차를 피합니다.
        with localcontext() as context:
            context.prec = 28
            result = _evaluate_node(tree.body)
    except (DecimalException, OverflowError) as exc:
        raise ValueError("계산할 수 없는 수식입니다.") from exc

    if not result.is_finite():
        raise ValueError("유한한 숫자만 계산할 수 있습니다.")
    # 불필요한 끝자리 0과 지수 표기를 제거해 사람이 읽기 쉬운 값으로 만듭니다.
    return format(result.normalize(), "f")


def _evaluate_node(node: ast.AST) -> Decimal:
    """허용한 숫자·부호·사칙연산 노드만 재귀적으로 계산합니다."""
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ValueError("0으로 나눌 수 없습니다.")
            return left / right
    # 함수 호출, 변수, 거듭제곱 등은 여기까지 와서 모두 거부됩니다.
    raise ValueError("괄호, 소수, 사칙연산만 사용할 수 있습니다.")
