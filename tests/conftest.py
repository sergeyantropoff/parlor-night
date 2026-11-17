import os

os.environ["ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://boardmentor:boardmentor@127.0.0.1:54329/boardmentor_test",
)
os.environ["COOKIE_SECURE"] = "false"
os.environ["ALLOW_REGISTRATION"] = "false"
os.environ["VALKEY_URL"] = ""
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
