f = "app/services/ingestion.py"
lines = open(f, encoding="utf-8").read().splitlines()
for i in range(34, 42):
    print(f"{i}: {repr(lines[i])}")
