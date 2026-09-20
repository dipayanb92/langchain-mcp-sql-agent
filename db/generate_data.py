"""
Generates a synthetic banking database (branches + bankers) for the
Qwen SQL agent to query. Safe to re-run — it drops and recreates both
tables each time so you always get a clean, consistent dataset.

Usage:
    python db/generate_data.py
"""
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

DB_PATH = Path(__file__).parent / "bank.db"

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
BRANCH_TYPES = ["Metro", "Urban", "Suburban", "Rural"]
ROLES = [
    "Relationship Manager",
    "Branch Manager",
    "Loan Officer",
    "Financial Advisor",
    "Teller",
    "Credit Analyst",
]
PERFORMANCE_RATINGS = ["Excellent", "Good", "Average", "Needs Improvement"]

N_BRANCHES = 15
N_BANKERS = 140


def random_date(start: date, end: date) -> date:
    delta_days = (end - start).days
    return start + timedelta(days=random.randint(0, delta_days))


def build_branches():
    rows = []
    for branch_id in range(1, N_BRANCHES + 1):
        city = fake.city()
        region = random.choice(REGIONS)
        branch_type = random.choices(BRANCH_TYPES, weights=[3, 3, 2, 1])[0]
        opened = random_date(date(1995, 1, 1), date(2022, 12, 31))
        total_deposits = round(random.uniform(5_000_000, 120_000_000), 2)
        total_loans = round(total_deposits * random.uniform(0.35, 0.85), 2)
        customer_count = random.randint(800, 15000)
        rows.append(
            (
                branch_id,
                f"{city} {branch_type} Branch",
                city,
                fake.state(),
                region,
                branch_type,
                opened.isoformat(),
                fake.name(),
                total_deposits,
                total_loans,
                customer_count,
            )
        )
    return rows


def build_bankers(branch_ids):
    rows = []
    for banker_id in range(1, N_BANKERS + 1):
        first, last = fake.first_name(), fake.last_name()
        role = random.choices(
            ROLES, weights=[30, 8, 15, 15, 20, 12]
        )[0]
        branch_id = random.choice(branch_ids)
        hire_date = random_date(date(2005, 1, 1), date(2025, 6, 30))
        years_experience = max(0, (date.today() - hire_date).days // 365)
        target = round(random.uniform(50_000, 400_000), 2)
        # actual performance clusters around target with noise, occasionally under/over
        actual = round(target * random.uniform(0.55, 1.35), 2)
        attainment = actual / target
        if attainment >= 1.1:
            rating = "Excellent"
        elif attainment >= 0.95:
            rating = "Good"
        elif attainment >= 0.75:
            rating = "Average"
        else:
            rating = "Needs Improvement"
        csat = round(random.uniform(2.5, 5.0), 2)
        rows.append(
            (
                banker_id,
                first,
                last,
                f"{first.lower()}.{last.lower()}@examplebank.com",
                role,
                branch_id,
                hire_date.isoformat(),
                years_experience,
                target,
                actual,
                csat,
                rating,
            )
        )
    return rows


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE branches (
            branch_id       INTEGER PRIMARY KEY,
            branch_name     TEXT NOT NULL,
            city            TEXT NOT NULL,
            state           TEXT NOT NULL,
            region          TEXT NOT NULL,
            branch_type     TEXT NOT NULL,
            opened_date     TEXT NOT NULL,
            manager_name    TEXT NOT NULL,
            total_deposits  REAL NOT NULL,
            total_loans     REAL NOT NULL,
            customer_count  INTEGER NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE bankers (
            banker_id                  INTEGER PRIMARY KEY,
            first_name                 TEXT NOT NULL,
            last_name                  TEXT NOT NULL,
            email                      TEXT NOT NULL,
            role                       TEXT NOT NULL,
            branch_id                  INTEGER NOT NULL REFERENCES branches(branch_id),
            hire_date                  TEXT NOT NULL,
            years_experience           INTEGER NOT NULL,
            monthly_sales_target       REAL NOT NULL,
            monthly_sales_actual       REAL NOT NULL,
            customer_satisfaction_score REAL NOT NULL,
            performance_rating        TEXT NOT NULL
        )
        """
    )

    branch_rows = build_branches()
    cur.executemany(
        "INSERT INTO branches VALUES (?,?,?,?,?,?,?,?,?,?,?)", branch_rows
    )

    branch_ids = [r[0] for r in branch_rows]
    banker_rows = build_bankers(branch_ids)
    cur.executemany(
        "INSERT INTO bankers VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", banker_rows
    )

    conn.commit()
    conn.close()
    print(f"Created {DB_PATH} with {len(branch_rows)} branches and {len(banker_rows)} bankers.")


if __name__ == "__main__":
    main()
