#!/usr/bin/env python3
"""
DORA Metrics Calculator
Computes 4 DORA metrics + Health Score per repo
"""

import sqlite3
import pandas as pd
from datetime import datetime, timezone

DB_PATH = "data/dora.db"


# ── DORA BAND THRESHOLDS (industry standard) ──────────────
# Based on DORA State of DevOps report
BANDS = {
    'deployment_frequency': {
        'Elite':  7,      # >7 deploys/week
        'High':   1,      # 1-7/week
        'Medium': 0.25,   # 1/month
        'Low':    0       # <1/month
    },
    'lead_time_hours': {
        'Elite':  24,     # <1 day
        'High':   168,    # <1 week
        'Medium': 720,    # <1 month
        'Low':    float('inf')
    },
    'mttr_hours': {
        'Elite':  1,      # <1 hour
        'High':   24,     # <1 day
        'Medium': 168,    # <1 week
        'Low':    float('inf')
    },
    'change_failure_rate': {
        'Elite':  0.05,   # <5%
        'High':   0.10,   # <10%
        'Medium': 0.15,   # <15%
        'Low':    1.0
    }
}

BAND_SCORE = {'Elite': 4, 'High': 3, 'Medium': 2, 'Low': 1, 'Insufficient Data': 0}


def get_band(metric, value):
    if value is None:
        return 'Insufficient Data'
    thresholds = BANDS[metric]
    if metric == 'deployment_frequency':
        if value >= thresholds['Elite']:   return 'Elite'
        if value >= thresholds['High']:    return 'High'
        if value >= thresholds['Medium']:  return 'Medium'
        return 'Low'
    else:  # lower is better
        if value <= thresholds['Elite']:   return 'Elite'
        if value <= thresholds['High']:    return 'High'
        if value <= thresholds['Medium']:  return 'Medium'
        return 'Low'


def calc_deployment_frequency(conn, repo):
    """Releases per week"""
    df = pd.read_sql("""
        SELECT published_at FROM releases
        WHERE repo = ? AND published_at IS NOT NULL
        ORDER BY published_at
    """, conn, params=(repo,))

    if len(df) < 2:
        # Fall back to merged PRs as proxy
        df = pd.read_sql("""
            SELECT merged_at as published_at FROM pull_requests
            WHERE repo = ? AND merged_at IS NOT NULL
            ORDER BY merged_at
        """, conn, params=(repo,))

    if len(df) < 2:
        return None

    df['published_at'] = pd.to_datetime(df['published_at'], utc=True)
    date_range_weeks = (df['published_at'].max() - df['published_at'].min()).days / 7
    if date_range_weeks == 0:
        return None
    return round(len(df) / date_range_weeks, 2)


def calc_lead_time(conn, repo):
    """Avg hours from PR open → merge"""
    df = pd.read_sql("""
        SELECT lead_time_hours FROM pull_requests
        WHERE repo = ?
        AND merged_at IS NOT NULL
        AND lead_time_hours IS NOT NULL
        AND lead_time_hours > 0
    """, conn, params=(repo,))

    if len(df) == 0:
        return None
    return round(df['lead_time_hours'].median(), 2)


def calc_mttr(conn, repo):
    """Avg hours to close bug issues"""
    df = pd.read_sql("""
        SELECT resolution_hours FROM issues
        WHERE repo = ?
        AND is_bug = 1
        AND state = 'closed'
        AND resolution_hours IS NOT NULL
        AND resolution_hours > 0
    """, conn, params=(repo,))

    if len(df) == 0:
        # Fall back: all closed issues
        df = pd.read_sql("""
            SELECT resolution_hours FROM issues
            WHERE repo = ?
            AND state = 'closed'
            AND resolution_hours IS NOT NULL
            AND resolution_hours > 0
        """, conn, params=(repo,))

    if len(df) == 0:
        return None
    return round(df['resolution_hours'].median(), 2)


def calc_change_failure_rate(conn, repo):
    """Revert PRs / total merged PRs"""
    total = pd.read_sql("""
        SELECT COUNT(*) as cnt FROM pull_requests
        WHERE repo = ? AND merged_at IS NOT NULL
    """, conn, params=(repo,)).iloc[0]['cnt']

    if total == 0:
        return None

    reverts = pd.read_sql("""
        SELECT COUNT(*) as cnt FROM pull_requests
        WHERE repo = ? AND is_revert = 1 AND merged_at IS NOT NULL
    """, conn, params=(repo,)).iloc[0]['cnt']

    return round(reverts / total, 4)


def compute_health_score(metrics):
    """Weighted composite score 0-100"""
    weights = {
        'deployment_frequency': 0.25,
        'lead_time':            0.30,
        'mttr':                 0.25,
        'change_failure_rate':  0.20,
    }
    band_map = {
        'deployment_frequency': get_band('deployment_frequency', metrics['deployment_frequency']),
        'lead_time':            get_band('lead_time_hours', metrics['lead_time']),
        'mttr':                 get_band('mttr_hours', metrics['mttr']),
        'change_failure_rate':  get_band('change_failure_rate', metrics['change_failure_rate']),
    }
    score = 0
    for key, weight in weights.items():
        score += BAND_SCORE[band_map[key]] * weight
    return round((score / 4) * 100, 1), band_map


def main():
    conn = sqlite3.connect(DB_PATH)

    repos = pd.read_sql("SELECT full_name FROM repos", conn)['full_name'].tolist()

    results = []
    for repo in repos:
        print(f"\n{repo}")
        dep_freq    = calc_deployment_frequency(conn, repo)
        lead_time   = calc_lead_time(conn, repo)
        mttr        = calc_mttr(conn, repo)
        cfr         = calc_change_failure_rate(conn, repo)

        metrics = {
            'deployment_frequency': dep_freq,
            'lead_time':            lead_time,
            'mttr':                 mttr,
            'change_failure_rate':  cfr,
        }

        health_score, bands = compute_health_score(metrics)

        print(f"  Deploy Freq : {dep_freq} /week  [{bands['deployment_frequency']}]")
        print(f"  Lead Time   : {lead_time} hrs   [{bands['lead_time']}]")
        print(f"  MTTR        : {mttr} hrs         [{bands['mttr']}]")
        print(f"  CFR         : {cfr}              [{bands['change_failure_rate']}]")
        print(f"  Health Score: {health_score}/100")

        results.append({
            'repo':                         repo,
            'deployment_frequency':         dep_freq,
            'deploy_freq_band':             bands['deployment_frequency'],
            'lead_time_hours':              lead_time,
            'lead_time_band':               bands['lead_time'],
            'mttr_hours':                   mttr,
            'mttr_band':                    bands['mttr'],
            'change_failure_rate':          cfr,
            'cfr_band':                     bands['change_failure_rate'],
            'health_score':                 health_score,
        })

    df = pd.DataFrame(results)
    df.to_csv("data/dora_metrics.csv", index=False)
    print(f"\n{'='*50}")
    print("DORA METRICS SUMMARY")
    print(df[['repo', 'health_score', 'deploy_freq_band',
              'lead_time_band', 'mttr_band', 'cfr_band']].to_string(index=False))
    print(f"\nSaved → data/dora_metrics.csv")
    conn.close()


if __name__ == '__main__':
    main()
