import os
import tempfile

# Keep tests from registering temporary workspaces in the real ~/.codex.
os.environ["CODEX_HOME"] = tempfile.mkdtemp(prefix="codex-home-")
# ...and from adding guides to the repo ATO library.
os.environ["AI_ACCOUNTING_LIBRARY"] = tempfile.mkdtemp(prefix="ato-library-")
