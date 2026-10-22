import os

# Tests must never touch the developer's live atelier.db. Test modules that need a
# file-backed store override this with tmp_path and reset_engine().
os.environ["DATABASE_URL"] = "sqlite://"
