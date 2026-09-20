"""Create development-only local configuration, never overwrite user configuration."""

import argparse
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--without-redis", action="store_true", help="Explicit local-only cache opt-out")
args = parser.parse_args()
password = secrets.token_hex(24)
values = {
    "APP_ENV": "development",
    "DATABASE_URL": f"postgresql+psycopg://computer:{password}@127.0.0.1:55432/computer",
    "REDIS_URL": "" if args.without_redis else "redis://127.0.0.1:56379/0",
    "POSTGRES_PASSWORD": password,
    "SESSION_SIGNING_SECRET": secrets.token_hex(32),
    "CORS_ALLOWED_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
}
content = (root / ".env.example").read_text(encoding="utf-8")
lines = []
for line in content.splitlines():
    key = line.partition("=")[0]
    lines.append(f"{key}={values.pop(key)}" if key in values else line)
lines.extend(f"{key}={value}" for key, value in values.items())
try:
    with (root / ".env").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
except FileExistsError:
    raise SystemExit(".env already exists; left unchanged. Edit it manually if needed.") from None
print("Created ignored .env with random local-only credentials; values are not printed.")
