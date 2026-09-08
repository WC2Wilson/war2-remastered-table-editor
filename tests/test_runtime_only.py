from pathlib import Path
import ast

p = Path(__file__).parents[1] / "src" / "war2_remastered_table_editor.py"
text = p.read_text(encoding="utf-8")
ast.parse(text)
assert "class ExecutableBackend" not in text
assert "Open EXE" not in text
assert "import pefile" not in text
assert "EXPECTED_TIMESTAMP = 0x699E13E7" in text
assert "APP_VERSION = \"1.2.0\"" in text
print("runtime-only source checks: PASS")
