from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
HOME = (ROOT / "src/pages/HomePage.tsx").read_text(encoding="utf-8")
PROFILE = (ROOT / "src/pages/ProfilePage.tsx").read_text(encoding="utf-8")


def test_app_diagnostics_hook_is_before_all_render_returns() -> None:
    """React #310 regression: hooks must not be introduced after loading/error returns."""
    render_section = APP[APP.index("export default function App()") : APP.index("  const startupDiagnostics")]
    hook_index = render_section.index("const openDiagnosticsByHiddenGesture = useCallback")
    first_render_return_index = min(
        render_section.index('return <LoadingState title="Загружаем данные клуба" />'),
        render_section.index('return (\n      <ErrorState\n        title="Не удалось открыть Bloom Club"'),
        render_section.index('return (\n      <ContentProvider>'),
    )
    assert hook_index < first_render_return_index


def test_trial_referral_pages_keep_content_hooks_unconditional() -> None:
    """Trial/referral UI must not call content hooks from render helpers or branches."""
    home_component_prefix = HOME[HOME.index("export function HomePage") : HOME.index("  async function handleActivateTrial")]
    assert 'useContent()' in home_component_prefix
    assert home_component_prefix.count('useContentText(') >= 10
    assert 'function renderTrialCta()' not in home_component_prefix

    profile_component_prefix = PROFILE[PROFILE.index("export function ProfilePage") : PROFILE.index("  useEffect(() =>")]
    assert profile_component_prefix.count('useContentText(') == 4
    assert 'const trialAvailable = isTrialEligible(profile, subscription);' in profile_component_prefix


HOOK_NAMES = ("useState", "useEffect", "useMemo", "useCallback", "useRef", "useContent", "useContentText")


def _component_body(source: str, signature: str) -> str:
    start = source.index(signature)
    cursor = source.index("(", start) if "function" in signature else start
    paren_depth = 0
    brace = -1
    for index in range(cursor, len(source)):
        char = source[index]
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "{" and paren_depth == 0:
            brace = index
            break
    assert brace != -1, f"Could not find body start for {signature}"
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"Could not find end of component {signature}")


def _top_level_statement_lines(body: str) -> list[tuple[int, str]]:
    statements: list[tuple[int, str]] = []
    depth = 0
    for line_number, line in enumerate(body.splitlines(), start=1):
        stripped = line.strip()
        if depth == 0 and stripped:
            statements.append((line_number, stripped))
        depth += line.count("{") + line.count("(") + line.count("[")
        depth -= line.count("}") + line.count(")") + line.count("]")
    return statements


def _assert_no_top_level_hooks_after_render_return(source: str, signature: str) -> None:
    body = _component_body(source, signature)
    statements = _top_level_statement_lines(body)
    first_render_return = next(
        line_number
        for line_number, statement in statements
        if statement.startswith("return") or statement.startswith("if ") and "return" in statement
    )
    late_hooks = [
        (line_number, statement)
        for line_number, statement in statements
        if line_number > first_render_return and any(f"{hook}(" in statement for hook in HOOK_NAMES)
    ]
    assert late_hooks == []


def test_app_home_profile_keep_hook_order_stable_across_render_states() -> None:
    """React #310 regression: loading/error/success renders must reach the same hooks first."""
    _assert_no_top_level_hooks_after_render_return(APP, "export default function App()")
    _assert_no_top_level_hooks_after_render_return(HOME, "export function HomePage")
    _assert_no_top_level_hooks_after_render_return(PROFILE, "export function ProfilePage")
