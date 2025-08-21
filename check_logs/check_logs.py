import re

# Файл с логами
LOG_FILE = "лог.txt"

# Регулярки для поиска
PATTERNS = {
    "SQL Injection": [
        r"(\bUNION\b|\bSELECT\b|\binformation_schema\b|\bpg_sleep\b|1=1|--|#)"
    ],
    "XSS Injection": [
        r"(<script>|<img|<svg|onerror=|onload=)"
    ],
    "Suspicious paths": [
        r"(wp-admin|phpmyadmin|/etc/passwd|\.git/|\.env|\.bak|\.zip|\.tar\.gz)"
    ],
    "Brute force": [
        r"(401 Unauthorized|403 Forbidden|/login|/auth|/token)"
    ],
    "DoS attempts": [
        r"(Range: bytes=0-)"
    ]
}

def analyze_logs():
    with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        logs = f.readlines()

    results = {category: [] for category in PATTERNS.keys()}

    for line in logs:
        for category, patterns in PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    results[category].append(line.strip())

    # Выводим результаты
    for category, lines in results.items():
        print(f"\n--- {category} ---")
        if lines:
            for l in lines[:20]:  # ограничим до 20 строк на категорию
                print(l)
            if len(lines) > 20:
                print(f"... ещё {len(lines) - 20} строк")
        else:
            print("ничего не найдено ✅")

if __name__ == "__main__":
    analyze_logs()
