import os
import tempfile

# one throwaway config dir (salt) for the whole test session; never touch the real ~/.config
os.environ["TOKEN_AUTOPSY_HOME"] = tempfile.mkdtemp(prefix="ta-test-")
