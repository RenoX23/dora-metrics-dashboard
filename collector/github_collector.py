#!/usr/bin/env python3
"""
GitHub API Collector
Fetches commits, PRs, releases, issues → SQLite
"""

import os
import sqlite3
import pandas as pd
from github import Github, Auth
from datetime import datetime, timezone
from dotenv import load_dotenv
import time

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")
g = Github(auth=Auth.Token(TOKEN))

TARGET_REPOS = [
    # Your repos
    "RenoX23/gitops-monitoring-project",
    "RenoX23/github-engineering-analytics-pipeline",
    "RenoX23/job-market-intelligence",
    "RenoX23/gapiq",
    "RenoX23/ecommerce-sales-analytics",
    "RenoX23/cloud-native-data-engineering",



    # Public orgs — rich data
    "apache/airflow",
    "grafana/grafana",
    "argoproj/argo-cd",
    "prometheus/prometheus",
    "dbt-labs/dbt-core",
]

DB_PATH = "data/dora.db"


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS repos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name   TEXT UNIQUE,
            owner       TEXT,
            name        TEXT,
            description TEXT,
            language    TEXT,
            stars       INTEGER,
            forks       INTEGER,
            created_at  TEXT,
            fetched_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS pull_requests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            repo            TEXT,
            pr_number       INTEGER,
            title           TEXT,
            state           TEXT,
            created_at      TEXT,
            merged_at       TEXT,
            closed_at       TEXT,
            lead_time_hours REAL,
            is_revert       INTEGER DEFAULT 0,
            UNIQUE(repo, pr_number)
        );

        CREATE TABLE IF NOT EXISTS releases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            repo        TEXT,
            tag_name    TEXT,
            name        TEXT,
            created_at  TEXT,
            published_at TEXT,
            UNIQUE(repo, tag_name)
        );

        CREATE TABLE IF NOT EXISTS issues (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            repo            TEXT,
            issue_number    INTEGER,
            title           TEXT,
            state           TEXT,
            is_bug          INTEGER DEFAULT 0,
            created_at      TEXT,
            closed_at       TEXT,
            resolution_hours REAL,
            UNIQUE(repo, issue_number)
        );
    """)
    conn.commit()
    print("DB initialized.")


def fetch_repo_meta(repo, conn):
    conn.execute("""
        INSERT OR REPLACE INTO repos
        (full_name, owner, name, description, language, stars, forks, created_at, fetched_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        repo.full_name,
        repo.owner.login,
        repo.name,
        repo.description,
        repo.language,
        repo.stargazers_count,
        repo.forks_count,
        str(repo.created_at),
        str(datetime.now(timezone.utc)),
    ))
    conn.commit()


def fetch_pull_requests(repo, conn, limit=200):
    print(f"  Fetching PRs...")
    count = 0
    for pr in repo.get_pulls(state='closed', sort='updated', direction='desc'):
        if count >= limit:
            break
        try:
            lead_time = None
            if pr.merged_at:
                delta = pr.merged_at - pr.created_at
                lead_time = delta.total_seconds() / 3600  # hours

            is_revert = 1 if pr.title and 'revert' in pr.title.lower() else 0

            conn.execute("""
                INSERT OR IGNORE INTO pull_requests
                (repo, pr_number, title, state, created_at, merged_at, closed_at,
                 lead_time_hours, is_revert)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                repo.full_name,
                pr.number,
                pr.title,
                pr.state,
                str(pr.created_at),
                str(pr.merged_at) if pr.merged_at else None,
                str(pr.closed_at) if pr.closed_at else None,
                lead_time,
                is_revert,
            ))
            count += 1
        except Exception as e:
            print(f"    PR error: {e}")
            continue

    conn.commit()
    print(f"  → {count} PRs fetched")


def fetch_releases(repo, conn, limit=50):
    print(f"  Fetching releases...")
    count = 0
    for rel in repo.get_releases():
        if count >= limit:
            break
        try:
            conn.execute("""
                INSERT OR IGNORE INTO releases
                (repo, tag_name, name, created_at, published_at)
                VALUES (?,?,?,?,?)
            """, (
                repo.full_name,
                rel.tag_name,
                rel.title,
                str(rel.created_at) if rel.created_at else None,
                str(rel.published_at) if rel.published_at else None,
            ))
            count += 1
        except Exception as e:
            print(f"    Release error: {e}")
            continue

    conn.commit()
    print(f"  → {count} releases fetched")


def fetch_issues(repo, conn, limit=200):
    print(f"  Fetching issues...")
    count = 0
    for issue in repo.get_issues(state='all', sort='updated', direction='desc'):
        if count >= limit:
            break
        if issue.pull_request:  # skip PRs listed as issues
            continue
        try:
            is_bug = 0
            if issue.labels:
                label_names = [l.name.lower() for l in issue.labels]
                if any(b in label_names for b in ['bug', 'fix', 'defect', 'error']):
                    is_bug = 1

            resolution_hours = None
            if issue.closed_at:
                delta = issue.closed_at - issue.created_at
                resolution_hours = delta.total_seconds() / 3600

            conn.execute("""
                INSERT OR IGNORE INTO issues
                (repo, issue_number, title, state, is_bug,
                 created_at, closed_at, resolution_hours)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                repo.full_name,
                issue.number,
                issue.title,
                issue.state,
                is_bug,
                str(issue.created_at),
                str(issue.closed_at) if issue.closed_at else None,
                resolution_hours,
            ))
            count += 1
        except Exception as e:
            print(f"    Issue error: {e}")
            continue

    conn.commit()
    print(f"  → {count} issues fetched")


def main():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # Check rate limit
    try:
        rate = g.get_rate_limit()
        remaining = rate.core.remaining if hasattr(rate, 'core') else g.rate_limiting[0]
        limit = rate.core.limit if hasattr(rate, 'core') else g.rate_limiting[1]
        print(f"GitHub API rate limit: {remaining}/{limit}\n")
    except Exception as e:
        print(f"Rate limit check skipped: {e}\n")

    for repo_name in TARGET_REPOS:
        print(f"\n{'='*50}")
        print(f"Repo: {repo_name}")
        try:
            repo = g.get_repo(repo_name)
            fetch_repo_meta(repo, conn)
            fetch_pull_requests(repo, conn, limit=200)
            fetch_releases(repo, conn, limit=50)
            fetch_issues(repo, conn, limit=200)

            # Rate limit safety
            rate = g.get_rate_limit()
            print(f"  Rate limit remaining: {rate.core.remaining}")
            if rate.core.remaining < 100:
                print("  Rate limit low — sleeping 60s")
                time.sleep(60)

        except Exception as e:
            print(f"  [REPO ERROR] {e}")
            continue

    # Summary
    print(f"\n{'='*50}")
    print("COLLECTION DONE")
    for table in ['repos', 'pull_requests', 'releases', 'issues']:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {cur.fetchone()[0]} rows")

    conn.close()


if __name__ == '__main__':
    main()
